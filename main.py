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

# ================= কনফিগ =================
BOT_TOKEN = "8856560094:AAF-UyEMkFFvpEFgAD2rbRnJR42nWzS3zDA"
ADMIN_IDS = [8744359777]
GROUP_ID = -1004380384761

LOGIN_URL = "http://139.99.9.120/ints/login"
STATS_URL = "http://139.99.9.120/ints/client/SMSCDRStats"
USERNAME = "otp_work_rakesh"
PASSWORD = "otp_work_rakesh"

COOKIE_FILE = "cookies.json"
DB_FILE = "otp.db"
API_PORT = 5000

CHANNEL_URL = "https://t.me/your_channel"
BOT_URL = "https://t.me/your_bot"

# ================= পুরনো EMOJI (OTP মেসেজের জন্য) =================
EMOJI = {
    "SEPARATOR": "6307542847251814164",
    "PREFIX": "4958725487682650920",
    "OTP_BUTTON": "6206420230269310869",
    "CHANNEL_BUTTON": "6204010762206189094",
    "BOT_BUTTON": "5339267587337370029",
    "SUCCESS": "6205984471477393007",
}

# ================= ডিফল্ট ইমোজি (দেশ ও সার্ভিসের জন্য) =================
DEFAULT_EMOJIS = {
    "services": {
        "uber": "5298715455316303708",
        "bolt": "5343587658717219067",
        "whatsapp": "5298715455316303708",
        "telegram": "5339267587337370029",
        "casushi": "5346008706012169915",
    },
    "countries": {
        "gb": "5293993521026453119",  # United Kingdom
        "af": "5292108962391414885",  # Afghanistan
    }
}

# ================= নতুন ইমোজি আইডি (প্যানেলের জন্য) =================
CUSTOM_EMOJIS = {
    "NEW_TOKEN": "5877410604225924969",
    "LIST_TOKENS": "6204104220694550861",
    "TOKEN_INFO": "4956561910792192697",
    "REMOVE_TOKEN": "4958534924278694938",
    "ENABLE_TOKEN": "4956721670690702265",
    "STATS": "6206343625232619150",
    "REFRESH": "6005843436479975944",
    "BACK": "5888484185261216745",
    "CANCEL": "6206396878532121864",
    "ADMIN": "4958725487682650920",
    "OTP_BUTTON": "6206420230269310869",   # ← প্যানেলের জন্য যোগ
    "GREEN_CIRCLE": "5188234920639632382",
    "RED_CIRCLE": "6206141323683042874",
    "CLOCK": "5436207838181471199",
    "ROCKET": "5337127177500510090",
    "GAMEPAD": "5319133596697524570",
    "WELCOME_SPARKLE": "5363992034728229166",
    "CHECK_MARK": "4956721670690702265",
}

def get_custom_emoji(key):
    return CUSTOM_EMOJIS.get(key, "")

# ================= প্যানেল বাটন (শুধু টেক্সট + আইকন) =================
def panel_button(text, callback, emoji_key, style=None):
    return InlineKeyboardButton(
        text=text,
        callback_data=callback,
        style=style,
        icon_custom_emoji_id=get_custom_emoji(emoji_key)
    )

