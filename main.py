import asyncio
import re
import os
import json
import sqlite3
import logging
import threading
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import KeyboardButtonStyle as KBS
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import *
from emoji_helper import emoji_tag, emoji

# ================= লগিং =================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= ডেটাবেস =================
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # messages টেবিলে full_message কলাম যোগ করা হয়েছে
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        number TEXT,
        otp TEXT,
        service TEXT,
        country TEXT,
        country_code TEXT,
        timestamp TEXT,
        full_message TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS api_tokens (
        token TEXT PRIMARY KEY,
        name TEXT,
        created_by INTEGER,
        created_at TEXT,
        expires_at TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS countries (
        iso TEXT PRIMARY KEY,
        name TEXT,
        flag TEXT,
        emoji_id TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS services (
        name TEXT PRIMARY KEY,
        emoji_id TEXT
    )''')
    conn.commit()
    conn.close()

def get_token_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_tokens")
    return c.fetchone()[0]

def get_active_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_tokens WHERE is_active=1 AND expires_at > datetime('now')")
    return c.fetchone()[0]

def get_inactive_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM api_tokens WHERE is_active=0 OR expires_at <= datetime('now')")
    return c.fetchone()[0]

def get_otp_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    return c.fetchone()[0]

def get_all_tokens():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM api_tokens ORDER BY created_at DESC")
    return [dict(row) for row in c.fetchall()]

def get_token_info(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM api_tokens WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_token(name, days=30):
    token = secrets.token_hex(16)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO api_tokens (token, name, created_by, created_at, expires_at, is_active) VALUES (?,?,?,?,?,1)",
        (token, name, ADMIN_IDS[0], created_at, expires_at)
    )
    conn.commit()
    conn.close()
    return token, created_at, expires_at

def create_token_with_date(name, expiry_date):
    token = secrets.token_hex(16)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO api_tokens (token, name, created_by, created_at, expires_at, is_active) VALUES (?,?,?,?,?,1)",
        (token, name, ADMIN_IDS[0], created_at, expiry_date)
    )
    conn.commit()
    conn.close()
    return token, created_at, expiry_date

def deactivate_token(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE api_tokens SET is_active=0 WHERE token=?", (token,))
    conn.commit()
    conn.close()

def activate_token(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE api_tokens SET is_active=1 WHERE token=?", (token,))
    conn.commit()
    conn.close()

def get_otps_by_number(number, limit=50):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT otp, timestamp, service, country, country_code, full_message 
           FROM messages 
           WHERE number=? 
           ORDER BY timestamp DESC 
           LIMIT ?""",
        (number, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_message(msg_id, number, otp, service, country, country_code, timestamp, full_message):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT OR IGNORE INTO messages 
           (id, number, otp, service, country, country_code, timestamp, full_message) 
           VALUES (?,?,?,?,?,?,?,?)""",
        (msg_id, number, otp, service, country, country_code, timestamp, full_message)
    )
    conn.commit()
    conn.close()

def is_duplicate(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM messages WHERE id=?", (msg_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

# ================= কান্ট্রি কোড ম্যাপ =================
COUNTRY_CODE_MAP = {
    "UNITED KINGDOM": "GB",
    "AFGHANISTAN": "AF",
    "BANGLADESH": "BD",
    "INDIA": "IN",
    "PAKISTAN": "PK",
    "USA": "US",
    "CANADA": "CA",
    "AUSTRALIA": "AU",
    "GERMANY": "DE",
    "FRANCE": "FR",
    "ITALY": "IT",
    "SPAIN": "ES",
    "BRAZIL": "BR",
    "MEXICO": "MX",
    "CHINA": "CN",
    "JAPAN": "JP",
    "RUSSIA": "RU",
    "SOUTH AFRICA": "ZA",
    "NIGERIA": "NG",
    "KENYA": "KE",
    "EGYPT": "EG",
    "SAUDI ARABIA": "SA",
    "UAE": "AE",
    "TURKEY": "TR",
    "IRAN": "IR",
    "IRAQ": "IQ",
    "SYRIA": "SY",
    "LEBANON": "LB",
    "JORDAN": "JO",
    "ISRAEL": "IL",
}

def get_country_code(country_name):
    if not country_name:
        return ""
    return COUNTRY_CODE_MAP.get(country_name.upper(), "")

# ================= ক্যাপচা ও OTP ডিটেক্ট =================
def solve_captcha(text):
    match = re.search(r"(\d+)\s*\+\s*(\d+)", text)
    return int(match.group(1)) + int(match.group(2)) if match else None

def extract_otp_from_sms(sms_text):
    if not sms_text:
        return None
    text = ' '.join(sms_text.split())
    patterns = [
        (r'(?:code|otp|pin|verification|auth|one[- ]time|password)\s*[:;.]?\s*(?:is\s*)?#?\s*(\d{4,8})', None),
        (r'#(\d{4,8})\b', None),
        (r'(\d{3})[-—\s](\d{3})', 6),
        (r'(\d{2})[-—\s](\d{3})', 5),
        (r'(\d{3})[-—\s](\d{2})', 5),
        (r'(\d{3})[-—\s](\d{2})[-—\s](\d{2})', 7),
        (r'(\d{4})[-—\s](\d{4})', 8),
        (r'[\(\[]\s*(\d{4,8})\s*[\)\]]', None),
        (r'\b(\d{4,8})\b', None),
    ]
    for pattern, expected_len in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            if expected_len:
                digits = ''.join(match.groups())
                if len(digits) == expected_len and digits.isdigit():
                    return digits
            else:
                if len(match.groups()) > 1:
                    digits = ''.join(match.groups())
                    if digits.isdigit():
                        return digits
                else:
                    digits = match.group(1) if match.groups() else match.group(0)
                    if digits.isdigit():
                        return digits
    return None

def detect_service_from_sms(msg):
    if not msg:
        return "UNKNOWN"
    msg_l = msg.lower()
    patterns = {
        "WhatsApp": [r'whatsapp'],
        "Telegram": [r'telegram'],
        "Facebook": [r'facebook', r'fb'],
        "Instagram": [r'instagram', r'ig'],
        "Google": [r'google', r'gmail'],
        "Amazon": [r'amazon'],
        "Uber": [r'uber'],
        "Bolt": [r'bolt'],
        "Casushi": [r'casushi'],
        "PayPal": [r'paypal'],
        "Binance": [r'binance'],
        "Netflix": [r'netflix'],
        "Twitter": [r'twitter'],
        "Discord": [r'discord'],
        "Snapchat": [r'snapchat'],
    }
    for srv, pats in patterns.items():
        for p in pats:
            if re.search(p, msg_l):
                return srv
    return "UNKNOWN"

def format_number(number):
    clean = number.replace('+', '').replace(' ', '').strip()
    if len(clean) < 9:
        return clean, ''
    return clean[:5], clean[-4:]

# ================= প্লেwright স্ক্র্যাপার =================
async def login_and_save_state(page):
    logger.info("🌐 Opening login page...")
    await page.goto(LOGIN_URL, wait_until="networkidle")
    await page.wait_for_timeout(2000)
    await page.locator("input[type='text']").first.fill(USERNAME)
    await page.locator("input[type='password']").fill(PASSWORD)
    captcha_text = await page.locator("body").inner_text()
    answer = solve_captcha(captcha_text)
    if answer is None:
        raise Exception("Captcha not found")
    logger.info(f"✅ Captcha: {answer}")
    await page.locator("input").last.fill(str(answer))
    await page.locator("button").click()
    await page.wait_for_timeout(5000)
    if "login" in page.url.lower():
        raise Exception("Login failed")
    await page.context.storage_state(path=COOKIE_FILE)
    logger.info(f"🍪 Cookies saved")

async def create_context(browser):
    if os.path.exists(COOKIE_FILE):
        return await browser.new_context(storage_state=COOKIE_FILE)
    return await browser.new_context()

async def ensure_logged_in(context, browser):
    page = await context.new_page()
    try:
        await page.goto(STATS_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            logger.warning("Session expired – re-logging in...")
            await context.close()
            new_context = await browser.new_context()
            new_page = await new_context.new_page()
            await login_and_save_state(new_page)
            await new_page.close()
            return await browser.new_context(storage_state=COOKIE_FILE)
        return context
    finally:
        await page.close()

async def scrape_sms_stats(context):
    page = await context.new_page()
    try:
        await page.goto(STATS_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            return None
        await page.wait_for_function(
            """() => {
                const rows = document.querySelectorAll('table.dataTable tbody tr');
                for (let row of rows) {
                    const firstCell = row.querySelector('td');
                    if (firstCell && !firstCell.innerText.trim().match(/^[\\d,]+$/)) {
                        return true;
                    }
                }
                return false;
            }""",
            timeout=30000
        )
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.select_one('table.dataTable tbody')
        if not table:
            return []
        rows = table.find_all('tr')
        results = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 7:
                continue
            first = cols[0].get_text(strip=True)
            if re.match(r'^[\d,]+$', first):
                continue
            date = cols[0].get_text(strip=True)
            range_val = cols[1].get_text(strip=True)
            number = cols[2].get_text(strip=True)
            cli = cols[3].get_text(strip=True)
            sms = cols[4].get_text(strip=True)
            country = range_val.split('_')[0] if range_val else ""
            country_code = get_country_code(country)
            otp = extract_otp_from_sms(sms)
            if not otp:
                continue
            service = cli.strip() if cli and cli.strip() and cli.upper() not in ["UNKNOWN", "SERVICE", ""] else detect_service_from_sms(sms)
            msg_id = f"{date}_{number}_{otp}"
            results.append({
                "id": msg_id,
                "date": date,
                "country": country,
                "country_code": country_code,
                "number": number,
                "service": service,
                "sms": sms,
                "otp": otp
            })
        return results
    finally:
        await page.close()

# ================= টেলিগ্রাম মেসেজ তৈরি =================
def build_otp_message(entry):
    prefix = emoji_tag("ADMIN", "🤖")
    country = entry.get("country", "Unknown")
    number = entry.get("number", "")
    service = entry.get("service", "Unknown")
    otp = entry.get("otp", "")
    prefix_num, suffix_num = format_number(number)
    separator = emoji_tag("PACKAGE", "➖")
    masked = f'<b>+{prefix_num}{separator}{suffix_num}</b>'
    text = f"{prefix} <b>{country.upper()}</b> | <b>{service}</b> {masked}"
    otp_btn = InlineKeyboardButton(
        "𝐎𝐓𝐏",
        copy_text=CopyTextButton(text=otp),
        style=KBS.SUCCESS,
        icon_custom_emoji_id=emoji("OTP_BUTTON")
    )
    channel_btn = InlineKeyboardButton(
        "𝐂𝐇𝐀𝐍𝐍𝐄𝐋", url=CHANNEL_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=emoji("BELL")
    )
    bot_btn = InlineKeyboardButton(
        "𝐁𝐎𝐓", url=BOT_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=emoji("ADMIN")
    )
    keyboard = InlineKeyboardMarkup([[otp_btn], [channel_btn, bot_btn]])
    return text, keyboard

# ================= API সার্ভার =================
api_app = Flask(__name__)

@api_app.route('/get_otp', methods=['GET'])
def get_otp_api():
    token = request.args.get('token')
    number = request.args.get('number')
    
    if not token:
        return jsonify({"status": "error", "error": "missing_token", "message": "Token is required"}), 400
    if not number:
        return jsonify({"status": "error", "error": "missing_number", "message": "Number is required"}), 400
    
    token_info = get_token_info(token)
    if not token_info:
        return jsonify({"status": "error", "error": "invalid_token", "message": "Invalid token"}), 401
    if token_info["is_active"] != 1:
        return jsonify({"status": "error", "error": "inactive_token", "message": "Token is inactive"}), 401
    if token_info["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return jsonify({"status": "error", "error": "expired_token", "message": "Token has expired"}), 401
    
    otps = get_otps_by_number(number)
    if not otps:
        return jsonify({
            "status": "not_found",
            "data": {"number": number, "total_otps": 0, "otps": []},
            "Sms": "No OTPs found for this number"
        })
    
    formatted_otps = []
    for o in otps:
        formatted_otps.append({
            "otp": o["otp"],
            "timestamp": o["timestamp"],
            "service": o["service"],
            "country": o["country"],
            "country_code": o.get("country_code", ""),
            "message": o["full_message"]  # ← পুরো SMS
        })
    
    return jsonify({
        "status": "success",
        "data": {
            "number": number,
            "total_otps": len(formatted_otps),
            "otps": formatted_otps
        },
        "Sms": f"Found {len(formatted_otps)} OTPs for this number"
    })

@api_app.route('/latest_otp', methods=['GET'])
def latest_otp_api():
    """শুধু সর্বশেষ OTP রিটার্ন করে (আপনার কাঙ্ক্ষিত ফরম্যাটে)"""
    token = request.args.get('token')
    number = request.args.get('number')
    
    if not token or not number:
        return jsonify({"status": "error", "message": "Token and number required"}), 400
    
    token_info = get_token_info(token)
    if not token_info or token_info["is_active"] != 1:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    
    otps = get_otps_by_number(number, limit=1)
    if not otps:
        return jsonify({
            "status": "not_found",
            "data": {"number": number, "otp": None},
            "Sms": "No OTP found for this number"
        })
    
    o = otps[0]
    return jsonify({
        "status": "success",
        "data": {
            "number": number,
            "otp": o["otp"],
            "timestamp": o["timestamp"],
            "service": o["service"],
            "country": o["country"],
            "country_code": o.get("country_code", ""),
            "message": o["full_message"]  # ← পুরো SMS
        },
        "Sms": "OTP found successfully"
    })

@api_app.route('/stats', methods=['GET'])
def api_stats():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "message": "Token required"}), 400
    
    token_info = get_token_info(token)
    if not token_info or token_info["is_active"] != 1:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    
    return jsonify({
        "status": "success",
        "data": {
            "total_otps": get_otp_count(),
            "total_tokens": get_token_count(),
            "active_tokens": get_active_count()
        }
    })

@api_app.route('/check_token', methods=['GET'])
def check_token_api():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "error": "missing_token", "message": "Token required"}), 400
    
    token_info = get_token_info(token)
    if not token_info:
        return jsonify({"status": "error", "error": "invalid_token", "message": "Invalid token"}), 401
    
    is_valid = token_info["is_active"] == 1 and token_info["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({
        "status": "success",
        "data": {
            "token": token,
            "is_valid": is_valid,
            "name": token_info["name"],
            "expires_at": token_info["expires_at"],
            "is_active": bool(token_info["is_active"])
        }
    })

def start_api_server():
    api_app.run(host="0.0.0.0", port=API_PORT, debug=False, use_reloader=False)

# ================= মনিটর লুপ =================
async def monitor_loop(application):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    context = await create_context(browser)
    context = await ensure_logged_in(context, browser)
    while True:
        try:
            context = await ensure_logged_in(context, browser)
            data = await scrape_sms_stats(context)
            if data is None:
                await asyncio.sleep(10)
                continue
            for entry in data:
                if is_duplicate(entry["id"]):
                    continue
                text, keyboard = build_otp_message(entry)
                try:
                    await application.bot.send_message(chat_id=GROUP_ID, text=text, parse_mode="HTML", reply_markup=keyboard)
                    # ডেটাবেসে পুরো SMS সহ সংরক্ষণ
                    save_message(
                        entry["id"],
                        entry["number"],
                        entry["otp"],
                        entry["service"],
                        entry["country"],
                        entry.get("country_code", ""),
                        entry["date"],
                        entry["sms"]  # ← পুরো SMS
                    )
                    logger.info(f"Sent OTP: {entry['otp']} for {entry['number']}")
                except Exception as e:
                    logger.error(f"Send error: {e}")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            await asyncio.sleep(10)
        await asyncio.sleep(3)

# ================= টেলিগ্রাম হ্যান্ডলার (শুধু অ্যাডমিন) =================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            return
        return await func(update, context)
    return wrapper

@admin_only
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"{emoji_tag('NEW_NUMBER', '➕')} New Token", callback_data="new_token")],
        [InlineKeyboardButton(f"{emoji_tag('COPY_NUMBER', '📋')} List Tokens", callback_data="list_tokens")],
        [InlineKeyboardButton(f"{emoji_tag('ID_ICON', 'ℹ️')} Token Info", callback_data="token_info")],
        [InlineKeyboardButton(f"{emoji_tag('DELETE', '❌')} Remove Token", callback_data="remove_token")],
        [InlineKeyboardButton(f"{emoji_tag('CHECK_MARK', '✅')} Enable Token", callback_data="enable_token")],
        [InlineKeyboardButton(f"{emoji_tag('STATS', '📊')} Stats", callback_data="stats")],
        [InlineKeyboardButton(f"{emoji_tag('REFRESH', '🔄')} Refresh", callback_data="refresh_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"{emoji_tag('ADMIN', '🤖')} <b>API Management Panel</b>\n\n"
        f"{emoji_tag('STATS', '📊')} Total Tokens: <b>{get_token_count()}</b>\n"
        f"{emoji_tag('GREEN_CIRCLE', '🟢')} Active: <b>{get_active_count()}</b>\n"
        f"{emoji_tag('RED_CIRCLE', '🔴')} Inactive: <b>{get_inactive_count()}</b>\n"
        f"{emoji_tag('OTP_BUTTON', '🔑')} Total OTPs: <b>{get_otp_count()}</b>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

@admin_only
async def new_token_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(f"{emoji_tag('CLOCK', '📆')} 7 Days", callback_data="new_token_7")],
        [InlineKeyboardButton(f"{emoji_tag('ROCKET', '🚀')} 30 Days", callback_data="new_token_30")],
        [InlineKeyboardButton(f"{emoji_tag('GAMEPAD', '🎮')} 90 Days", callback_data="new_token_90")],
        [InlineKeyboardButton(f"{emoji_tag('WELCOME_SPARKLE', '✨')} Custom Date", callback_data="new_token_custom")],
        [InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"{emoji_tag('NEW_NUMBER', '➕')} <b>Create New Token</b>\n\nChoose expiry duration:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

@admin_only
async def create_token_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days_map = {"new_token_7": 7, "new_token_30": 30, "new_token_90": 90}
    if query.data in days_map:
        days = days_map[query.data]
        token, created, expires = create_token(f"Token_{datetime.now().strftime('%Y%m%d')}", days)
        text = (
            f"{emoji_tag('CHECK_MARK', '✅')} <b>New API token created!</b>\n\n"
            f"{emoji_tag('ID_ICON', 'ℹ️')} Name: <code>Token_{datetime.now().strftime('%Y%m%d')}</code>\n"
            f"{emoji_tag('ADMIN', '🔑')} Token: <code>{token}</code>\n"
            f"{emoji_tag('CLOCK', '📅')} Created: {created}\n"
            f"{emoji_tag('CLOCK', '⏰')} Expires: {expires}\n"
            f"{emoji_tag('GREEN_CIRCLE', '🟢')} Status: Active\n\n"
            f"{emoji_tag('PREFIX', '📌')} Usage:\n"
            f"<code>/get_otp?number=NUMBER&token={token}</code>"
        )
        keyboard = [[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif query.data == "new_token_custom":
        context.user_data["awaiting_custom_token"] = True
        text = (
            f"{emoji_tag('WELCOME_SPARKLE', '✨')} <b>Create Token with Custom Date</b>\n\n"
            "Send: <code>Name|YYYY-MM-DD</code>\nExample: <code>MyApp|2026-12-31</code>"
        )
        keyboard = [[InlineKeyboardButton(f"{emoji_tag('CANCEL', '❌')} Cancel", callback_data="panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_custom_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_custom_token"):
        return
    text = update.message.text.strip()
    context.user_data["awaiting_custom_token"] = False
    if "|" in text:
        name, date_str = text.split("|", 1)
        name = name.strip()
        date_str = date_str.strip()
    else:
        name = f"Token_{datetime.now().strftime('%Y%m%d')}"
        date_str = text
    try:
        expiry_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
        token, created, expires = create_token_with_date(name, expiry_date)
        msg = (
            f"{emoji_tag('CHECK_MARK', '✅')} <b>New API token created!</b>\n\n"
            f"{emoji_tag('ID_ICON', 'ℹ️')} Name: <code>{name}</code>\n"
            f"{emoji_tag('ADMIN', '🔑')} Token: <code>{token}</code>\n"
            f"{emoji_tag('CLOCK', '📅')} Created: {created}\n"
            f"{emoji_tag('CLOCK', '⏰')} Expires: {expires}\n"
            f"{emoji_tag('GREEN_CIRCLE', '🟢')} Status: Active\n\n"
            f"{emoji_tag('PREFIX', '📌')} Usage:\n"
            f"<code>/get_otp?number=NUMBER&token={token}</code>"
        )
        keyboard = [[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except ValueError:
        await update.message.reply_text(f"{emoji_tag('RED_CIRCLE', '❌')} Invalid date format. Use YYYY-MM-DD")

@admin_only
async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens = get_all_tokens()
    if not tokens:
        await query.edit_message_text(f"{emoji_tag('RED_CIRCLE', '⚠️')} No tokens found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]))
        return
    text = f"{emoji_tag('COPY_NUMBER', '📋')} <b>API Tokens ({len(tokens)} total)</b>\n\n"
    for i, t in enumerate(tokens[:10], 1):
        status = emoji_tag("GREEN_CIRCLE", "🟢") if t["is_active"] == 1 and t["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else emoji_tag("RED_CIRCLE", "🔴")
        text += f"{status} #{i}: <b>{t['name']}</b>\n"
        text += f"<code>{t['token'][:12]}...</code>\n"
        text += f"📅 Expires: {t['expires_at']}\n\n"
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_token_info"] = True
    text = f"{emoji_tag('ID_ICON', 'ℹ️')} Send the token you want info about."
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('CANCEL', '❌')} Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_token_info"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_token_info"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text(f"{emoji_tag('RED_CIRCLE', '❌')} Token not found.")
        return
    status = emoji_tag("GREEN_CIRCLE", "🟢") if info["is_active"] == 1 and info["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else emoji_tag("RED_CIRCLE", "🔴")
    text = (
        f"{emoji_tag('ID_ICON', 'ℹ️')} <b>Token Information</b>\n\n"
        f"🏷️ Name: <b>{info['name']}</b>\n"
        f"🔑 Token: <code>{info['token']}</code>\n"
        f"📊 Status: {status}\n"
        f"📅 Created: {info['created_at']}\n"
        f"⏰ Expires: {info['expires_at']}\n"
        f"👤 Created by: {info['created_by']}"
    )
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_remove_token"] = True
    text = f"{emoji_tag('DELETE', '❌')} Send the token you want to deactivate."
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('CANCEL', '❌')} Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_remove_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_remove_token"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text(f"{emoji_tag('RED_CIRCLE', '❌')} Token not found.")
        return
    deactivate_token(token)
    await update.message.reply_text(f"{emoji_tag('CHECK_MARK', '✅')} Token <code>{token[:12]}...</code> deactivated.", parse_mode="HTML")

@admin_only
async def enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_enable_token"] = True
    text = f"{emoji_tag('CHECK_MARK', '✅')} Send the token you want to reactivate."
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('CANCEL', '❌')} Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_enable_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_enable_token"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text(f"{emoji_tag('RED_CIRCLE', '❌')} Token not found.")
        return
    activate_token(token)
    await update.message.reply_text(f"{emoji_tag('CHECK_MARK', '✅')} Token <code>{token[:12]}...</code> reactivated.", parse_mode="HTML")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        f"{emoji_tag('STATS', '📊')} <b>Bot Statistics</b>\n\n"
        f"📈 Total OTPs: <b>{get_otp_count()}</b>\n"
        f"🔑 Total Tokens: <b>{get_token_count()}</b>\n"
        f"🟢 Active Tokens: <b>{get_active_count()}</b>\n"
        f"🔴 Inactive Tokens: <b>{get_inactive_count()}</b>"
    )
    keyboard = [[InlineKeyboardButton(f"{emoji_tag('BACK', '🔙')} Back", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def refresh_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await panel(update, context)

# ---- সাধারণ ইউজারদের জন্য কিছুই না ----
async def ignore_non_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return  # চুপ থাকবে

# ================= মেইন =================
def main():
    init_db()
    # API সার্ভার চালু
    threading.Thread(target=start_api_server, daemon=True).start()
    logger.info(f"🌐 API Server running on http://0.0.0.0:{API_PORT}")

    application = Application.builder().token(BOT_TOKEN).build()

    # কমান্ড হ্যান্ডলার (শুধু অ্যাডমিন)
    application.add_handler(CommandHandler("panel", panel))
    application.add_handler(CallbackQueryHandler(new_token_menu, pattern="^new_token$"))
    application.add_handler(CallbackQueryHandler(create_token_callback, pattern="^new_token_(7|30|90|custom)$"))
    application.add_handler(CallbackQueryHandler(list_tokens, pattern="^list_tokens$"))
    application.add_handler(CallbackQueryHandler(token_info, pattern="^token_info$"))
    application.add_handler(CallbackQueryHandler(remove_token, pattern="^remove_token$"))
    application.add_handler(CallbackQueryHandler(enable_token, pattern="^enable_token$"))
    application.add_handler(CallbackQueryHandler(stats, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(refresh_panel, pattern="^refresh_panel$"))
    application.add_handler(CallbackQueryHandler(panel, pattern="^panel$"))

    # টেক্সট ইনপুট হ্যান্ডলার (শুধু অ্যাডমিনদের জন্য)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enable_token))

    # সাধারণ ইউজারদের জন্য ইগনোর
    application.add_handler(MessageHandler(filters.ALL, ignore_non_admin), group=1)

    # মনিটর লুপ
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_loop(application))

    logger.info("🚀 Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()