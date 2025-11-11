# please give credits https://github.com/MN-BOTS
# @MrMNTG @MusammilN

import os
import re
import tempfile
import requests
import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from verify_patch import IS_VERIFY, is_verified, build_verification_link, HOW_TO_VERIFY
from pymongo import MongoClient
import shutil
from config import CHANNEL, DATABASE
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------
# Mongo setup
# ------------------------
mongo_client = MongoClient(DATABASE.URI)
db = mongo_client[DATABASE.NAME]

settings_col = db["terabox_settings"]
queue_col = db["terabox_queue"]
last_upload_col = db["terabox_lastupload"]

TERABOX_REGEX = r'https?://(?:www\.)?[^/\s]*tera[^/\s]*\.[a-z]+/s/[^\s]+'

# ------------------------
# Cookie / Headers
# ------------------------
# By default use only ndus cookie (less brittle). Replace with full cookie string if needed.
COOKIE = 'ndus=YfMjGd9peHuiCNXDDN-XZo7gqMIEDpy0X4J3VIGX'

# Use a mobile User-Agent (often returns simpler HTML)
MOBILE_UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "Host": "www.terabox.com",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": MOBILE_UA,
    "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cookie": COOKIE,
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
}

DL_HEADERS = {
    "User-Agent": MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.terabox.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": COOKIE,
}

# ------------------------
# Utils
# ------------------------

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"


def _search_regex(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return ""


def build_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST'])
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s


# ------------------------
# Fallback HTML dlink extractor
# ------------------------
def try_extract_dlink_from_html(html: str) -> str:
    # 1) direct dlink-like tokens
    m = re.search(r'(https?://[^\s"\'<>]+dlink[^\s"\'<>]+)', html)
    if m:
        return m.group(1)
    # 2) data-dlink attribute
    m = re.search(r'data-dlink="([^"]+)"', html)
    if m:
        return m.group(1)
    # 3) potential direct file URLs
    m = re.search(r'(https?://[^\s"\'<>]+\.(?:mp4|mkv|jpg|jpeg|png|pdf|zip|rar))', html)
    if m:
        return m.group(1)
    # 4) sometimes `file_url` or similar inside scripts
    m = re.search(r'file_url"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    return ""


# ------------------------
# Core: get_file_info (aggressive extractor + fallback)
# ------------------------

def get_file_info(share_url: str) -> dict:
    session = build_session()
    # fetch share page
    try:
        resp = session.get(share_url, allow_redirects=True, timeout=20)
    except requests.exceptions.RequestException as ex:
        raise ValueError(f"Failed to fetch share page: {ex}")

    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch share page ({resp.status_code})")

    final_url = resp.url
    # ensure session will use referer and host for subsequent requests
    session.headers.update({"Referer": final_url, "Host": "www.terabox.com"})
    html = resp.text or ""

    # debug info
    print(f"[TERA DEBUG] final_url={final_url}")
    print(f"[TERA DEBUG] html_len={len(html)}")

    # quick detect: extraction code / password prompt
    lower_html = html.lower()
    if "please input the extraction code" in lower_html or "请输入提取码" in lower_html or "input the extraction code" in lower_html:
        # signal handler: this link requires an extraction code
        raise ValueError("PASSWORD_REQUIRED")

    # helper: try list of regexes against a text blob
    def try_patterns(text, patterns):
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        return ""

    # candidate patterns (more exhaustive)
    js_patterns = [
        r'jsToken"\s*:\s*"([^"]+)"',
        r'js_token"\s*:\s*"([^"]+)"',
        r'fn\("%22([^"]+)%22"\)',
        r'fn\("([^"]+)"\)',
        r'jsToken=([^&"\']+)',
    ]
    logid_patterns = [
        r'dp-logid=([^&"\']+)',
        r'"dp-logid"\s*:\s*"([^"]+)"',
        r'logid"\s*:\s*"([^"]+)"',
    ]
    bdstoken_patterns = [
        r'bdstoken"\s*:\s*"([^"]+)"',
        r'bdstoken=([^&"\']+)',
        r'"bdstoken"\s*:\s*"([^"]+)"'
    ]

    # 1) Try top-level html first
    js_token = try_patterns(html, js_patterns)
    logid = try_patterns(html, logid_patterns)
    bdstoken = try_patterns(html, bdstoken_patterns)
    print(f"[TERA DEBUG] top-level tokens js={bool(js_token)} logid={bool(logid)} bdstoken={bool(bdstoken)}")

    # 2) If not found, try searching inside every <script>...</script> block
    if not all([js_token, logid, bdstoken]):
        scripts = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html)
        for i, s in enumerate(scripts):
            if all([js_token, logid, bdstoken]):
                break
            if not js_token:
                js_token = try_patterns(s, js_patterns) or js_token
            if not logid:
                logid = try_patterns(s, logid_patterns) or logid
            if not bdstoken:
                bdstoken = try_patterns(s, bdstoken_patterns) or bdstoken
        print(f"[TERA DEBUG] script-scan tokens js={bool(js_token)} logid={bool(logid)} bdstoken={bool(bdstoken)} script_count={len(scripts)}")

    # 3) try to locate any JSON blobs that might include tokens (window.__INITIAL_STATE__ etc)
    if not all([js_token, logid, bdstoken]):
        json_blobs = re.findall(r'(\{(?:[^{}]|\{[^}]*\}){20,}\})', html)
        for jb in json_blobs:
            if all([js_token, logid, bdstoken]):
                break
            js_token = js_token or try_patterns(jb, js_patterns)
            logid = logid or try_patterns(jb, logid_patterns)
            bdstoken = bdstoken or try_patterns(jb, bdstoken_patterns)
        print(f"[TERA DEBUG] json-scan tokens js={bool(js_token)} logid={bool(logid)} bdstoken={bool(bdstoken)} json_blobs={len(json_blobs)}")

    # 4) fallback: try to find a direct dlink/file URL in HTML (no tokens required)
    if not all([js_token, logid, bdstoken]):
        fallback = try_extract_dlink_from_html(html)
        if fallback:
            print(f"[TERA DEBUG] fallback dlink found in HTML: {fallback[:200]}")
            # Build a minimal info dict using fallback direct link
            size_bytes = 0
            try:
                head = requests.head(fallback, headers=DL_HEADERS, allow_redirects=True, timeout=10)
                size_bytes = int(head.headers.get("Content-Length", 0) or 0)
            except Exception:
                size_bytes = 0
            return {
                "name": os.path.basename(urlparse(fallback).path) or "download",
                "download_link": fallback,
                "size_bytes": size_bytes,
                "size_str": get_size(size_bytes),
                "final_url": final_url,
            }

    # 5) final token check
    if not all([js_token, logid, bdstoken]):
        preview = html.replace("\n", " ").replace("\r", " ")[:3000]
        raise ValueError(f"Failed to extract authentication tokens. final_url={final_url} html_preview={preview}")

    # build params and call list
    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": parse_qs(urlparse(final_url).query).get("surl", [""])[0], "root": "1,",
    }
    list_url = "https://www.terabox.com/share/list?" + urlencode(params)
    print(f"[TERA DEBUG] list_url={list_url}")

    try:
        info_resp = session.get(list_url, timeout=30)
        info = info_resp.json()
    except Exception as ex:
        txt = getattr(info_resp, "text", "")[:1500] if 'info_resp' in locals() else str(ex)
        raise ValueError(f"List API request failed or returned non-json. err={ex} resp_preview={txt}")

    if info.get("errno") or not info.get("list"):
        errmsg = info.get("errmsg", "Unknown error")
        jpreview = json.dumps(info)[:1200]
        raise ValueError(f"List API error: {errmsg} json_preview={jpreview}")

    file = info["list"][0]
    dlink = file.get("dlink") or ""
    if not dlink:
        raise ValueError("No direct link (dlink) returned. Cookie missing/invalid or host/headers mismatch. file_preview=" + json.dumps(file)[:800])

    size_bytes = int(file.get("size", 0))
    return {
        "name": file.get("server_filename", "download"),
        "download_link": dlink,
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes),
        "final_url": final_url,
    }