# ================= সকল দেশ (পুরো ম্যাপ) =================
COUNTRY_CODE_MAP = {
    "1": ("US", "🇺🇸", "USA"),
    "7": ("RU", "🇷🇺", "RUSSIA"),
    "20": ("EG", "🇪🇬", "EGYPT"),
    "27": ("ZA", "🇿🇦", "SOUTH AFRICA"),
    "30": ("GR", "🇬🇷", "GREECE"),
    "31": ("NL", "🇳🇱", "NETHERLANDS"),
    "33": ("FR", "🇫🇷", "FRANCE"),
    "34": ("ES", "🇪🇸", "SPAIN"),
    "39": ("IT", "🇮🇹", "ITALY"),
    "40": ("RO", "🇷🇴", "ROMANIA"),
    "41": ("CH", "🇨🇭", "SWITZERLAND"),
    "43": ("AT", "🇦🇹", "AUSTRIA"),
    "44": ("GB", "🇬🇧", "UNITED KINGDOM"),
    "46": ("SE", "🇸🇪", "SWEDEN"),
    "48": ("PL", "🇵🇱", "POLAND"),
    "49": ("DE", "🇩🇪", "GERMANY"),
    "51": ("PE", "🇵🇪", "PERU"),
    "52": ("MX", "🇲🇽", "MEXICO"),
    "54": ("AR", "🇦🇷", "ARGENTINA"),
    "55": ("BR", "🇧🇷", "BRAZIL"),
    "56": ("CL", "🇨🇱", "CHILE"),
    "57": ("CO", "🇨🇴", "COLOMBIA"),
    "58": ("VE", "🇻🇪", "VENEZUELA"),
    "60": ("MY", "🇲🇾", "MALAYSIA"),
    "62": ("ID", "🇮🇩", "INDONESIA"),
    "63": ("PH", "🇵🇭", "PHILIPPINES"),
    "66": ("TH", "🇹🇭", "THAILAND"),
    "81": ("JP", "🇯🇵", "JAPAN"),
    "82": ("KR", "🇰🇷", "SOUTH KOREA"),
    "84": ("VN", "🇻🇳", "VIETNAM"),
    "86": ("CN", "🇨🇳", "CHINA"),
    "90": ("TR", "🇹🇷", "TURKEY"),
    "91": ("IN", "🇮🇳", "INDIA"),
    "92": ("PK", "🇵🇰", "PAKISTAN"),
    "93": ("AF", "🇦🇫", "AFGHANISTAN"),
    "94": ("LK", "🇱🇰", "SRI LANKA"),
    "95": ("MM", "🇲🇲", "MYANMAR"),
    "98": ("IR", "🇮🇷", "IRAN"),
    "211": ("SS", "🇸🇸", "SOUTH SUDAN"),
    "212": ("MA", "🇲🇦", "MOROCCO"),
    "213": ("DZ", "🇩🇿", "ALGERIA"),
    "216": ("TN", "🇹🇳", "TUNISIA"),
    "218": ("LY", "🇱🇾", "LIBYA"),
    "220": ("GM", "🇬🇲", "GAMBIA"),
    "221": ("SN", "🇸🇳", "SENEGAL"),
    "222": ("MR", "🇲🇷", "MAURITANIA"),
    "223": ("ML", "🇲🇱", "MALI"),
    "224": ("GN", "🇬🇳", "GUINEA"),
    "225": ("CI", "🇨🇮", "IVORY COAST"),
    "226": ("BF", "🇧🇫", "BURKINA FASO"),
    "227": ("NE", "🇳🇪", "NIGER"),
    "228": ("TG", "🇹🇬", "TOGO"),
    "229": ("BJ", "🇧🇯", "BENIN"),
    "230": ("MU", "🇲🇺", "MAURITIUS"),
    "231": ("LR", "🇱🇷", "LIBERIA"),
    "232": ("SL", "🇸🇱", "SIERRA LEONE"),
    "233": ("GH", "🇬🇭", "GHANA"),
    "234": ("NG", "🇳🇬", "NIGERIA"),
    "235": ("TD", "🇹🇩", "CHAD"),
    "236": ("CF", "🇨🇫", "CENTRAL AFRICAN REPUBLIC"),
    "237": ("CM", "🇨🇲", "CAMEROON"),
    "238": ("CV", "🇨🇻", "CAPE VERDE"),
    "239": ("ST", "🇸🇹", "SAO TOME AND PRINCIPE"),
    "240": ("GQ", "🇬🇶", "EQUATORIAL GUINEA"),
    "241": ("GA", "🇬🇦", "GABON"),
    "242": ("CG", "🇨🇬", "CONGO"),
    "243": ("CD", "🇨🇩", "DR CONGO"),
    "244": ("AO", "🇦🇴", "ANGOLA"),
    "245": ("GW", "🇬🇼", "GUINEA-BISSAU"),
    "246": ("IO", "🇮🇴", "BRITISH INDIAN OCEAN TERRITORY"),
    "248": ("SC", "🇸🇨", "SEYCHELLES"),
    "249": ("SD", "🇸🇩", "SUDAN"),
    "250": ("RW", "🇷🇼", "RWANDA"),
    "251": ("ET", "🇪🇹", "ETHIOPIA"),
    "252": ("SO", "🇸🇴", "SOMALIA"),
    "253": ("DJ", "🇩🇯", "DJIBOUTI"),
    "254": ("KE", "🇰🇪", "KENYA"),
    "255": ("TZ", "🇹🇿", "TANZANIA"),
    "256": ("UG", "🇺🇬", "UGANDA"),
    "257": ("BI", "🇧🇮", "BURUNDI"),
    "258": ("MZ", "🇲🇿", "MOZAMBIQUE"),
    "260": ("ZM", "🇿🇲", "ZAMBIA"),
    "261": ("MG", "🇲🇬", "MADAGASCAR"),
    "262": ("RE", "🇷🇪", "REUNION"),
    "263": ("ZW", "🇿🇼", "ZIMBABWE"),
    "264": ("NA", "🇳🇦", "NAMIBIA"),
    "265": ("MW", "🇲🇼", "MALAWI"),
    "266": ("LS", "🇱🇸", "LESOTHO"),
    "267": ("BW", "🇧🇼", "BOTSWANA"),
    "268": ("SZ", "🇸🇿", "ESWATINI"),
    "269": ("KM", "🇰🇲", "COMOROS"),
    "290": ("SH", "🇸🇭", "SAINT HELENA"),
    "291": ("ER", "🇪🇷", "ERITREA"),
    "297": ("AW", "🇦🇼", "ARUBA"),
    "298": ("FO", "🇫🇴", "FAROE ISLANDS"),
    "299": ("GL", "🇬🇱", "GREENLAND"),
    "350": ("GI", "🇬🇮", "GIBRALTAR"),
    "351": ("PT", "🇵🇹", "PORTUGAL"),
    "352": ("LU", "🇱🇺", "LUXEMBOURG"),
    "353": ("IE", "🇮🇪", "IRELAND"),
    "354": ("IS", "🇮🇸", "ICELAND"),
    "355": ("AL", "🇦🇱", "ALBANIA"),
    "356": ("MT", "🇲🇹", "MALTA"),
    "357": ("CY", "🇨🇾", "CYPRUS"),
    "358": ("FI", "🇫🇮", "FINLAND"),
    "359": ("BG", "🇧🇬", "BULGARIA"),
    "370": ("LT", "🇱🇹", "LITHUANIA"),
    "371": ("LV", "🇱🇻", "LATVIA"),
    "372": ("EE", "🇪🇪", "ESTONIA"),
    "373": ("MD", "🇲🇩", "MOLDOVA"),
    "374": ("AM", "🇦🇲", "ARMENIA"),
    "375": ("BY", "🇧🇾", "BELARUS"),
    "376": ("AD", "🇦🇩", "ANDORRA"),
    "377": ("MC", "🇲🇨", "MONACO"),
    "378": ("SM", "🇸🇲", "SAN MARINO"),
    "380": ("UA", "🇺🇦", "UKRAINE"),
    "381": ("RS", "🇷🇸", "SERBIA"),
    "382": ("ME", "🇲🇪", "MONTENEGRO"),
    "383": ("XK", "🇽🇰", "KOSOVO"),
    "385": ("HR", "🇭🇷", "CROATIA"),
    "386": ("SI", "🇸🇮", "SLOVENIA"),
    "387": ("BA", "🇧🇦", "BOSNIA AND HERZEGOVINA"),
    "389": ("MK", "🇲🇰", "NORTH MACEDONIA"),
    "420": ("CZ", "🇨🇿", "CZECH REPUBLIC"),
    "421": ("SK", "🇸🇰", "SLOVAKIA"),
    "423": ("LI", "🇱🇮", "LIECHTENSTEIN"),
    "500": ("FK", "🇫🇰", "FALKLAND ISLANDS"),
    "501": ("BZ", "🇧🇿", "BELIZE"),
    "502": ("GT", "🇬🇹", "GUATEMALA"),
    "503": ("SV", "🇸🇻", "EL SALVADOR"),
    "504": ("HN", "🇭🇳", "HONDURAS"),
    "505": ("NI", "🇳🇮", "NICARAGUA"),
    "506": ("CR", "🇨🇷", "COSTA RICA"),
    "507": ("PA", "🇵🇦", "PANAMA"),
    "509": ("HT", "🇭🇹", "HAITI"),
    "590": ("GP", "🇬🇵", "GUADELOUPE"),
    "591": ("BO", "🇧🇴", "BOLIVIA"),
    "592": ("GY", "🇬🇾", "GUYANA"),
    "593": ("EC", "🇪🇨", "ECUADOR"),
    "594": ("GF", "🇬🇫", "FRENCH GUIANA"),
    "595": ("PY", "🇵🇾", "PARAGUAY"),
    "596": ("MQ", "🇲🇶", "MARTINIQUE"),
    "597": ("SR", "🇸🇷", "SURINAME"),
    "598": ("UY", "🇺🇾", "URUGUAY"),
    "599": ("BQ", "🇧🇶", "CARIBBEAN NETHERLANDS"),
    "880": ("BD", "🇧🇩", "BANGLADESH"),
    "960": ("MV", "🇲🇻", "MALDIVES"),
    "961": ("LB", "🇱🇧", "LEBANON"),
    "962": ("JO", "🇯🇴", "JORDAN"),
    "963": ("SY", "🇸🇾", "SYRIA"),
    "964": ("IQ", "🇮🇶", "IRAQ"),
    "965": ("KW", "🇰🇼", "KUWAIT"),
    "966": ("SA", "🇸🇦", "SAUDI ARABIA"),
    "967": ("YE", "🇾🇪", "YEMEN"),
    "968": ("OM", "🇴🇲", "OMAN"),
    "970": ("PS", "🇵🇸", "PALESTINE"),
    "971": ("AE", "🇦🇪", "UAE"),
    "972": ("IL", "🇮🇱", "ISRAEL"),
    "973": ("BH", "🇧🇭", "BAHRAIN"),
    "974": ("QA", "🇶🇦", "QATAR"),
    "975": ("BT", "🇧🇹", "BHUTAN"),
    "976": ("MN", "🇲🇳", "MONGOLIA"),
    "977": ("NP", "🇳🇵", "NEPAL"),
    "992": ("TJ", "🇹🇯", "TAJIKISTAN"),
    "993": ("TM", "🇹🇲", "TURKMENISTAN"),
    "994": ("AZ", "🇦🇿", "AZERBAIJAN"),
    "995": ("GE", "🇬🇪", "GEORGIA"),
    "996": ("KG", "🇰🇬", "KYRGYZSTAN"),
    "998": ("UZ", "🇺🇿", "UZBEKISTAN"),
}

