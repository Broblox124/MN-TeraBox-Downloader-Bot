#please give credits https://github.com/MN-BOTS

# @MrMNTG @MusammilN

# please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN

import os
import re
import tempfile
import requests
import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs
from pyrogram import Client
from pyrogram import filters
from pyrogram.types import Message
from verify_patch import IS_VERIFY, is_verified, build_verification_link, HOW_TO_VERIFY
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import shutil
from config import CHANNEL, DATABASE
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

#------------------------

#Mongo setup

#------------------------

mongo_client = MongoClient(DATABASE.URI) db = mongo_client[DATABASE.NAME]

settings_col = db["terabox_settings"] queue_col = db["terabox_queue"] last_upload_col = db["terabox_lastupload"]

TERABOX_REGEX = r'https?://(?:www.)?[^/\s]tera[^/\s].[a-z]+/s/[^\s]+'

#------------------------

#Cookie / Headers

#------------------------

#NOTE: User-provided full cookie string is here. You can replace with only ndus=... if repo owner confirmed.

COOKIE = '__stripe_mid=7e85521c-2999-45d7-ad52-bccacc21be947d0744; __bid_n=19a43e782d674d36734207; _fbp=fb.1.1762075873135.776639740404065926; _ga=GA1.1.282403741.1762075873; _ga_06ZNKL8C2E=GS2.1.s1762850111$o4$g1$t1762850261$j54$l0$h0; _ga_HSVH9T016H=GS2.1.s1762341284$o2$g0$t1762341294$j50$l0$h0; _gcl_au=1.1.1986755109.1762075873; _rdt_em=:8c949e87cf16da80bc494a2b04c66a66ab63f6cac4155aa378c602c7343e0ba5,6c504c8f9f1f97ea213fb77179f0ceccf015deda3a8ad59208b066452d8a6d39,3695d266e9d1697a120ec443ba9a580cae31e3f076644205d4ad84d2ce22f6cd,3f029b132f44ca54cebf9b27b34c1f6087f0c9227dcea03d88ca50c29442d602,ca07ca59d63d2c83c70717803f86aa00d3e8080256ca30d52342667274ae5b61; _rdt_uuid=1762075874081.ee3d8dd2-22ed-4ff4-a0de-5fdbf3d06761; ab_sr=1.0.1_NTAzYzBmNjc2NTIzZWMxOTBhOGY2MTRmNjdjZWE4ZTc1ZjU3MWYxNjdjMjgyNWY4OTZmZGY5ODNjZTRiNGM1NTIxYzkzYzdhMGMwZjQ3OTQ5YzBjZDMwMDAyNjMxYmI0YTc0NWEyYjcxMjY0MjA1ZjU2YWMwZGQxMTZkYTM1MWY2N2ZkNzYzYTgyYjQ0ZWFiMjBiMzMyNWUxZDBlNjczMQ==; ab_ymg_result={"data":"2a91d703c9b896b9975b076a358035892ab22e34798473aa79bf41650dee64e4fea2a42fecdc3dd3eded908aeb7ff3efd59ce35f91f9c20c152f0edb7c3b53f8a1b7584bba7fc36ec38fec8028d0330bd3a64aefef181fd74a2888f4cd7a9f3b53554633be313f18f54292a969d1c308847df89f5aba50e8d1112df821a6f6862cd38eac3c5ec1f1d1c592cbfaeb1dab","key_id":"66","sign":"cf528be1"}; browserid=5yTxW5LU80WcPn24U6mOqQv_NJBIGnAnfLB3IagjxhvjoduhXlelAcAfOr4=; lang=en; ndus=YfMjGd9peHuiCNXDDN-XZo7gqMIEDpy0X4J3VIGX'

