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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ================= LOGGING (Only Emoji - No API Call Log) =================
logging.getLogger("telegram").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("apscheduler").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

logging.basicConfig(
    format="%(asctime)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= FOLDER =================
DATA_FOLDER = "ISM_PANEL_DATA"
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

COOKIE_FILE = os.path.join(DATA_FOLDER, "cookies.json")
DB_FILE = os.path.join(DATA_FOLDER, "otp.db")
JSON_FILE = os.path.join(DATA_FOLDER, "otp_log.json")

# ================= CONFIG (UPDATED) =================
BOT_TOKEN = "8901961818:AAFbhaZIoY13b1nmcuhLOoBpK0M9zgFUJgs"   # নতুন টোকেন
ADMIN_IDS = [8744359777]

LOGIN_URL = "http://139.99.9.120/ints/login"
STATS_URL = "http://139.99.9.120/ints/client/SMSCDRStats"
USERNAME = "otp_work_rakesh"
PASSWORD = "otp_work_rakesh"

API_PORT = 6080
REFRESH_INTERVAL = 4  # seconds

# ================= FULL COUNTRY MAP (unchanged) =================
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

ISO_TO_INFO = {}
for code, val in COUNTRY_CODE_MAP.items():
    if len(val) >= 3:
        iso, flag, name = val[0], val[1], val[2]
        ISO_TO_INFO[iso] = (flag, name)

NAME_TO_ISO = {}
for code, val in COUNTRY_CODE_MAP.items():
    if len(val) >= 3:
        iso = val[0]
        name = val[2].lower()
        NAME_TO_ISO[name] = iso
        if name == "united kingdom":
            NAME_TO_ISO["uk"] = "GB"
            NAME_TO_ISO["gb"] = "GB"
        elif name == "united states":
            NAME_TO_ISO["us"] = "US"
        elif name == "united arab emirates":
            NAME_TO_ISO["uae"] = "AE"
        elif name == "south korea":
            NAME_TO_ISO["kr"] = "KR"

def get_country_code(country_name):
    if not country_name:
        return ""
    lower = country_name.lower()
    if lower in NAME_TO_ISO:
        return NAME_TO_ISO[lower]
    clean = re.sub(r'[^a-zA-Z]', '', lower)
    for key in NAME_TO_ISO:
        if clean in key or key in clean:
            return NAME_TO_ISO[key]
    return ""

# ================= DATABASE =================
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
    c.execute("PRAGMA table_info(messages)")
    columns = [col[1] for col in c.fetchall()]
    if "full_message" not in columns:
        c.execute("ALTER TABLE messages ADD COLUMN full_message TEXT")
    if "country_code" not in columns:
        c.execute("ALTER TABLE messages ADD COLUMN country_code TEXT")

    c.execute('''CREATE TABLE IF NOT EXISTS api_tokens (
        token TEXT PRIMARY KEY,
        name TEXT,
        created_by INTEGER,
        created_at TEXT,
        expires_at TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    conn.commit()
    c.execute("SELECT token FROM api_tokens WHERE token='test_token_123'")
    if not c.fetchone():
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO api_tokens (token, name, created_by, created_at, expires_at, is_active) VALUES (?,?,?,?,?,1)",
            ("test_token_123", "TestToken", ADMIN_IDS[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry)
        )
        logger.info("🔑 Test token created.")
    conn.commit()
    conn.close()

def is_duplicate(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM messages WHERE id=?", (msg_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

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

def get_all_otps(limit=50):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT number, otp, service, country, country_code, timestamp, full_message FROM messages ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_otp_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    return c.fetchone()[0]

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

# ================= JSON LOG =================
def append_to_json_log(entry):
    try:
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []
        if not isinstance(data, list):
            data = []
        data.append(entry)
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ JSON write failed: {e}")

# ================= OTP EXTRACTION =================
def extract_otp_from_sms(sms_text):
    if not sms_text:
        return None
    text = ' '.join(sms_text.split())
    patterns = [
        (r'(?:code|otp|pin|verification|auth|security code|one[- ]time|password)\s*(?:is\s*)?[:;.]?\s*#?\s*(\d{4,8})', None),
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
        "PayPal": [r'paypal'],
        "Binance": [r'binance'],
        "Netflix": [r'netflix'],
        "Amex": [r'amex'],
        "KUICK": [r'kuick'],
        "Telkom": [r'telkom'],
        "ISM": [r'ism'],
    }
    for srv, pats in patterns.items():
        for p in pats:
            if re.search(p, msg_l):
                return srv
    return "UNKNOWN"

# ================= COOKIE-BASED LOGIN & SCRAPE =================
async def login_and_save_cookie(playwright):
    """শুধুমাত্র প্রথমবার বা কুকি এক্সপায়ার হলে লগইন করে কুকি সেভ করে (headless)"""
    browser = await playwright.chromium.launch(
        headless=True,   # <-- headless mode on (no GUI)
        slow_mo=0,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context()
    page = await context.new_page()

    logger.info("🌐 Opening login page...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)

    logger.info("✍️ Filling credentials...")
    await page.locator("input[type='text']").first.fill(USERNAME)
    await page.locator("input[type='password']").fill(PASSWORD)

    logger.info("🧩 Solving captcha...")
    captcha_text = await page.locator("body").inner_text()
    match = re.search(r"(\d+)\s*\+\s*(\d+)", captcha_text)
    if not match:
        logger.error("❌ Captcha not found")
        await browser.close()
        return False
    answer = int(match.group(1)) + int(match.group(2))
    logger.info(f"✅ Captcha answer: {answer}")
    await page.locator("input").last.fill(str(answer))

    logger.info("🚀 Clicking login button...")
    await page.locator("button").click()
    await page.wait_for_timeout(5000)

    if "login" in page.url.lower():
        logger.error("❌ Login failed – still on login page")
        await browser.close()
        return False

    logger.info("✅ Login successful!")
    await context.storage_state(path=COOKIE_FILE)
    logger.info(f"🍪 Cookies saved to {COOKIE_FILE}")
    await browser.close()
    return True

async def load_stats_with_cookie(playwright):
    """কুকি দিয়ে পেজ লোড (headless)"""
    if not os.path.exists(COOKIE_FILE):
        logger.warning("⚠️ Cookie file not found")
        return False, None

    browser = await playwright.chromium.launch(
        headless=True,   # <-- headless mode
        slow_mo=0,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(storage_state=COOKIE_FILE)
    page = await context.new_page()

    try:
        logger.info("🔄 Loading Stats page with cookie...")
        await page.goto(STATS_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1000)

        # Wait for data rows (date pattern)
        try:
            await page.wait_for_function(
                """() => {
                    const rows = document.querySelectorAll('table.dataTable tbody tr');
                    for (let row of rows) {
                        const firstCell = row.querySelector('td');
                        if (firstCell) {
                            const text = firstCell.innerText.trim();
                            if (/^\\d{4}-\\d{2}-\\d{2}/.test(text)) {
                                return true;
                            }
                        }
                    }
                    return false;
                }""",
                timeout=10000,
                polling=200
            )
            logger.info("✅ Data rows loaded.")
        except Exception as e:
            logger.warning(f"⏳ Data rows not found within timeout: {e}")

        # Scrape data
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.select_one('table.dataTable tbody')
        if not table:
            logger.warning("⚠️ Table body not found")
            await browser.close()
            return False, None

        rows = table.find_all('tr')
        results = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 9:
                continue
            first = cols[0].get_text(strip=True)
            if re.match(r'^[\d,]+$', first) or "Total" in first:
                continue
            date = cols[0].get_text(strip=True)
            range_val = cols[1].get_text(strip=True)
            number = cols[2].get_text(strip=True)
            cli = cols[3].get_text(strip=True)
            client = cols[4].get_text(strip=True)
            sms = cols[5].get_text(strip=True)

            country = range_val
            country_code = get_country_code(country)

            otp = extract_otp_from_sms(sms)
            if not otp:
                continue

            service = "UNKNOWN"
            if cli and cli.strip() and cli.upper() not in ["UNKNOWN", "SERVICE", ""]:
                service = cli.strip()
            elif client and client.strip() and client.upper() not in ["UNKNOWN", "SERVICE", ""]:
                service = client.strip().lstrip('#')
            else:
                service = detect_service_from_sms(sms)

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

        await browser.close()
        return True, results

    except Exception as e:
        logger.error(f"❌ Error loading with cookie: {e}")
        try:
            if "login" in page.url.lower():
                logger.warning("⚠️ Redirected to login – cookie expired")
        except:
            pass
        await browser.close()
        return False, None

# ================= MONITOR LOOP (headless) =================
async def monitor_loop(application):
    playwright = await async_playwright().start()

    # First login if no cookie
    if not os.path.exists(COOKIE_FILE):
        logger.info("🔑 First-time login – creating cookie...")
        success = await login_and_save_cookie(playwright)
        if not success:
            logger.error("❌ Initial login failed. Exiting monitor loop.")
            return

    consecutive_failures = 0

    while True:
        try:
            success, data = await load_stats_with_cookie(playwright)

            if success and data is not None:
                consecutive_failures = 0
                new_count = 0
                for entry in data:
                    if is_duplicate(entry["id"]):
                        continue
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
                    append_to_json_log({
                        "id": entry["id"],
                        "number": entry["number"],
                        "otp": entry["otp"],
                        "service": entry["service"],
                        "country": entry["country"],
                        "country_code": entry.get("country_code", ""),
                        "timestamp": entry["date"],
                        "full_message": entry["sms"]
                    })
                    new_count += 1
                    logger.info(f"💾 New OTP stored: {entry['otp']} for {entry['number']}")
                if new_count:
                    logger.info(f"📤 Total {new_count} new OTPs stored.")
                else:
                    logger.debug("🔄 No new OTPs.")
            else:
                consecutive_failures += 1
                logger.warning(f"⚠️ Cookie load failed ({consecutive_failures} consecutive)")

                if consecutive_failures >= 2:
                    logger.info("🔄 Re-login triggered...")
                    if os.path.exists(COOKIE_FILE):
                        os.remove(COOKIE_FILE)
                    success = await login_and_save_cookie(playwright)
                    if success:
                        logger.info("✅ New cookie created.")
                        consecutive_failures = 0
                    else:
                        logger.error("❌ Re-login failed. Will retry later.")

        except Exception as e:
            logger.error(f"❌ Monitor loop error: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                logger.warning("⚠️ Too many errors, attempting to recreate cookie...")
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)
                await login_and_save_cookie(playwright)
                consecutive_failures = 0

        await asyncio.sleep(REFRESH_INTERVAL)

# ================= API SERVER =================
api_app = Flask(__name__)

@api_app.route('/get_otp', methods=['GET'])
def get_otp_api():
    token = request.args.get('token')
    number = request.args.get('number')
    if not token or not number:
        return jsonify({"status": "error", "message": "Token and number required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1 or info["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return jsonify({"status": "error", "error": "invalid_token"}), 401
    otps = get_otps_by_number(number)
    if not otps:
        return jsonify({"status": "not_found", "data": {"number": number, "total_otps": 0, "otps": []}})
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
    return jsonify({"status": "success", "data": {"number": number, "total_otps": len(formatted), "otps": formatted}})

@api_app.route('/latest_otp', methods=['GET'])
def latest_otp_api():
    token = request.args.get('token')
    number = request.args.get('number')
    if not token or not number:
        return jsonify({"status": "error", "message": "Token and number required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1:
        return jsonify({"status": "error", "error": "invalid_token"}), 401
    otps = get_otps_by_number(number, limit=1)
    if not otps:
        return jsonify({"status": "not_found", "data": {"number": number, "otp": None}})
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
        }
    })

@api_app.route('/all_otp', methods=['GET'])
def all_otp_api():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "error": "missing_token", "message": "Token required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1 or info["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return jsonify({"status": "error", "error": "invalid_token", "message": "Invalid or expired token"}), 401
    try:
        rows = get_all_otps(50)
        if not rows:
            return jsonify({"status": "success", "Sms": "No OTPs found", "data": {"total": 0, "otps": []}})
        formatted = []
        for row in rows:
            formatted.append({
                "number": row.get("number", ""),
                "otp": row.get("otp", ""),
                "timestamp": row.get("timestamp", ""),
                "service": row.get("service", "UNKNOWN"),
                "country": row.get("country", "Unknown"),
                "country_code": row.get("country_code", ""),
                "message": row.get("full_message", "")
            })
        return jsonify({
            "status": "success",
            "Sms": f"Found {len(formatted)} recent OTPs",
            "data": {"total": len(formatted), "otps": formatted}
        })
    except Exception as e:
        logger.error(f"❌ Error in /all_otp: {e}")
        return jsonify({"status": "error", "error": "internal_error", "message": str(e)}), 500

@api_app.route('/stats', methods=['GET'])
def api_stats():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "message": "Token required"}), 400
    info = get_token_info(token)
    if not info or info["is_active"] != 1:
        return jsonify({"status": "error", "error": "invalid_token"}), 401
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
        return jsonify({"status": "error", "error": "missing_token"}), 400
    info = get_token_info(token)
    if not info:
        return jsonify({"status": "error", "error": "invalid_token"}), 401
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

# ================= TELEGRAM HANDLERS (unchanged) =================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            return
        return await func(update, context)
    return wrapper

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>OTP Bot Active</b>\n\n"
        "📌 <b>Commands:</b>\n"
        "/panel - Open API Management Panel\n"
        "/stats - View bot statistics",
        parse_mode="HTML"
    )

@admin_only
async def stats_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"📈 Total OTPs: <b>{get_otp_count()}</b>\n"
        f"🔑 Total Tokens: <b>{get_token_count()}</b>\n"
        f"🟢 Active: <b>{get_active_count()}</b>\n"
        f"🔴 Inactive: <b>{get_inactive_count()}</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

@admin_only
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        send_func = update.message.reply_text
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        send_func = query.edit_message_text
    else:
        return

    keyboard = [
        [InlineKeyboardButton("➕ New Token", callback_data="new_token")],
        [InlineKeyboardButton("📋 List Tokens", callback_data="list_tokens")],
        [InlineKeyboardButton("ℹ️ Token Info", callback_data="token_info")],
        [InlineKeyboardButton("❌ Remove Token", callback_data="remove_token")],
        [InlineKeyboardButton("✅ Enable Token", callback_data="enable_token")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"🤖 <b>API Management Panel</b>\n\n"
        f"📊 Total Tokens: <b>{get_token_count()}</b>\n"
        f"🟢 Active: <b>{get_active_count()}</b>\n"
        f"🔴 Inactive: <b>{get_inactive_count()}</b>\n"
        f"🔑 Total OTPs: <b>{get_otp_count()}</b>"
    )
    await send_func(text, reply_markup=reply_markup, parse_mode="HTML")

@admin_only
async def new_token_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⏰ 7 Days", callback_data="new_token_7")],
        [InlineKeyboardButton("🚀 30 Days", callback_data="new_token_30")],
        [InlineKeyboardButton("🎮 90 Days", callback_data="new_token_90")],
        [InlineKeyboardButton("✨ Custom Date", callback_data="new_token_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "➕ <b>Create New Token</b>\n\nChoose expiry duration:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

@admin_only
async def create_token_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        if query.data.startswith("new_token_"):
            days_map = {"7": 7, "30": 30, "90": 90}
            if query.data in ["new_token_7", "new_token_30", "new_token_90"]:
                days = days_map[query.data.split("_")[2]]
                token, created, expires = create_token(f"Token_{datetime.now().strftime('%Y%m%d')}", days)
                msg = (
                    f"✅ <b>New API token created!</b>\n\n"
                    f"ℹ️ Name: <code>Token_{datetime.now().strftime('%Y%m%d')}</code>\n"
                    f"🔑 Token: <code>{token}</code>\n"
                    f"📅 Created: {created}\n"
                    f"⏰ Expires: {expires}\n"
                    f"🟢 Status: Active\n\n"
                    f"📌 Usage:\n"
                    f"<code>/get_otp?number=NUMBER&token={token}</code>"
                )
                await query.message.reply_text(msg, parse_mode="HTML")
                await query.edit_message_text(
                    "✅ Token created successfully! Check the new message above.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel")]])
                )
            elif query.data == "new_token_custom":
                context.user_data["awaiting_custom_token"] = True
                text = "✨ <b>Create Token with Custom Date</b>\n\nSend: <code>Name|YYYY-MM-DD</code>\nExample: <code>MyApp|2026-12-31</code>"
                keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="panel")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Error in create_token_callback: {e}")
        await query.message.reply_text("❌ Failed to create token. Please try again.", parse_mode="HTML")

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
            f"✅ <b>New API token created!</b>\n\n"
            f"ℹ️ Name: <code>{name}</code>\n"
            f"🔑 Token: <code>{token}</code>\n"
            f"📅 Created: {created}\n"
            f"⏰ Expires: {expires}\n"
            f"🟢 Status: Active\n\n"
            f"📌 Usage:\n"
            f"<code>/get_otp?number=NUMBER&token={token}</code>"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        await update.message.reply_text("✅ Token created! You can see it in the list.", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD", parse_mode="HTML")

@admin_only
async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens = get_all_tokens()
    if not tokens:
        await query.edit_message_text(
            "⚠️ No tokens found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel")]])
        )
        return
    text = f"📋 <b>API Tokens ({len(tokens)} total)</b>\n\n"
    for i, t in enumerate(tokens[:10], 1):
        status = "🟢" if t["is_active"] == 1 and t["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else "🔴"
        text += f"{status} #{i}: <b>{t['name']}</b>\n"
        text += f"<code>{t['token'][:12]}...</code>\n"
        text += f"📅 Expires: {t['expires_at']}\n\n"
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_token_info"] = True
    text = "ℹ️ Send the token you want info about."
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_token_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_token_info"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_token_info"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text("❌ Token not found.", parse_mode="HTML")
        return
    status = "🟢" if info["is_active"] == 1 and info["expires_at"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S") else "🔴"
    text = (
        f"ℹ️ <b>Token Information</b>\n\n"
        f"🏷️ Name: <b>{info['name']}</b>\n"
        f"🔑 Token: <code>{info['token']}</code>\n"
        f"📊 Status: {status}\n"
        f"📅 Created: {info['created_at']}\n"
        f"⏰ Expires: {info['expires_at']}\n"
        f"👤 Created by: {info['created_by']}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="panel")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_remove_token"] = True
    text = "❌ <b>Send the token you want to deactivate.</b>\n\n⚠️ This action can be undone with Enable Token."
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_remove_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_remove_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_remove_token"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text("❌ Token not found.", parse_mode="HTML")
        return
    deactivate_token(token)
    await update.message.reply_text(f"✅ Token <code>{token[:12]}...</code> deactivated.", parse_mode="HTML")

@admin_only
async def enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_enable_token"] = True
    text = "✅ Send the token you want to reactivate."
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def handle_enable_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_enable_token"):
        return
    token = update.message.text.strip()
    context.user_data["awaiting_enable_token"] = False
    info = get_token_info(token)
    if not info:
        await update.message.reply_text("❌ Token not found.", parse_mode="HTML")
        return
    activate_token(token)
    await update.message.reply_text(f"✅ Token <code>{token[:12]}...</code> reactivated.", parse_mode="HTML")

@admin_only
async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"📈 Total OTPs: <b>{get_otp_count()}</b>\n"
        f"🔑 Total Tokens: <b>{get_token_count()}</b>\n"
        f"🟢 Active: <b>{get_active_count()}</b>\n"
        f"🔴 Inactive: <b>{get_inactive_count()}</b>"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

@admin_only
async def refresh_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await panel(update, context)

async def ignore_non_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return

# ================= MAIN =================
def main():
    init_db()
    threading.Thread(target=start_api_server, daemon=True).start()
    logger.info("🌐 API Server running on http://0.0.0.0:5000")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("panel", panel))
    application.add_handler(CommandHandler("stats", stats_text))

    application.add_handler(CallbackQueryHandler(new_token_menu, pattern="^new_token$"))
    application.add_handler(CallbackQueryHandler(create_token_callback, pattern="^new_token_(7|30|90|custom)$"))
    application.add_handler(CallbackQueryHandler(list_tokens, pattern="^list_tokens$"))
    application.add_handler(CallbackQueryHandler(token_info, pattern="^token_info$"))
    application.add_handler(CallbackQueryHandler(remove_token, pattern="^remove_token$"))
    application.add_handler(CallbackQueryHandler(enable_token, pattern="^enable_token$"))
    application.add_handler(CallbackQueryHandler(stats_callback, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(refresh_panel, pattern="^refresh_panel$"))
    application.add_handler(CallbackQueryHandler(panel, pattern="^panel$"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_token))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enable_token))

    application.add_handler(MessageHandler(filters.ALL, ignore_non_admin), group=1)

    loop = asyncio.get_event_loop()
    loop.create_task(monitor_loop(application))

    logger.info("🚀 Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