ISO_TO_INFO = {iso: (flag, name) for iso, flag, name in COUNTRY_CODE_MAP.values()}
NAME_TO_ISO = {}
for code, (iso, flag, name) in COUNTRY_CODE_MAP.items():
    NAME_TO_ISO[name.lower()] = iso
    if name.lower() == "united kingdom":
        NAME_TO_ISO["uk"] = "GB"
        NAME_TO_ISO["gb"] = "GB"

def get_country_code(country_name):
    return NAME_TO_ISO.get(country_name.lower(), "")

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
    conn.commit()
    conn.close()

def is_duplicate(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM messages WHERE id=?", (msg_id,))
    return c.fetchone() is not None

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

def get_otps_by_number(number, limit=50):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT otp, timestamp, service, country, country_code, full_message FROM messages WHERE number=? ORDER BY timestamp DESC LIMIT ?",
        (number, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_otp_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    count = c.fetchone()[0]
    conn.close()
    return count

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

def get_all_tokens():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM api_tokens ORDER BY created_at DESC")
    return [dict(row) for row in c.fetchall()]

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

# ================= OTP ডিটেক্ট (পুরনো) =================
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

# ================= স্ক্র্যাপার (পুরনো) =================
def solve_captcha(text):
    match = re.search(r"(\d+)\s*\+\s*(\d+)", text)
    return int(match.group(1)) + int(match.group(2)) if match else None

async def login_and_save_state(page):
    logger.info("🌐 Opening login page...")
    await page.goto(LOGIN_URL, wait_until="networkidle")
    await page.wait_for_timeout(2000)
    logger.info("✍️ Filling credentials...")
    await page.locator("input[type='text']").first.fill(USERNAME)
    await page.locator("input[type='password']").fill(PASSWORD)
    logger.info("🧩 Solving captcha...")
    captcha_text = await page.locator("body").inner_text()
    answer = solve_captcha(captcha_text)
    if answer is None:
        raise Exception("Captcha not found")
    logger.info(f"✅ Captcha: {answer}")
    await page.locator("input").last.fill(str(answer))
    logger.info("🚀 Clicking login...")
    await page.locator("button").click()
    await page.wait_for_timeout(5000)
    if "login" in page.url.lower():
        raise Exception("Login failed")
    await page.context.storage_state(path=COOKIE_FILE)
    logger.info("🍪 Cookies saved")

async def create_context(browser):
    if os.path.exists(COOKIE_FILE):
        logger.info("🍪 Loading saved session...")
        return await browser.new_context(storage_state=COOKIE_FILE)
    else:
        logger.info("🔑 No session – fresh context.")
        return await browser.new_context()

async def ensure_logged_in(context, browser):
    page = await context.new_page()
    try:
        logger.info("🔍 Checking session on SMS page...")
        await page.goto(STATS_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            logger.warning("⚠️ Session expired – re‑logging in...")
            await context.close()
            new_context = await browser.new_context()
            new_page = await new_context.new_page()
            await login_and_save_state(new_page)
            await new_page.close()
            return await browser.new_context(storage_state=COOKIE_FILE)
        else:
            logger.info("✅ Session valid.")
            return context
    finally:
        await page.close()

async def scrape_sms_stats(context):
    page = await context.new_page()
    try:
        logger.info("📊 Navigating to SMS CDR Stats...")
        await page.goto(STATS_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        if "login" in page.url.lower():
            logger.error("❌ Redirected to login.")
            return None

        logger.info("⏳ Waiting for AJAX data...")
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
        logger.info("✅ AJAX data loaded.")
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.select_one('table.dataTable tbody')
        if not table:
            logger.error("❌ Table body not found.")
            return []

        rows = table.find_all('tr')
        logger.info(f"📊 Found {len(rows)} rows.")
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

# ================= OTP মেসেজ তৈরি (পুরনো EMOJI + ডিফল্ট ইমোজি) =================
def build_otp_message(entry):
    # প্রিফিক্স
    prefix = f'<tg-emoji emoji-id="{EMOJI["PREFIX"]}">🤖</tg-emoji>'
    # সেপারেটর
    separator = f'<tg-emoji emoji-id="{EMOJI["SEPARATOR"]}">➖</tg-emoji>'

    # দেশের তথ্য
    country_raw = entry.get("country", "Unknown")
    iso = get_country_code(country_raw)
    if iso and iso in ISO_TO_INFO:
        flag = ISO_TO_INFO[iso][0]
        country_name = ISO_TO_INFO[iso][1]
    else:
        flag = "🏳"
        country_name = country_raw.upper()

    # দেশের ইমোজি (ডিফল্ট ইমোজি থেকে)
    country_emoji_id = None
    if iso and iso.lower() in DEFAULT_EMOJIS["countries"]:
        country_emoji_id = DEFAULT_EMOJIS["countries"][iso.lower()]
    elif country_raw.lower() in DEFAULT_EMOJIS["countries"]:
        country_emoji_id = DEFAULT_EMOJIS["countries"][country_raw.lower()]

    if country_emoji_id:
        country_display = f'<tg-emoji emoji-id="{country_emoji_id}">{flag}</tg-emoji><b>{iso or country_raw.upper()}</b>'
    else:
        # কাস্টম ইমোজি না থাকলে সাধারণ ফ্ল্যাগ ব্যবহার
        country_display = f'{flag}<b>{iso or country_raw.upper()}</b>'

    # সার্ভিসের তথ্য
    service_name = entry.get("service", "Unknown").lower()
    service_display = f'<b>{service_name.capitalize()}</b>'
    if service_name in DEFAULT_EMOJIS["services"]:
        service_emoji_id = DEFAULT_EMOJIS["services"][service_name]
        service_display = f'<tg-emoji emoji-id="{service_emoji_id}">🔧</tg-emoji>'
    else:
        # ডিফল্ট ইমোজি না থাকলে #service_name
        service_display = f'#{service_name.capitalize()}'

    # মাস্কড নাম্বার
    number = entry.get("number", "")
    prefix_num, suffix_num = format_number(number)
    masked_number = f'<b>+{prefix_num}{separator}{suffix_num}</b>'

    # পুরো টেক্সট
    text = f"{prefix} {country_display} | {service_display} {masked_number}"

    # বাটন
    otp_btn = InlineKeyboardButton(
        "𝐎𝐓𝐏",
        copy_text=CopyTextButton(text=entry["otp"]),
        style=KBS.SUCCESS,
        icon_custom_emoji_id=EMOJI["OTP_BUTTON"]
    )
    channel_btn = InlineKeyboardButton(
        "𝐂𝐇𝐀𝐍𝐍𝐄𝐋", url=CHANNEL_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=EMOJI["CHANNEL_BUTTON"]
    )
    bot_btn = InlineKeyboardButton(
        "𝐁𝐎𝐓", url=BOT_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=EMOJI["BOT_BUTTON"]
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
        return jsonify({"status": "error", "error": "missing_token", "message": "Token required"}), 400
    if not number:
        return jsonify({"status": "error", "error": "missing_number", "message": "Number required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1 or info["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return jsonify({"status": "error", "error": "invalid_token", "message": "Invalid or expired token"}), 401
    otps = get_otps_by_number(number)
    if not otps:
        return jsonify({"status": "not_found", "data": {"number": number, "total_otps": 0, "otps": []}, "Sms": "No OTPs found"})
    formatted = []
    for o in otps:
        formatted.append({
            "otp": o["otp"],
            "timestamp": o["timestamp"],
            "service": o["service"],
            "country": o["country"],
            "country_code": o.get("country_code", ""),
            "message": o["full_message"]
        })
    return jsonify({
        "status": "success",
        "data": {"number": number, "total_otps": len(formatted), "otps": formatted},
        "Sms": f"Found {len(formatted)} OTPs"
    })

@api_app.route('/latest_otp', methods=['GET'])
def latest_otp_api():
    token = request.args.get('token')
    number = request.args.get('number')
    if not token or not number:
        return jsonify({"status": "error", "message": "Token and number required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1:
        return jsonify({"status": "error", "message": "Invalid token"}), 401
    otps = get_otps_by_number(number, limit=1)
    if not otps:
        return jsonify({"status": "not_found", "data": {"number": number, "otp": None}, "Sms": "No OTP found"})
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
            "message": o["full_message"]
        },
        "Sms": "OTP found successfully"
    })

@api_app.route('/stats', methods=['GET'])
def api_stats():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "message": "Token required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1:
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
    info = get_token_info(token)
    if not info:
        return jsonify({"status": "error", "error": "invalid_token", "message": "Invalid token"}), 401
    is_valid = info["is_active"] == 1 and info["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({
        "status": "success",
        "data": {
            "token": token,
            "is_valid": is_valid,
            "name": info["name"],
            "expires_at": info["expires_at"],
            "is_active": bool(info["is_active"])
        }
    })

def start_api_server():
    api_app.run(host="0.0.0.0", port=API_PORT, debug=False, use_reloader=False)

# ================= মনিটর লুপ =================
async def monitor_loop(application):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    context = await create_context(browser)
    context = await ensure_logged_in(context, browser)

    while True:
        try:
            context = await ensure_logged_in(context, browser)
            data = await scrape_sms_stats(context)
            if data is None:
                logger.error("Scraping failed, retrying...")
                await asyncio.sleep(10)
                continue
            new_count = 0
            for entry in data:
                if is_duplicate(entry["id"]):
                    continue
                text, keyboard = build_otp_message(entry)
                try:
                    await application.bot.send_message(
                        chat_id=GROUP_ID,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    save_message(
                        entry["id"],
                        entry["number"],
                        entry["otp"],
                        entry["service"],
                        entry["country"],
                        entry.get("country_code", ""),
                        entry["date"],
                        entry["sms"]
                    )
                    new_count += 1
                    logger.info(f"✅ Sent OTP: {entry['otp']} for {entry['number']}")
                except Exception as e:
                    logger.error(f"Send error: {e}")
            if new_count:
                logger.info(f"📤 Sent {new_count} new OTPs.")
            else:
                logger.debug("No new OTPs.")
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

# ----- প্যানেল (শুধু কাস্টম ইমোজি, কোনো সাধারণ ইমোজি নয়) -----
@admin_only
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [panel_button("New Token", "new_token", "NEW_TOKEN", KBS.PRIMARY)],
        [panel_button("List Tokens", "list_tokens", "LIST_TOKENS")],
        [panel_button("Token Info", "token_info", "TOKEN_INFO")],
        [panel_button("Remove Token", "remove_token", "REMOVE_TOKEN", KBS.DANGER)],
        [panel_button("Enable Token", "enable_token", "ENABLE_TOKEN", KBS.SUCCESS)],
        [panel_button("Stats", "stats", "STATS")],
        [panel_button("Refresh", "refresh_panel", "REFRESH")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # প্যানেলের মেসেজ – সব জায়গায় কাস্টম ইমোজি
    admin_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["ADMIN"]}">🤖</tg-emoji>'
    stats_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["STATS"]}">📊</tg-emoji>'
    green_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'
    red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">🔴</tg-emoji>'
    otp_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["OTP_BUTTON"]}">🔑</tg-emoji>'

    text = (
        f"{admin_emoji} <b>API Management Panel</b>\n\n"
        f"{stats_emoji} Total Tokens: <b>{get_token_count()}</b>\n"
        f"{green_emoji} Active: <b>{get_active_count()}</b>\n"
        f"{red_emoji} Inactive: <b>{get_inactive_count()}</b>\n"
        f"{otp_emoji} Total OTPs: <b>{get_otp_count()}</b>"
    )

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

# ----- নিউ টোকেন মেনু -----
@admin_only
async def new_token_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [panel_button("7 Days", "new_token_7", "CLOCK", KBS.PRIMARY)],
        [panel_button("30 Days", "new_token_30", "ROCKET", KBS.PRIMARY)],
        [panel_button("90 Days", "new_token_90", "GAMEPAD", KBS.PRIMARY)],
        [panel_button("Custom Date", "new_token_custom", "WELCOME_SPARKLE", KBS.PRIMARY)],
        [panel_button("Back", "panel", "BACK", KBS.SECONDARY)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    new_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["NEW_TOKEN"]}">➕</tg-emoji>'
    text = f"{new_emoji} <b>Create New Token</b>\n\nChoose expiry duration:"

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

# ----- টোকেন তৈরি (ক্যালব্যাক) -----
@admin_only
async def create_token_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days_map = {"new_token_7": 7, "new_token_30": 30, "new_token_90": 90}
    if query.data in days_map:
        days = days_map[query.data]
        token, created, expires = create_token(f"Token_{datetime.now().strftime('%Y%m%d')}", days)

        check_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CHECK_MARK"]}">✅</tg-emoji>'
        info_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["TOKEN_INFO"]}">ℹ️</tg-emoji>'
        admin_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["ADMIN"]}">🔑</tg-emoji>'
        clock_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CLOCK"]}">📅</tg-emoji>'
        green_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'

        text = (
            f"{check_emoji} <b>New API token created!</b>\n\n"
            f"{info_emoji} Name: <code>Token_{datetime.now().strftime('%Y%m%d')}</code>\n"
            f"{admin_emoji} Token: <code>{token}</code>\n"
            f"{clock_emoji} Created: {created}\n"
            f"{clock_emoji} Expires: {expires}\n"
            f"{green_emoji} Status: Active\n\n"
            f"{admin_emoji} Usage:\n"
            f"<code>/get_otp?number=NUMBER&token={token}</code>"
        )
        keyboard = [[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    elif query.data == "new_token_custom":
        context.user_data["awaiting_custom_token"] = True
        sparkle_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["WELCOME_SPARKLE"]}">✨</tg-emoji>'
        text = (
            f"{sparkle_emoji} <b>Create Token with Custom Date</b>\n\n"
            "Send: <code>Name|YYYY-MM-DD</code>\nExample: <code>MyApp|2026-12-31</code>"
        )
        keyboard = [[panel_button("Cancel", "panel", "CANCEL", KBS.DANGER)]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ----- কাস্টম টোকেন (টেক্সট ইনপুট) -----
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

        check_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CHECK_MARK"]}">✅</tg-emoji>'
        info_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["TOKEN_INFO"]}">ℹ️</tg-emoji>'
        admin_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["ADMIN"]}">🔑</tg-emoji>'
        clock_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CLOCK"]}">📅</tg-emoji>'
        green_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'

        msg = (
            f"{check_emoji} <b>New API token created!</b>\n\n"
            f"{info_emoji} Name: <code>{name}</code>\n"
            f"{admin_emoji} Token: <code>{token}</code>\n"
            f"{clock_emoji} Created: {created}\n"
            f"{clock_emoji} Expires: {expires}\n"
            f"{green_emoji} Status: Active\n\n"
            f"{admin_emoji} Usage:\n"
            f"<code>/get_otp?number=NUMBER&token={token}</code>"
        )
        keyboard = [[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except ValueError:
        red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">❌</tg-emoji>'
        await update.message.reply_text(
            f"{red_emoji} Invalid date format. Use YYYY-MM-DD",
            parse_mode="HTML"
        )

# ----- টোকেন তালিকা -----
@admin_only
async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens = get_all_tokens()
    if not tokens:
        red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">⚠️</tg-emoji>'
        await query.edit_message_text(
            f"{red_emoji} No tokens found.",
            reply_markup=InlineKeyboardMarkup([[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]])
        )
        return

    list_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["LIST_TOKENS"]}">📋</tg-emoji>'
    text = f"{list_emoji} <b>API Tokens ({len(tokens)} total)</b>\n\n"
    for i, t in enumerate(tokens[:10], 1):
        green = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'
        red = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">🔴</tg-emoji>'
        status = green if t["is_active"] == 1 and t["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else red
        text += f"{status} #{i}: <b>{t['name']}</b>\n"
        text += f"<code>{t['token'][:12]}...</code>\n"
        text += f"📅 Expires: {t['expires_at']}\n\n"
    keyboard = [[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ----- টোকেন তথ্য -----
@admin_only
async def token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_token_info"] = True
    info_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["TOKEN_INFO"]}">ℹ️</tg-emoji>'
    text = f"{info_emoji} Send the token you want info about."
    keyboard = [[panel_button("Cancel", "panel", "CANCEL", KBS.DANGER)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_token_info"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_token_info"] = False
    info = get_token_info(token)
    if not info:
        red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">❌</tg-emoji>'
        await update.message.reply_text(f"{red_emoji} Token not found.", parse_mode="HTML")
        return

    info_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["TOKEN_INFO"]}">ℹ️</tg-emoji>'
    green = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'
    red = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">🔴</tg-emoji>'
    status = green if info["is_active"] == 1 and info["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else red

    text = (
        f"{info_emoji} <b>Token Information</b>\n\n"
        f"🏷️ Name: <b>{info['name']}</b>\n"
        f"🔑 Token: <code>{info['token']}</code>\n"
        f"📊 Status: {status}\n"
        f"📅 Created: {info['created_at']}\n"
        f"⏰ Expires: {info['expires_at']}\n"
        f"👤 Created by: {info['created_by']}"
    )
    keyboard = [[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ----- টোকেন রিমুভ (ডেঞ্জার) -----
@admin_only
async def remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_remove_token"] = True
    remove_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["REMOVE_TOKEN"]}">❌</tg-emoji>'
    text = f"{remove_emoji} <b>Send the token you want to deactivate.</b>\n\n⚠️ This action can be undone with Enable Token."
    keyboard = [[panel_button("Cancel", "panel", "CANCEL", KBS.SECONDARY)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_remove_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_remove_token"] = False
    info = get_token_info(token)
    if not info:
        red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">❌</tg-emoji>'
        await update.message.reply_text(f"{red_emoji} Token not found.", parse_mode="HTML")
        return
    deactivate_token(token)
    check_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CHECK_MARK"]}">✅</tg-emoji>'
    await update.message.reply_text(
        f"{check_emoji} Token <code>{token[:12]}...</code> deactivated.",
        parse_mode="HTML"
    )

# ----- টোকেন এনেবল (সাকসেস) -----
@admin_only
async def enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_enable_token"] = True
    enable_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["ENABLE_TOKEN"]}">✅</tg-emoji>'
    text = f"{enable_emoji} Send the token you want to reactivate."
    keyboard = [[panel_button("Cancel", "panel", "CANCEL", KBS.DANGER)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_enable_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_enable_token"] = False
    info = get_token_info(token)
    if not info:
        red_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">❌</tg-emoji>'
        await update.message.reply_text(f"{red_emoji} Token not found.", parse_mode="HTML")
        return
    activate_token(token)
    check_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["CHECK_MARK"]}">✅</tg-emoji>'
    await update.message.reply_text(
        f"{check_emoji} Token <code>{token[:12]}...</code> reactivated.",
        parse_mode="HTML"
    )

# ----- স্ট্যাটাস -----
@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stats_emoji = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["STATS"]}">📊</tg-emoji>'
    green = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["GREEN_CIRCLE"]}">🟢</tg-emoji>'
    red = f'<tg-emoji emoji-id="{CUSTOM_EMOJIS["RED_CIRCLE"]}">🔴</tg-emoji>'
    text = (
        f"{stats_emoji} <b>Bot Statistics</b>\n\n"
        f"📈 Total OTPs: <b>{get_otp_count()}</b>\n"
        f"🔑 Total Tokens: <b>{get_token_count()}</b>\n"
        f"{green} Active: <b>{get_active_count()}</b>\n"
        f"{red} Inactive: <b>{get_inactive_count()}</b>"
    )
    keyboard = [[panel_button("Back", "panel", "BACK", KBS.SECONDARY)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ----- রিফ্রেশ -----
@admin_only
async def refresh_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await panel(update, context)

# ---- সাধারণ ইউজারদের জন্য কিছুই না ----
async def ignore_non_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return

# ================= মেইন =================
def main():
    init_db()
    threading.Thread(target=start_api_server, daemon=True).start()
    logger.info(f"🌐 API Server running on http://0.0.0.0:{API_PORT}")

    application = Application.builder().token(BOT_TOKEN).build()

    # অ্যাডমিন কমান্ড
    application.add_handler(CommandHandler("panel", panel))
    application.add_handler(CommandHandler("start", panel))
    application.add_handler(CommandHandler("stats", stats_command))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(new_token_menu, pattern="^new_token$"))
    application.add_handler(CallbackQueryHandler(create_token_callback, pattern="^new_token_(7|30|90|custom)$"))
    application.add_handler(CallbackQueryHandler(list_tokens, pattern="^list_tokens$"))
    application.add_handler(CallbackQueryHandler(token_info, pattern="^token_info$"))
    application.add_handler(CallbackQueryHandler(remove_token, pattern="^remove_token$"))
    application.add_handler(CallbackQueryHandler(enable_token, pattern="^enable_token$"))
    application.add_handler(CallbackQueryHandler(stats_command, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(refresh_panel, pattern="^refresh_panel$"))
    application.add_handler(CallbackQueryHandler(panel, pattern="^panel$"))

    # টেক্সট ইনপুট (শুধু অ্যাডমিন)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enable_token))

    # সাধারণ ইউজারদের ইগনোর
    application.add_handler(MessageHandler(filters.ALL, ignore_non_admin), group=1)

    loop = asyncio.get_event_loop()
    loop.create_task(monitor_loop(application))

    logger.info("🚀 Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