HEADERS = { "Accept": "application/json, text/plain, /", "Accept-Encoding": "gzip, deflate, br", "Accept-Language": "en-US,en;q=0.9,hi;q=0.8", "Connection": "keep-alive", "DNT": "1", # Use .com host (important) "Host": "www.terabox.com", "Upgrade-Insecure-Requests": "1", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0", "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"', "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1", "Cookie": COOKIE, "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"', }

DL_HEADERS = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/91.0.4472.124 Safari/537.36", "Accept": "text/html,application/xhtml+xml,application/xml;" "q=0.9,image/webp,/;q=0.8", "Accept-Language": "en-US,en;q=0.5", "Referer": "https://www.terabox.com/", "DNT": "1", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1", "Cookie": COOKIE, }

#------------------------

#Utils

#------------------------

def get_size(bytes_len: int) -> str: if bytes_len >= 1024 ** 3: return f"{bytes_len / 10243:.2f} GB" if bytes_len >= 1024 ** 2: return f"{bytes_len / 10242:.2f} MB" if bytes_len >= 1024: return f"{bytes_len / 1024:.2f} KB" return f"{bytes_len} bytes"

def _search_regex(patterns, text): for p in patterns: m = re.search(p, text) if m: return m.group(1) if m.groups() else m.group(0) return ""

Build a requests session with retries

def build_session(): s = requests.Session() s.headers.update(HEADERS) retries = Retry( total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(['GET', 'POST']) ) s.mount("https://", HTTPAdapter(max_retries=retries)) s.mount("http://", HTTPAdapter(max_retries=retries)) return s

#------------------------

#Core: get_file_info (robust)

#------------------------

def get_file_info(share_url: str) -> dict: session = build_session() try: resp = session.get(share_url, allow_redirects=True, timeout=20) except requests.exceptions.RequestException as ex: raise ValueError(f"Failed to fetch share page: {ex}")

if resp.status_code != 200:
    raise ValueError(f"Failed to fetch share page ({resp.status_code})")

final_url = resp.url
session.headers.update({"Referer": final_url, "Host": "www.terabox.com"})

html = resp.text or ""
print(f"[TERA DEBUG] final_url={final_url}")
print(f"[TERA DEBUG] html_len={len(html)}")

# Flexible token extraction
js_token = _search_regex([
    r'jsToken"\s*:\s*"([^\"]+)"',
    r'fn"%22([^\\"]+)%22"',
    r'fn"([^\\"]+)"'
], html)
logid = _search_regex([
    r'dp-logid=([^&\"\']+)',
    r'"dp-logid"\s*:\s*"([^\"]+)"'
], html)
bdstoken = _search_regex([
    r'bdstoken"\s*:\s*"([^\"]+)"',
    r'bdstoken=([^&\"\']+)'
], html)

print(f"[TERA DEBUG] tokens found js={bool(js_token)} logid={bool(logid)} bdstoken={bool(bdstoken)}")

if not all([js_token, logid, bdstoken]):
    preview = (html[:1200]).replace("\n", " ")
    raise ValueError(f"Failed to extract authentication tokens. final_url={final_url} html_preview={preview[:900]}")

params = {
    "app_id": "250528", "web": "1", "channel": "dubox",
    "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
    "page": "1", "num": "20", "by": "name", "order": "asc",
    "site_referer": final_url, "shorturl": parse_qs(urlparse(final_url).query).get("surl", [""])[0], "root": "1,",
}

list_url = "https://www.terabox.com/share/list?" + urlencode(params)
print(f"[TERA DEBUG] list_url={list_url}")

try:
    info_resp = session.get(list_url, timeout=20)
    info = info_resp.json()
except Exception as ex:
    txt = getattr(info_resp, "text", "")[:1000] if 'info_resp' in locals() else str(ex)
    raise ValueError(f"List API request failed or returned non-json. err={ex} resp_preview={txt}")

if info.get("errno") or not info.get("list"):
    errmsg = info.get("errmsg", "Unknown error")
    jpreview = json.dumps(info)[:800]
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

#------------------------

#Handler: download & upload

#------------------------

@Client.on_message(filters.private & filters.regex(TERABOX_REGEX)) async def handle_terabox(client, message: Message): user_id = message.from_user.id

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
