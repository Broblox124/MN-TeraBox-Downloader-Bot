#please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN
import os
import re
import tempfile
import requests
import asyncio
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
#please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN

mongo_client = MongoClient(DATABASE.URI)
db = mongo_client[DATABASE.NAME]

settings_col = db["terabox_settings"]
queue_col = db["terabox_queue"]
last_upload_col = db["terabox_lastupload"]

TERABOX_REGEX = r'https?://(?:www\.)?[^/\s]*tera[^/\s]*\.[a-z]+/s/[^\s]+'

COOKIE = "__bid_n=19a43e782d674d36734207; _fbp=fb.1.1762075873135.776639740404065926; _ga=GA1.1.282403741.1762075873; _ga_06ZNKL8C2E=GS2.1.s1762517933$o3$g1$t1762517949$j44$l0$h0; _ga_HSVH9T016H=GS2.1.s1762341284$o2$g0$t1762341294$j50$l0$h0; _gcl_au=1.1.1986755109.1762075873; _rdt_em=:8c949e87cf16da80bc494a2b04c66a66ab63f6cac4155aa378c602c7343e0ba5,6c504c8f9f1f97ea213fb77179f0ceccf015deda3a8ad59208b066452d8a6d39,3695d266e9d1697a120ec443ba9a580cae31e3f076644205d4ad84d2ce22f6cd,3f029b132f44ca54cebf9b27b34c1f6087f0c9227dcea03d88ca50c29442d602,ca07ca59d63d2c83c70717803f86aa00d3e8080256ca30d52342667274ae5b61; _rdt_uuid=1762075874081.ee3d8dd2-22ed-4ff4-a0de-5fdbf3d06761; ab_sr=1.0.1_NTM4ZGFmM2M0MGRjYmQ5ODRlMjM3ZWFhZTZmYTczYTJlNWYxNGEwNDBhNTYxMWQ2MzIxYTYzZDUwMTAwOWI2M2NiY2FiOWExYTYwZTBhOWQ1M2IwMWYxMWNjZDQxMWM0YjEyNjA5MjQ3NGRhZjU4NmZjMjg0OTg3ZmY2YmYxYjBlOWJmZjE1OTU0NzhkZGExN2VlMGMyMmQ3MGIxNDJhMg==; ab_ymg_result={"data":"077517bab9a811769da3719821d7ed4e9444269dc9e7ff37115cf1ee0c35367487635da2c59b1fe95efa273fedb8523d50ee79c4dddf20cf1a376a8714230d92e602aedccaf2bec163ddcc3d3bb434624bd959850916de030fbdafcf8faf202f5cb25942e0616e7e56786e507327f078151223fe709fb59f2c62317c895c1094647e1b73f7ff900d2429900ae29fbdbd","key_id":"66","sign":"2387963a"}; browserid=5yTxW5LU80WcPn24U6mOqQv_NJBIGnAnfLB3IagjxhvjoduhXlelAcAfOr4=; lang=en; ndus=YfMjGd9peHuiCNXDDN-XZo7gqMIEDpy0X4J3VIGX" # add your own cookies like ndus=YzrYlCHteHuixx7IN5r0ABCDFXDGSTGBDJKLBKMKH

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "Host": "www.terabox.app",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cookie": COOKIE,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;"
              "q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.terabox.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": COOKIE,
}

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def find_between(text: str, start: str, end: str) -> str:
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except Exception:
        return ""

def get_file_info(share_url: str) -> dict:
    resp = requests.get(share_url, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch share page ({resp.status_code})")
    final_url = resp.url

    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise ValueError("Invalid share URL (missing surl)")

    page = requests.get(final_url, headers=HEADERS)
    html = page.text

    js_token = find_between(html, 'fn%28%22', '%22%29')
    logid = find_between(html, 'dp-logid=', '&')
    bdstoken = find_between(html, 'bdstoken":"', '"')
    if not all([js_token, logid, bdstoken]):
        raise ValueError("Failed to extract authentication tokens")

    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": surl, "root": "1,",
    }
    info = requests.get(
        "https://www.terabox.app/share/list?" + urlencode(params),
        headers=HEADERS
    ).json()

    if info.get("errno") or not info.get("list"):
        errmsg = info.get("errmsg", "Unknown error")
        raise ValueError(f"List API error: {errmsg}")

    file = info["list"][0]
    size_bytes = int(file.get("size", 0))
    return {
        "name": file.get("server_filename", "download"),
        "download_link": file.get("dlink", ""),
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes)
    }


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
        return await message.reply(f"❌ Failed to get file info:\n{e}")

    temp_path = os.path.join(tempfile.gettempdir(), info["name"])

    await message.reply("📥 Downloading...")

    try:
        with requests.get(info["download_link"], headers=DL_HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)

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