# ------------------------
# Handler: download & upload
# ------------------------

@Client.on_message(filters.private & filters.regex(TERABOX_REGEX))
async def handle_terabox(client, message: Message):
    user_id = message.from_user.id

    if IS_VERIFY and not await is_verified(user_id):
        verify_url = await build_verification_link(client.me.username, user_id)
        buttons = [
            [
                InlineKeyboardButton("✅ Verify Now", url=verify_url),
                InlineKeyboardButton("📖 Tutorial", url=HOW_TO_VERIFY)
            ]
        ]
        await message.reply_text(
            "🔐 You must verify before using this command.\n\n⏳ Verification lasts for 12 hours.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    url = message.text.strip()
    try:
        info = get_file_info(url)
    except Exception as e:
        if str(e) == "PASSWORD_REQUIRED":
            # save pending share for user in DB and prompt for code (later you can add /pass handler)
            settings_col.update_one({"user_id": user_id}, {"$set": {"pending_share": url}}, upsert=True)
            return await message.reply("🔐 This link requires an extraction code. Reply with: /pass <code>")
        return await message.reply(f"❌ Failed to get file info:\n{e}")

    temp_path = os.path.join(tempfile.gettempdir(), info["name"])

    await message.reply("📥 Downloading...")

    # Use session + chunked streaming for robustness on big files
    session = build_session()
    dl_headers = dict(DL_HEADERS)
    dl_headers["Referer"] = info.get("final_url", "https://www.terabox.com/")

    try:
        with session.get(info["download_link"], headers=dl_headers, stream=True, timeout=(10, 600)) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        caption = (
            f"File Name: {info['name']}\n"
            f"File Size: {info['size_str']}\n"
            f"Link: {url}"
        )

        if CHANNEL.ID:
            await client.send_document(
                chat_id=CHANNEL.ID,
                document=temp_path,
                caption=caption,
                file_name=info["name"]
            )

        sent_msg = await client.send_document(
            chat_id=message.chat.id,
            document=temp_path,
            caption=caption,
            file_name=info["name"],
            protect_content=True
        )

        await message.reply("✅ File will be deleted from your chat after 12 hours.")
        await asyncio.sleep(43200)
        try:
            await sent_msg.delete()
        except Exception:
            pass

    except Exception as e:
        await message.reply(f"❌ Upload failed:\n`{e}`")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
