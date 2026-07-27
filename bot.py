# bot.py — SR NUMBER HUB (Complete Final – Group OTP Fix & All Features)

import asyncio, json, os, re, sqlite3, threading, tempfile, zipfile, shutil
from datetime import datetime, timedelta

import requests
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, Update, CopyTextButton,
    CallbackQuery
)
from telegram.constants import KeyboardButtonStyle as KBS
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)
from telegram.error import BadRequest

from emoji import CUSTOM_EMOJIS

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8666689980:AAGju2ULiLUA0oCrEdaqsh2Mi6zVNU4ZAL4"
ADMIN_IDS = [8744359777]

OTP_GROUP_URL = "https://t.me/RgxOtp"
OTP_API_URL = "http://127.0.0.1:5080/all_otp"
OTP_API_TOKEN = "46c78242c14e02f41ac5e0799122c36f"
OTP_POLL_INTERVAL = 1  # seconds

MIN_WITHDRAW = 0.1  # USD

# Admin contacts
ADMIN_WHATSAPP = "https://wa.me/8801962636806"
ADMIN_TELEGRAM = "t.me/SR_ADMIN_RAKESH"

# Second admin contacts (fill later)
ADMIN2_WHATSAPP = ""
ADMIN2_TELEGRAM = ""

# Group OTP settings
GROUP_ID = -1004380384761
CHANNEL_URL = "https://t.me/+76nQ1vvAzy04ZWE0"
BOT_URL = "https://t.me/SrNumberHubBOT"

# Emoji constants for group OTP (from your reference bot)
EMOJI_PREFIX = "4958725487682650920"
EMOJI_SEPARATOR = "6307542847251814164"
EMOJI_OTP_BUTTON = "6206420230269310869"
EMOJI_CHANNEL_BUTTON = "6204010762206189094"
EMOJI_BOT_BUTTON = "5339267587337370029"

# ==================== DATABASE FOLDER ====================
DB_DIR = "NUMBER-PANEL-DATA"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "mrisbrand_master.db")

# ==================== DATABASE SETUP ====================
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
db_lock = threading.Lock()
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
              joined_date TEXT, last_active TEXT,
              current_number_id INTEGER DEFAULT NULL,
              current_number TEXT DEFAULT NULL, current_country TEXT DEFAULT NULL,
              current_service TEXT DEFAULT NULL, number_expiry TEXT DEFAULT NULL,
              last_menu_message_id INTEGER DEFAULT NULL,
              remove_cc INTEGER DEFAULT 0,
              banned INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS numbers
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number TEXT,
              country TEXT, service TEXT, assigned_date TEXT, status TEXT DEFAULT 'active',
              expiry_time TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS otps
             (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, otp TEXT,
              message TEXT, timestamp TEXT, forwarded INTEGER DEFAULT 0, user_id INTEGER)''')

c.execute('''CREATE TABLE IF NOT EXISTS countries
             (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, service TEXT,
              flag TEXT, active INTEGER DEFAULT 1, stock INTEGER DEFAULT 0)''')

c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_countries_name_service ON countries(name, service)")

c.execute('''CREATE TABLE IF NOT EXISTS available_numbers
             (id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT, service TEXT,
              number TEXT, used INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS used_numbers
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number TEXT,
              country TEXT, service TEXT, assigned_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS services
             (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE,
              display_name TEXT, active INTEGER DEFAULT 1, emoji_id TEXT DEFAULT '')''')

c.execute('''CREATE TABLE IF NOT EXISTS admins
             (user_id INTEGER PRIMARY KEY)''')
c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (8744359777)")

c.execute('''CREATE TABLE IF NOT EXISTS group_emojis
             (type TEXT, key TEXT, emoji_id TEXT, PRIMARY KEY(type, key))''')

# Add missing columns
try:
    c.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE users ADD COLUMN withdrawn REAL DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE users ADD COLUMN total_otp INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE users ADD COLUMN remove_cc INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE services ADD COLUMN emoji_id TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass

default_services = ["WhatsApp", "Telegram", "Facebook", "IMO", "Google", "Tinder", "Uber", "Instagram", "Twitter", "Snapchat"]
for service in default_services:
    c.execute("INSERT OR IGNORE INTO services (name, display_name, active, emoji_id) VALUES (?, ?, 1, '')", (service, service))

conn.commit()
print("✅ Database setup completed")

# ==================== STATE TRACKING ====================
admin_mode = {}
admin_panel_state = {}
admin_temp_data = {}
last_activation_data = {}
user_manager_state = {}

def safe_url(url: str) -> str | None:
    if url and isinstance(url, str) and (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        return url
    return None

def safe_icon(emoji_id: str) -> str | None:
    if emoji_id and isinstance(emoji_id, str) and emoji_id.isdigit() and len(emoji_id) > 9:
        return emoji_id
    return None

def parse_payout(payout_str: str) -> float:
    if not payout_str:
        return 0.001
    return float(payout_str.replace('$', '').strip())

# ==================== LOAD COUNTRIES FROM JSON ====================
def load_countries_db():
    try:
        with open('countries.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for name, info in data.items():
                if "emoji_id" not in info:
                    info["emoji_id"] = ""
                if "payout" not in info:
                    info["payout"] = "0.001$"
                if "iso" not in info:
                    info["iso"] = name[:2].upper()
            return data
    except FileNotFoundError:
        default = {
            "Pakistan": {"code": "+92", "iso": "PK", "payout": "0.001$", "emoji_id": ""},
            "India": {"code": "+91", "iso": "IN", "payout": "0.001$", "emoji_id": ""},
            "Venezuela": {"code": "+58", "iso": "VE", "payout": "0.001$", "emoji_id": ""},
            "Nigeria": {"code": "+234", "iso": "NG", "payout": "0.001$", "emoji_id": ""},
        }
        with open('countries.json', 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=2, ensure_ascii=False)
        return default

def save_countries_db(data):
    with open('countries.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

COUNTRIES_DATA = load_countries_db()

def get_country_info(country_name):
    return COUNTRIES_DATA.get(country_name, {"emoji_id": "", "payout": "0.001$", "iso": country_name[:2].upper()})

# ==================== DEFAULT EMOJIS ====================
DEFAULT_EMOJIS = {
    "services": {
        "uber": "5298715455316303708",
        "bolt": "5343587658717219067",
        "whatsapp": "5298715455316303708",
        "telegram": "5339267587337370029",
        "casushi": "5346008706012169915",
        "paypal": "",
        "google": "",
        "facebook": "",
        "instagram": "",
        "amazon": "",
        "netflix": "",
        "twitter": "",
        "discord": "",
        "snapchat": "",
    },
    "countries": {
        "gb": "5293993521026453119",
        "af": "5292108962391414885",
        "us": "",
        "in": "",
        "pk": "",
        "bd": "",
        "ng": "",
        "ve": "",
    }
}

# ==================== CUSTOM EMOJI HTML HELPER ====================
def emoji_tag(emoji_id: str, fallback: str = " ") -> str:
    if not emoji_id or not emoji_id.isdigit() or len(emoji_id) < 10:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def country_flag_emoji(country_name: str) -> str:
    eid = get_country_info(country_name).get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
    return emoji_tag(eid, "🏁")

def service_emoji_tag(service_name: str) -> str:
    row = db_fetch_one("SELECT emoji_id FROM services WHERE LOWER(name) = LOWER(?)", (service_name,))
    eid = row[0] if row and row[0] else CUSTOM_EMOJIS.get("DEFAULT_SERVICE", "")
    return emoji_tag(eid, "⚙️")

# ==================== KEYBOARD BUILDERS ====================
BTN_GET_NUMBER = "Get Number"
BTN_BALANCE = "Balance"
BTN_SUPPORT = "Support"
BTN_ADMIN = "Admin Panel"

def bottom_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(BTN_GET_NUMBER, style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("GET_NUMBER", ""))),
            KeyboardButton(BTN_BALANCE, style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon("5312123810638483121")),
        ],
        [
            KeyboardButton(BTN_SUPPORT, style=KBS.SUCCESS, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("SUPPORT", "")))
        ],
    ]
    if is_admin(user_id):
        rows.append([KeyboardButton(BTN_ADMIN, style=KBS.DANGER, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("ADMIN", "")))])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True,
                               input_field_placeholder="Choose an option...")

def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Get Number", callback_data="menu_get_number", style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("GET_NUMBER", ""))),
            InlineKeyboardButton("Balance", callback_data="menu_balance", style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon("5312123810638483121")),
        ],
        [
            InlineKeyboardButton("Support", callback_data="menu_support", style=KBS.SUCCESS, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("SUPPORT", ""))),
        ],
    ] + ([
        [InlineKeyboardButton("Admin Panel", callback_data="menu_admin", style=KBS.DANGER, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("ADMIN", "")))],
    ] if is_admin(user_id) else []))

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Back to Main Menu", callback_data="back_to_menu", style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", ""))),
    ]])

def number_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("New Number", callback_data="next_number", style=KBS.SUCCESS, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("NEW_NUMBER", ""))),
            InlineKeyboardButton("Change Service", callback_data="back_to_services", style=KBS.SUCCESS, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("CHANGE_COUNTRY", ""))),
        ],
        [
            InlineKeyboardButton("OTP Group", url=OTP_GROUP_URL, style=KBS.DANGER, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("JOIN_OTP_GROUP", ""))),
        ],
        [
            InlineKeyboardButton("Home", callback_data="back_to_menu", style=KBS.PRIMARY, icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("HOME", ""))),
        ],
    ])

def services_keyboard() -> InlineKeyboardMarkup:
    services = db_fetch_all("SELECT name, display_name, emoji_id FROM services WHERE active = 1 ORDER BY name")
    if not services:
        return back_to_main_keyboard()
    rows = []
    row = []
    for s in services:
        btn = InlineKeyboardButton(
            text=s[1],
            callback_data=f"svc_sel|{s[0]}",
            style=KBS.PRIMARY,
            icon_custom_emoji_id=safe_icon(s[2]) if s[2] else None
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Back to Main Menu", callback_data="back_to_menu", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    return InlineKeyboardMarkup(rows)

def countries_for_service_keyboard(service: str) -> InlineKeyboardMarkup:
    countries = db_fetch_all(
        "SELECT name, stock FROM countries WHERE service = ? AND active = 1 AND stock > 0 ORDER BY name",
        (service,)
    )
    if not countries:
        return back_to_main_keyboard()
    rows = []
    for name, stock in countries:
        info = get_country_info(name)
        flag_eid = info.get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
        payout = info.get("payout", "0.001$")
        label = f"{name} — {payout} — ({stock})"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=f"cnt_sel|{name}|{service}",
            style=KBS.SUCCESS,
            icon_custom_emoji_id=safe_icon(flag_eid)
        )])
    rows.append([InlineKeyboardButton("Back to Services", callback_data="menu_get_number", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    return InlineKeyboardMarkup(rows)

def support_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    if ADMIN_WHATSAPP:
        buttons.append(InlineKeyboardButton("Admin WH", url=ADMIN_WHATSAPP, style=KBS.SUCCESS,
                                            icon_custom_emoji_id=safe_icon("5334998226636390258")))
    if ADMIN_TELEGRAM:
        buttons.append(InlineKeyboardButton("Admin TG", url=ADMIN_TELEGRAM, style=KBS.PRIMARY,
                                            icon_custom_emoji_id=safe_icon("5330237710655306682")))
    if ADMIN2_WHATSAPP:
        buttons.append(InlineKeyboardButton("Admin2 WH", url=ADMIN2_WHATSAPP, style=KBS.SUCCESS,
                                            icon_custom_emoji_id=safe_icon("5334998226636390258")))
    if ADMIN2_TELEGRAM:
        buttons.append(InlineKeyboardButton("Admin2 TG", url=ADMIN2_TELEGRAM, style=KBS.PRIMARY,
                                            icon_custom_emoji_id=safe_icon("5330237710655306682")))
    if not buttons:
        buttons = [InlineKeyboardButton("No support available", callback_data="noop")]
    return InlineKeyboardMarkup([buttons])

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("User Manager", callback_data="admin_user_manager", style=KBS.PRIMARY,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("USER_MANAGER", ""))),
            InlineKeyboardButton("Upload Stock", callback_data="admin_upload", style=KBS.SUCCESS,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("UPLOAD", ""))),
        ],
        [
            InlineKeyboardButton("Delete Stock", callback_data="admin_delete", style=KBS.DANGER,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", ""))),
            InlineKeyboardButton("Broadcast", callback_data="admin_broadcast", style=KBS.PRIMARY,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BROADCAST", ""))),
        ],
        [
            InlineKeyboardButton("Give Account", callback_data="admin_giveaway", style=KBS.SUCCESS,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("GIVEAWAY", ""))),
            InlineKeyboardButton("Country Manager", callback_data="admin_country_manager", style=KBS.PRIMARY,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("COUNTRY_MANAGER", ""))),
        ],
        [
            InlineKeyboardButton("Service Manager", callback_data="admin_service_manager", style=KBS.PRIMARY,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("SERVICE_MANAGER", ""))),
            InlineKeyboardButton("Exit Admin", callback_data="admin_exit", style=KBS.DANGER,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("EXIT", ""))),
        ],
        [
            InlineKeyboardButton("Database", callback_data="admin_database", style=KBS.SUCCESS,
                                 icon_custom_emoji_id=safe_icon("6206236607532504295")),
            InlineKeyboardButton("Back to Main Menu", callback_data="back_to_menu", style=KBS.PRIMARY,
                                 icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", ""))),
        ],
    ])

def admin_back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Back to Admin Panel", callback_data="admin_back", style=KBS.PRIMARY,
                             icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", ""))),
    ]])

def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Cancel", callback_data="admin_back", style=KBS.DANGER,
                             icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("CANCEL", ""))),
    ]])

# ==================== DATABASE HELPERS (SYNC) ====================
def db_exec(query, params=()):
    with db_lock:
        c.execute(query, params)
        conn.commit()

def db_fetch_one(query, params=()):
    with db_lock:
        c.execute(query, params)
        return c.fetchone()

def db_fetch_all(query, params=()):
    with db_lock:
        c.execute(query, params)
        return c.fetchall()

def ensure_user(user_id, username, first_name):
    db_exec('''INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date, last_active)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def extract_country_from_filename(filename):
    try:
        name = filename.replace('.txt', '')
        if '_' in name:
            country_part = name.split('_')[0].strip()
        else:
            country_part = name.strip()
        for country_name in COUNTRIES_DATA.keys():
            if country_name.lower() == country_part.lower():
                return country_name
        for country_name in COUNTRIES_DATA.keys():
            if country_part.lower().startswith(country_name.lower()) or country_name.lower().startswith(country_part.lower()):
                return country_name
        for country_name in COUNTRIES_DATA.keys():
            if country_name.lower() in country_part.lower() or country_part.lower() in country_name.lower():
                return country_name
        return country_part
    except Exception:
        return None

def extract_service_from_filename(filename):
    try:
        name = filename.replace('.txt', '').lower()
        if '_' in name:
            service_part = name.split('_', 1)[1].strip()
        else:
            return "Unknown"
        services = db_fetch_all("SELECT name FROM services WHERE active = 1")
        for service in services:
            if service[0].lower() in service_part:
                return service[0]
        return service_part
    except Exception:
        return "Unknown"

def load_numbers_from_file(file_path, filename):
    try:
        country = extract_country_from_filename(filename)
        service = extract_service_from_filename(filename)
        if not country:
            return 0, None, None
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            numbers = file.read().strip().split('\n')
        valid_numbers = []
        for num in numbers:
            num = num.strip()
            if num:
                if not num.startswith('+'):
                    num = '+' + num
                valid_numbers.append(num)
        if not valid_numbers:
            return 0, None, None
        with db_lock:
            for number in valid_numbers:
                c.execute('''INSERT INTO available_numbers (country, service, number)
                             VALUES (?, ?, ?)''', (country, service, number))
            c.execute('''INSERT OR IGNORE INTO countries (name, service, flag, stock)
                         VALUES (?, ?, ?, 0)''', (country, service, country))
            c.execute("SELECT stock FROM countries WHERE name = ? AND service = ?", (country, service))
            current = c.fetchone()
            current_stock = current[0] if current else 0
            c.execute('''UPDATE countries SET stock = ?, active = 1
                         WHERE name = ? AND service = ?''',
                      (current_stock + len(valid_numbers), country, service))
            conn.commit()
        return len(valid_numbers), country, service
    except Exception as e:
        print(f"Error loading file: {e}")
        return 0, None, None

def delete_country_stock(country, service):
    try:
        db_exec("DELETE FROM available_numbers WHERE country = ? AND service = ?", (country, service))
        db_exec("DELETE FROM countries WHERE name = ? AND service = ?", (country, service))
        return True
    except Exception as e:
        print(f"Error deleting stock: {e}")
        return False

def get_numbers_from_stock(country, service, count=3):
    try:
        with db_lock:
            c.execute('''SELECT COUNT(*) FROM available_numbers
                         WHERE country = ? AND service = ? AND used = 0''', (country, service))
            available = c.fetchone()
            if not available or available[0] == 0:
                return []
            take = min(count, available[0])
            c.execute('''SELECT id, number FROM available_numbers
                         WHERE country = ? AND service = ? AND used = 0
                         ORDER BY id ASC LIMIT ?''', (country, service, take))
            results = c.fetchall()
            if not results:
                return []
            numbers = []
            for num_id, number in results:
                c.execute("UPDATE available_numbers SET used = 1 WHERE id = ?", (num_id,))
                numbers.append(number)
            c.execute('''UPDATE countries SET stock = (
                            SELECT COUNT(*) FROM available_numbers 
                            WHERE country = ? AND service = ? AND used = 0
                         ) WHERE name = ? AND service = ?''', 
                      (country, service, country, service))
            conn.commit()
            return numbers
    except Exception as e:
        print(f"Error getting numbers: {e}")
        return []

def format_numbers_message(country, service, numbers, user_id=None, first_name=None):
    if first_name is None:
        first_name = "User"
    remove_cc = 0
    if user_id:
        row = db_fetch_one("SELECT remove_cc FROM users WHERE user_id = ?", (user_id,))
        if row:
            remove_cc = row[0] or 0

    flag_eid = get_country_info(country).get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
    country_code = get_country_info(country).get("code", "")

    message = (
        f'{emoji_tag("5462908885356549237", "📱")} <b>THIS IS YOUR</b> '
        f'{service_emoji_tag(service)} {country_flag_emoji(country)} '
        f'<b>ACTIVATED NUMBERS</b>{emoji_tag("5462908885356549237", "📱")}\n\n'
    )
    rows = []
    for number in numbers:
        display_num = number
        copy_num = number
        if remove_cc == 1 and country_code and number.startswith(country_code):
            display_num = number[len(country_code):]
            copy_num = display_num
        rows.append([InlineKeyboardButton(
            text=display_num,
            copy_text=CopyTextButton(text=copy_num),
            style=KBS.PRIMARY,
            icon_custom_emoji_id=safe_icon(flag_eid)
        )])

    if remove_cc == 1:
        cc_button = InlineKeyboardButton("ADD CC", callback_data="toggle_cc",
                                         style=KBS.SUCCESS,
                                         icon_custom_emoji_id=safe_icon("4956507094124594921"))
    else:
        cc_button = InlineKeyboardButton("REMOVE CC", callback_data="toggle_cc",
                                         style=KBS.DANGER,
                                         icon_custom_emoji_id=safe_icon("4956337889593000947"))
    rows.append([cc_button])

    new_style = KBS.DANGER if remove_cc == 1 else KBS.SUCCESS
    change_style = KBS.DANGER if remove_cc == 1 else KBS.SUCCESS
    rows.append([
        InlineKeyboardButton("New Number", callback_data="next_number", style=new_style,
                             icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("NEW_NUMBER", ""))),
        InlineKeyboardButton("Change Service", callback_data="back_to_services", style=change_style,
                             icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("CHANGE_COUNTRY", ""))),
    ])
    otp_style = KBS.PRIMARY if remove_cc == 1 else KBS.DANGER
    rows.append([
        InlineKeyboardButton("OTP Group", url=OTP_GROUP_URL, style=otp_style,
                             icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("JOIN_OTP_GROUP", ""))),
    ])
    return message, InlineKeyboardMarkup(rows)

def stock_added_message(country, service, count):
    flag_eid = get_country_info(country).get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
    svc_eid_row = db_fetch_one("SELECT emoji_id FROM services WHERE name = ?", (service,))
    svc_eid = svc_eid_row[0] if svc_eid_row and svc_eid_row[0] else CUSTOM_EMOJIS.get("DEFAULT_SERVICE", "")
    return (
        f'{emoji_tag("4958617898751886363", "📊")} <b>STOCK</b> {emoji_tag("5463412319948148591", "📦")} <b>ADDED SUCCESSFULLY</b> {emoji_tag("4956721670690702265", "✅")}\n\n'
        f'<b>NUMBER</b> {emoji_tag("6204108584381322968", "📱")} : <b>{count}</b>\n'
        f'<b>COUNTRY</b> {emoji_tag("5188540541922480562", "🌍")} : {emoji_tag(flag_eid, "🏁")}\n'
        f'<b>SERVICE</b> {emoji_tag("5465590345108589516", "🔧")} : {emoji_tag(svc_eid, "⚙️")}'
    )

def stock_added_broadcast(country, service, count):
    flag_eid = get_country_info(country).get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
    svc_eid_row = db_fetch_one("SELECT emoji_id FROM services WHERE name = ?", (service,))
    svc_eid = svc_eid_row[0] if svc_eid_row and svc_eid_row[0] else CUSTOM_EMOJIS.get("DEFAULT_SERVICE", "")
    return (
        f'{emoji_tag("4958617898751886363", "📊")} <b>STOCK</b> {emoji_tag("5463412319948148591", "📦")} <b>ADDED SUCCESSFULLY</b> {emoji_tag("4956721670690702265", "✅")}\n\n'
        f'<b>NUMBER</b> {emoji_tag("6204108584381322968", "📱")} : <b>{count}</b>\n'
        f'<b>COUNTRY</b> {emoji_tag("5188540541922480562", "🌍")} : {emoji_tag(flag_eid, "🏁")}\n'
        f'<b>SERVICE</b> {emoji_tag("5465590345108589516", "🔧")} : {emoji_tag(svc_eid, "⚙️")}'
    )

# ==================== WELCOME HTML ====================
def welcome_html(user_id, first_name):
    spark = CUSTOM_EMOJIS.get("WELCOME_SPARKLE", "")
    rocket = CUSTOM_EMOJIS.get("ROCKET", "")
    id_icon = CUSTOM_EMOJIS.get("ID_ICON", "")
    check = CUSTOM_EMOJIS.get("CHECK_MARK", "")
    gamepad = CUSTOM_EMOJIS.get("GAMEPAD", "")
    return (
        f'{emoji_tag(spark, "✨")} Welcome to SR NUMBER HUB, {first_name}! {emoji_tag(spark, "✨")}\n\n'
        f'{emoji_tag(rocket, "🚀")} Your Premium Platform for Virtual Numbers.\n\n'
        f'{emoji_tag(id_icon, "🆔")} Your ID: <code>{user_id}</code>\n'
        f'{emoji_tag(check, "✅")} You are a Verified Member!\n\n'
        f'{emoji_tag(gamepad, "🎮")} Tap a button below to navigate.\n\n'
        '━━━━━━━━━━━━━━━━━━━━\n'
        '👨‍💻 Developer: SR NUMBER HUB'
    )

# ==================== /start COMMAND ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await ban_check(update, context):
        return
    username = update.effective_user.username
    first_name = update.effective_user.first_name or "User"
    ensure_user(user_id, username, first_name)
    db_exec("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    await update.message.reply_text(welcome_html(user_id, first_name), reply_markup=bottom_menu_keyboard(user_id), parse_mode='HTML')

# ==================== BAN CHECK ====================
async def ban_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    banned = db_fetch_one("SELECT banned FROM users WHERE user_id=?", (user_id,))
    if banned and banned[0]:
        text = (
            f'{emoji_tag("6206077285720659346", "🚫")} <b>Now You Can\'t Use Me</b> {emoji_tag("6206003549722122915", "😢")}\n'
            f'{emoji_tag("6206267591426578467", "📞")} <b>CONTACT TO SUPPORT ADMINS</b> {emoji_tag("6206319341487527808", "👨‍💼")}'
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=support_keyboard(), parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=support_keyboard(), parse_mode='HTML')
        return True
    return False

# ==================== ADMIN CHECK ====================
def is_admin(user_id):
    return db_fetch_one("SELECT user_id FROM admins WHERE user_id=?", (user_id,)) is not None

# ==================== SAFE EDIT ====================
async def safe_edit_message(query, text, **kwargs):
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

# ==================== REPLY OR EDIT (FIXED) ====================
async def reply_or_edit(target, text: str, reply_markup=None, parse_mode=None):
    if isinstance(target, CallbackQuery):
        await safe_edit_message(target, text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif hasattr(target, 'callback_query') and target.callback_query:
        await safe_edit_message(target.callback_query, text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await target.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

# ==================== MAIN MENU CALLBACKS ====================
async def show_main_menu(update: Update, user_id, first_name):
    ensure_user(user_id, update.effective_user.username, first_name)
    await reply_or_edit(update, welcome_html(user_id, first_name),
                        reply_markup=main_menu_keyboard(user_id), parse_mode='HTML')

async def show_get_number(update: Update, context, user_id, first_name):
    ensure_user(user_id, update.effective_user.username, first_name)
    db_exec("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    await reply_or_edit(update, "Select a Service:", reply_markup=services_keyboard())

async def show_balance(update: Update, user_id):
    ensure_user(user_id, update.effective_user.username, update.effective_user.first_name)
    user = db_fetch_one("SELECT first_name, balance, withdrawn, total_otp FROM users WHERE user_id = ?", (user_id,))
    if not user:
        return
    first_name, balance, withdrawn, total_otp = user
    balance = balance or 0.0
    withdrawn = withdrawn or 0.0
    total_otp = total_otp or 0
    text = (
        f'{emoji_tag("4958534696645428119", "👤")} {first_name} YOUR DETAILS {emoji_tag("4958506272551863292", "📋")}\n'
        f'------------------------------------------------\n'
        f'{emoji_tag("5197269100878907942", "🆔")} USER ID: {user_id}\n'
        f'{emoji_tag("4958926882994127612", "💰")} BALANCE: ${balance:.3f}\n'
        f'{emoji_tag("5445221832074483553", "💸")} WITHDRAWED: ${withdrawn:.3f}\n'
        f'{emoji_tag("4958534696645428119", "⚠️")} MINIMUM WITHDRAW: $0.1\n'
        f'{emoji_tag("5197288647275071607", "📨")} TOTAL OTP: {total_otp}'
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"WITHDRAW", callback_data="withdraw", style=KBS.SUCCESS,
                             icon_custom_emoji_id=safe_icon("5445353829304387411"))
    ]])
    await reply_or_edit(update, text, reply_markup=kb, parse_mode='HTML')

async def show_withdraw(update: Update, user_id):
    ensure_user(user_id, update.effective_user.username, update.effective_user.first_name)
    balance = db_fetch_one("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    if not balance:
        return
    balance = balance[0] or 0.0
    if balance >= MIN_WITHDRAW:
        text = (
            f'{emoji_tag("4956290155326473271", "📞")} PLEASE CONTACT TO ADMIN {emoji_tag("4956420911310832630", "👨‍💼")}\n\n'
            f'{emoji_tag("4958926882994127612", "💰")} BALANCE: ${balance:.3f}\n'
        )
        kb_buttons = []
        if ADMIN_WHATSAPP:
            kb_buttons.append([InlineKeyboardButton("ADMIN WH", url=ADMIN_WHATSAPP, style=KBS.SUCCESS,
                                                    icon_custom_emoji_id=safe_icon("5334998226636390258"))])
        if ADMIN_TELEGRAM:
            kb_buttons.append([InlineKeyboardButton("ADMIN TG", url=ADMIN_TELEGRAM, style=KBS.PRIMARY,
                                                    icon_custom_emoji_id=safe_icon("5330237710655306682"))])
        if ADMIN2_WHATSAPP:
            kb_buttons.append([InlineKeyboardButton("ADMIN2 WH", url=ADMIN2_WHATSAPP, style=KBS.SUCCESS,
                                                    icon_custom_emoji_id=safe_icon("5334998226636390258"))])
        if ADMIN2_TELEGRAM:
            kb_buttons.append([InlineKeyboardButton("ADMIN2 TG", url=ADMIN2_TELEGRAM, style=KBS.PRIMARY,
                                                    icon_custom_emoji_id=safe_icon("5330237710655306682"))])
        kb = InlineKeyboardMarkup(kb_buttons) if kb_buttons else None
    else:
        need = round(MIN_WITHDRAW - balance, 3)
        text = (
            f'{emoji_tag("4956611513369494230", "🔻")} YOUR MAIN BALANCE IS LOW{emoji_tag("4956387556594811916", "😞")}\n\n'
            f'{emoji_tag("4958534696645428119", "⚠️")} MINIMUM WITHDRAW: $0.1\n'
            f'{emoji_tag("4958926882994127612", "💰")} YOUR CURRENT BALANCE: ${balance:.3f}\n'
            f'{emoji_tag("4958642964181025908", "🧾")} NEED: ${need:.3f}\n\n'
            f'{emoji_tag("4958503072801228000", "📢")} KINDLY GRAB SOME OTP TO WITHDRAW YOU BALANCE {emoji_tag("4956721670690702265", "✅")}'
        )
        kb = None
    await reply_or_edit(update, text, reply_markup=kb, parse_mode='HTML')

async def show_support(update: Update):
    await reply_or_edit(update, "CONTACT SUPPORT\n\n━━━━━━━━━━━━━━━━━━━━\nFor any issues, questions, or requests — contact admin directly.\n\nDeveloper: SR NUMBER HUB", reply_markup=support_keyboard())

# ==================== ADMIN COMMANDS ====================
async def enter_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        admin_mode[user_id] = True
        admin_panel_state[user_id] = "main"
        await update.message.reply_text("ADMIN PANEL\n\nDeveloper: SR NUMBER HUB\n\nSelect an action below:", reply_markup=admin_panel_keyboard())
    else:
        await update.message.reply_text("Unauthorized access!")

async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_mode:
        admin_mode.pop(user_id, None)
        admin_panel_state.pop(user_id, None)
        await update.message.reply_text("Admin mode deactivated!", reply_markup=main_menu_keyboard(user_id))
    else:
        await update.message.reply_text("You're not in admin mode!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        db_exec("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        await update.message.reply_text(f"User {uid} added as admin.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        db_exec("DELETE FROM admins WHERE user_id=?", (uid,))
        await update.message.reply_text(f"User {uid} removed from admins.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")

# ==================== ADMIN PANEL MENU ====================
async def admin_panel_menu(update: Update, user_id):
    if not is_admin(user_id):
        if isinstance(update, CallbackQuery):
            await update.answer("Unauthorized!", show_alert=True)
        else:
            await update.message.reply_text("Unauthorized!")
        return
    admin_mode[user_id] = True
    admin_panel_state[user_id] = "main"
    await reply_or_edit(update, "ADMIN PANEL\n\nDeveloper: SR NUMBER HUB\n\nSelect an action below:", reply_markup=admin_panel_keyboard())

# ==================== USER MANAGER ====================
def generate_user_list_text():
    users = db_fetch_all("SELECT user_id, first_name, balance, withdrawn, total_otp, banned FROM users ORDER BY user_id")
    lines = []
    for u in users:
        uid, first_name, balance, withdrawn, total_otp, banned = u
        balance = balance or 0.0
        withdrawn = withdrawn or 0.0
        total_otp = total_otp or 0
        status = "Banned" if banned else "Active"
        lines.append(f"{first_name} | {uid} | ${balance:.3f} | ${withdrawn:.3f} | {total_otp} | {status}")
    return '\n'.join(lines)

async def send_user_list_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = generate_user_list_text()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        f.flush()
        await update.callback_query.message.reply_document(document=open(f.name, 'rb'), filename="USER_DATA.txt")
    os.unlink(f.name)

async def user_manager_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not is_admin(user_id):
        await update.callback_query.answer("Admin mode required!", show_alert=True)
        return
    admin_panel_state[user_id] = "user_manager"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Search User", callback_data="um_search", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("SEARCH_USER", "")))],
        [InlineKeyboardButton("Download User List", callback_data="um_download", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DOWNLOAD_LIST", "")))],
        [InlineKeyboardButton("Stats Overview", callback_data="um_stats", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("STATS", "")))],
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_back", style=KBS.DANGER,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))],
    ])
    await reply_or_edit(update, "USER MANAGER\n\nSelect an option:", reply_markup=kb)

async def um_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    admin_panel_state[user_id] = "um_searching"
    await reply_or_edit(update, "Send the user ID or username to search.", reply_markup=admin_cancel_keyboard())

async def show_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data):
    uid, first_name, username, balance, withdrawn, total_otp, banned, joined, last_active = user_data
    balance = balance or 0.0
    withdrawn = withdrawn or 0.0
    total_otp = total_otp or 0
    status = "Banned" if banned else "Active"
    since = (datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    recent = db_fetch_all("SELECT number, service FROM numbers WHERE user_id=? AND assigned_date > ? ORDER BY assigned_date DESC LIMIT 10", (uid, since))
    recent_str = "\n".join([f"  • {num} ({svc})" for num, svc in recent]) if recent else "  None"
    text = (
        f"Name: {first_name}\n"
        f"ID: {uid}\n"
        f"Username: @{username or 'N/A'}\n"
        f"Balance: ${balance:.3f}\n"
        f"Withdrawn: ${withdrawn:.3f}\n"
        f"Total OTP: {total_otp}\n"
        f"Status: {status}\n"
        f"Joined: {joined}\n"
        f"Last Active: {last_active}\n\n"
        f"📱 Recent Numbers (20 min):\n{recent_str}"
    )
    ban_text = "Ban" if not banned else "Unban"
    ban_style = KBS.DANGER if not banned else KBS.SUCCESS
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Edit Balance", callback_data=f"um_editbal|{uid}", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("EDIT_BALANCE", "")))],
        [InlineKeyboardButton(ban_text, callback_data=f"um_ban|{uid}", style=ban_style,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BAN_USER", "")))],
        [InlineKeyboardButton("Back", callback_data="um_back", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))],
    ])
    await reply_or_edit(update, text, reply_markup=kb)

async def um_edit_balance_prompt(query, user_id, context: ContextTypes.DEFAULT_TYPE):
    target_uid = query.data.split('|')[1]
    admin_panel_state[user_id] = "um_editbal"
    admin_temp_data[user_id] = {"target_uid": target_uid}
    await query.edit_message_text("Send amount to add/subtract (e.g., +0.5 or -0.2) and optional reason.", reply_markup=admin_cancel_keyboard())

async def um_ban_toggle(query, user_id, context: ContextTypes.DEFAULT_TYPE):
    target_uid = query.data.split('|')[1]
    if not is_admin(user_id): return
    user = db_fetch_one("SELECT banned FROM users WHERE user_id=?", (target_uid,))
    if not user:
        await query.answer("User not found.")
        return
    new_ban = 0 if user[0] else 1
    db_exec("UPDATE users SET banned = ? WHERE user_id = ?", (new_ban, target_uid))
    await query.answer(f"User {'banned' if new_ban else 'unbanned'}!")
    if new_ban:
        try:
            ban_text = (
                f'{emoji_tag("6206077285720659346", "🚫")} <b>Now You Can\'t Use Me</b> {emoji_tag("6206003549722122915", "😢")}\n'
                f'{emoji_tag("6206267591426578467", "📞")} <b>CONTACT TO SUPPORT ADMINS</b> {emoji_tag("6206319341487527808", "👨‍💼")}'
            )
            await context.bot.send_message(target_uid, ban_text, reply_markup=support_keyboard(), parse_mode='HTML')
        except:
            pass
    else:
        try:
            unban_text = (
                f'{emoji_tag("6206508629286196237", "🎉")} <b>Congratulation Now You Can Use The Bot</b> {emoji_tag("6206479140040743133", "🥳")}\n'
                f'{emoji_tag("6206503415195899956", "🔓")} <b>You Are Unbanned</b> {emoji_tag("6204251568137574946", "✅")}'
            )
            await context.bot.send_message(target_uid, unban_text, parse_mode='HTML')
        except:
            pass
    user_data = db_fetch_one("SELECT user_id, first_name, username, balance, withdrawn, total_otp, banned, joined_date, last_active FROM users WHERE user_id=?", (target_uid,))
    if user_data:
        await show_user_detail(query, context, user_data)

async def um_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = db_fetch_one("SELECT COUNT(*) FROM users")[0]
    banned = db_fetch_one("SELECT COUNT(*) FROM users WHERE banned=1")[0]
    active = total - banned
    today = datetime.now().strftime("%Y-%m-%d")
    today_otp = db_fetch_one("SELECT COUNT(*) FROM otps WHERE timestamp LIKE ?", (f"{today}%",))[0] or 0
    text = (
        f"📊 User Statistics\n"
        f"Total Users: {total}\n"
        f"Active: {active}\n"
        f"Banned: {banned}\n"
        f"Today's OTP: {today_otp}\n"
    )
    await reply_or_edit(update, text, reply_markup=admin_back_button())

# ==================== DATABASE DOWNLOAD/UPLOAD ====================
async def database_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not is_admin(user_id): await update.callback_query.answer("Admin mode required!", show_alert=True); return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("DOWNLOAD", callback_data="db_download", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon("6203886371363364022"))],
        [InlineKeyboardButton("UPLOAD", callback_data="db_upload", style=KBS.SUCCESS,
                              icon_custom_emoji_id=safe_icon("6206046503690048595"))],
        [InlineKeyboardButton("Back", callback_data="admin_back", style=KBS.DANGER,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))],
    ])
    await reply_or_edit(update, "DATABASE MANAGEMENT\n\nSelect an option:", reply_markup=kb)

async def db_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id): return
    await query.answer("Preparing database download...")
    tmpdir = tempfile.mkdtemp()
    try:
        shutil.copy2(DB_PATH, os.path.join(tmpdir, "mrisbrand_master.db"))
        if os.path.exists("countries.json"):
            shutil.copy2("countries.json", os.path.join(tmpdir, "countries.json"))
        if os.path.exists("emoji.py"):
            shutil.copy2("emoji.py", os.path.join(tmpdir, "emoji.py"))
        zip_path = os.path.join(tmpdir, "sr-number-data.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmpdir):
                for file in files:
                    if file == "sr-number-data.zip":
                        continue
                    full = os.path.join(root, file)
                    arcname = os.path.relpath(full, tmpdir)
                    zf.write(full, arcname)
        await context.bot.send_document(chat_id=query.message.chat_id, document=open(zip_path, 'rb'))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

async def db_upload_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id): return
    admin_panel_state[user_id] = "waiting_db_upload"
    await query.edit_message_text("Upload the sr-number-data.zip file to restore the database.", reply_markup=admin_cancel_keyboard())

async def handle_db_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) or admin_panel_state.get(user_id) != "waiting_db_upload":
        return
    document = update.message.document
    if not document or not document.file_name.endswith('.zip'):
        await update.message.reply_text("Please upload the correct sr-number-data.zip file.")
        return
    file = await context.bot.get_file(document.file_id)
    tmpdir = tempfile.mkdtemp()
    zip_path = os.path.join(tmpdir, "upload.zip")
    await file.download_to_drive(zip_path)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmpdir)
        for root, dirs, files in os.walk(tmpdir):
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, tmpdir)
                if fname == "mrisbrand_master.db":
                    global conn, c
                    conn.close()
                    shutil.copy2(full, DB_PATH)
                    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                    c = conn.cursor()
                elif fname == "countries.json":
                    shutil.copy2(full, "countries.json")
                    global COUNTRIES_DATA
                    COUNTRIES_DATA = load_countries_db()
                elif fname == "emoji.py":
                    shutil.copy2(full, "emoji.py")
    except Exception as e:
        await update.message.reply_text(f"Error restoring database: {e}")
        return
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    admin_panel_state[user_id] = "main"
    await update.message.reply_text("✅ Database restored successfully!", reply_markup=admin_panel_keyboard())

# ==================== CALLBACK HANDLERS ====================
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await ban_check(update, context):
        return
    first_name = query.from_user.first_name or "User"
    data = query.data
    await query.answer()
    action = data[len("menu_"):]
    if action == "get_number": await show_get_number(update, context, user_id, first_name)
    elif action == "balance": await show_balance(update, user_id)
    elif action == "support": await show_support(update)
    elif action == "admin": await admin_panel_menu(update, user_id)

async def balance_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    await query.answer()
    await show_balance(update, query.from_user.id)

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    await query.answer()
    await show_withdraw(update, query.from_user.id)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    first_name = query.from_user.first_name or "User"
    await query.answer()
    await show_main_menu(update, user_id, first_name)

# ==================== TOGGLE CC CALLBACK ====================
async def toggle_cc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    await query.answer()
    row = db_fetch_one("SELECT remove_cc FROM users WHERE user_id = ?", (user_id,))
    if row:
        new_val = 0 if row[0] == 1 else 1
        db_exec("UPDATE users SET remove_cc = ? WHERE user_id = ?", (new_val, user_id))
    else:
        new_val = 0
    data = last_activation_data.get(user_id)
    if not data:
        await safe_edit_message(query, "No active numbers to display.", reply_markup=back_to_main_keyboard())
        return
    country, service, numbers, msg_id = data
    msg, kb = format_numbers_message(country, service, numbers, user_id=user_id)
    try:
        await safe_edit_message(query, msg, reply_markup=kb, parse_mode='HTML')
    except Exception:
        await query.message.reply_text(msg, reply_markup=kb, parse_mode='HTML')

# ==================== SERVICE→COUNTRY FLOW ====================
async def service_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    await query.answer()
    service = query.data.split('|', 1)[1]
    db_exec("UPDATE users SET current_service = ? WHERE user_id = ?", (service, user_id))
    await safe_edit_message(query, f"Select a Country for {service}:", reply_markup=countries_for_service_keyboard(service))

async def country_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    first_name = query.from_user.first_name or "User"
    await query.answer("Allocating 3 numbers...")
    parts = query.data.split('|')
    if len(parts) < 3:
        await query.answer("Invalid selection.", show_alert=True)
        return
    country = parts[1]
    service = parts[2]

    await safe_edit_message(query, f'{emoji_tag("5976826804931928647", "⏳")}', parse_mode='HTML')
    await asyncio.sleep(1)

    numbers = get_numbers_from_stock(country, service, 3)
    if not numbers:
        await query.answer("No numbers available for this country/service!", show_alert=True)
        await safe_edit_message(query, "Select a Country:", reply_markup=countries_for_service_keyboard(service))
        return

    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for number in numbers:
        db_exec('''INSERT INTO numbers (user_id, number, country, service, assigned_date, status, expiry_time)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)''',
                (user_id, number, country, service, now_str, expiry))
    db_exec('''UPDATE users SET current_number = ?, current_country = ?, current_service = ?, number_expiry = ?
               WHERE user_id = ?''', (numbers[0], country, service, expiry, user_id))

    msg, kb = format_numbers_message(country, service, numbers, user_id=user_id)
    sent_msg = await query.message.reply_text(msg, reply_markup=kb, parse_mode='HTML')
    last_activation_data[user_id] = (country, service, numbers, sent_msg.message_id)
    try:
        await query.delete_message()
    except:
        pass

async def back_to_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    await query.answer()
    db_exec("UPDATE users SET current_service = NULL, current_country = NULL, current_number = NULL, number_expiry = NULL WHERE user_id = ?", (user_id,))
    await safe_edit_message(query, "Select a Service:", reply_markup=services_keyboard())

async def next_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await ban_check(update, context): return
    user_id = query.from_user.id
    first_name = query.from_user.first_name or "User"
    await query.answer("Getting next 3 numbers...")
    
    await safe_edit_message(query, f'{emoji_tag("5976826804931928647", "⏳")}', parse_mode='HTML')
    await asyncio.sleep(1)

    result = db_fetch_one("SELECT current_country, current_service FROM users WHERE user_id = ?", (user_id,))
    country = service = None
    if result and result[0]:
        country, service = result
    else:
        fallback = db_fetch_one("SELECT country, service FROM numbers WHERE user_id = ? ORDER BY assigned_date DESC LIMIT 1", (user_id,))
        if fallback: country, service = fallback
    if not country or not service:
        await query.answer("Please select a service and country first!", show_alert=True)
        await safe_edit_message(query, "Select a Service:", reply_markup=services_keyboard())
        return
    numbers = get_numbers_from_stock(country, service, 3)
    if not numbers:
        await query.answer(f"No more {country} {service} numbers!", show_alert=True)
        await safe_edit_message(query, f"Select a Country for {service}:", reply_markup=countries_for_service_keyboard(service))
        return
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for number in numbers:
        db_exec('''INSERT INTO numbers (user_id, number, country, service, assigned_date, status, expiry_time)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)''',
                (user_id, number, country, service, now_str, expiry))
    db_exec('''UPDATE users SET current_number = ?, current_country = ?, current_service = ?, number_expiry = ?
               WHERE user_id = ?''', (numbers[0], country, service, expiry, user_id))
    msg, kb = format_numbers_message(country, service, numbers, user_id=user_id)
    sent_msg = await query.message.reply_text(msg, reply_markup=kb, parse_mode='HTML')
    last_activation_data[user_id] = (country, service, numbers, sent_msg.message_id)
    try:
        await query.delete_message()
    except:
        pass

# ==================== ADMIN CALLBACKS ====================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("Admin mode required!", show_alert=True)
        return
    await query.answer()
    data = query.data
    if data.startswith("admin_del|"):
        parts = data.split('|', 2)
        if len(parts) == 3:
            if delete_country_stock(parts[1], parts[2]):
                await query.answer(f"{parts[1]} — {parts[2]} deleted!")
            else:
                await query.answer(f"Error deleting {parts[1]} — {parts[2]}!", show_alert=True)
            await show_delete_options(query, user_id)
        return
    action = data[len("admin_"):]
    if action == "stats": await show_admin_stats(update, user_id)
    elif action == "upload": await request_upload(update, user_id)
    elif action == "delete": await show_delete_options(query, user_id)
    elif action == "broadcast": await request_broadcast(update, user_id)
    elif action == "giveaway": await request_giveaway(update, user_id)
    elif action == "country_manager": await country_manager_menu(update, user_id)
    elif action == "service_manager": await service_manager_menu(update, user_id)
    elif action == "user_manager": await user_manager_menu(update, context, user_id)
    elif action == "database": await database_menu(update, context, user_id)
    elif action == "exit": await exit_admin_callback_query(query, user_id, context.bot)
    elif action == "back":
        admin_panel_state[user_id] = "main"
        await safe_edit_message(query, "ADMIN PANEL\n\nDeveloper: SR NUMBER HUB\n\nSelect an action below:", reply_markup=admin_panel_keyboard())

async def show_admin_stats(update: Update, user_id):
    total_users = db_fetch_one("SELECT COUNT(*) FROM users")[0]
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    active_users = db_fetch_one("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))[0]
    active_numbers = db_fetch_one("SELECT COUNT(*) FROM numbers WHERE status = 'active'")[0]
    total_stock = db_fetch_one("SELECT SUM(stock) FROM countries")[0] or 0
    available_numbers = db_fetch_one("SELECT COUNT(*) FROM available_numbers WHERE used = 0")[0]
    active_countries = db_fetch_one("SELECT COUNT(*) FROM countries WHERE active = 1")[0]
    text = (
        f'{emoji_tag(CUSTOM_EMOJIS["STATS"], "📊")} BOT STATISTICS {emoji_tag(CUSTOM_EMOJIS["STATS"], "📊")}\n\n'
        f'{emoji_tag(CUSTOM_EMOJIS["GIVEAWAY"], "👥")} USERS {emoji_tag(CUSTOM_EMOJIS["GIVEAWAY"], "👥")}\n\n'
        f'Total Users: {total_users}\n'
        f'Active {emoji_tag(CUSTOM_EMOJIS["GREEN_CIRCLE"], "🟢")}: {active_users}\n'
        f'Inactive {emoji_tag(CUSTOM_EMOJIS["RED_CIRCLE"], "🔴")}: {total_users - active_users}\n\n'
        f'{emoji_tag(CUSTOM_EMOJIS["GET_NUMBER"], "📱")} NUMBERS {emoji_tag(CUSTOM_EMOJIS["GET_NUMBER"], "📱")}\n\n'
        f'Active {emoji_tag(CUSTOM_EMOJIS["GREEN_CIRCLE"], "🟢")}: {active_numbers}\n'
        f'Total Stock {emoji_tag(CUSTOM_EMOJIS["PACKAGE"], "📦")}: {total_stock}\n'
        f'Available {emoji_tag(CUSTOM_EMOJIS["GEAR"], "⚙️")}: {available_numbers}\n\n'
        f'{emoji_tag(CUSTOM_EMOJIS["CHANGE_COUNTRY"], "🌍")} COUNTRIES {emoji_tag(CUSTOM_EMOJIS["CHANGE_COUNTRY"], "🌍")}\n'
        f'{emoji_tag(CUSTOM_EMOJIS["GREEN_CIRCLE"], "🟢")} Active Services {emoji_tag(CUSTOM_EMOJIS["SERVICE_MANAGER"], "🔧")}: {active_countries}\n\n'
        f'{datetime.now().strftime("%I:%M %p | %d %b %Y")} {emoji_tag(CUSTOM_EMOJIS["CLOCK"], "🕐")}'
    )
    countries = db_fetch_all("SELECT name, service, stock FROM countries WHERE active = 1 ORDER BY name")
    if countries:
        text += f'\n\n{emoji_tag(CUSTOM_EMOJIS["PACKAGE"], "📦")} STOCK DETAILS {emoji_tag(CUSTOM_EMOJIS["PACKAGE"], "📦")}:\n'
        for name, service, stock_count in countries:
            text += f'In stock {country_flag_emoji(name)} {name} — {service_emoji_tag(service)}: {stock_count}\n'
    await reply_or_edit(update, text, reply_markup=admin_back_button(), parse_mode='HTML')

async def show_delete_options(query, user_id):
    countries = db_fetch_all("SELECT name, service, stock FROM countries WHERE active = 1 ORDER BY name")
    if not countries:
        await safe_edit_message(query, "No countries to delete!", reply_markup=admin_back_button())
        return
    rows = []
    for name, service, stock_count in countries:
        rows.append([InlineKeyboardButton(f"Delete {name} — {service} (Stock: {stock_count})",
                                          callback_data=f"admin_del|{name}|{service}",
                                          style=KBS.DANGER,
                                          icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", "")))])
    rows.append([InlineKeyboardButton("Back to Admin Panel", callback_data="admin_back", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await safe_edit_message(query, "DELETE STOCK\n\nSelect a country/service to delete all its numbers:", reply_markup=InlineKeyboardMarkup(rows))

async def request_upload(update: Update, user_id):
    admin_panel_state[user_id] = "waiting_file"
    await reply_or_edit(update, "UPLOAD STOCK\n\nSend a .txt file with phone numbers.\nFilename must contain country & service name.\nOne number per line.", reply_markup=admin_cancel_keyboard())

async def request_broadcast(update: Update, user_id):
    admin_panel_state[user_id] = "waiting_broadcast"
    await reply_or_edit(update, "BROADCAST MESSAGE\n\nSend the message you want to broadcast to ALL users (any media or text).", reply_markup=admin_cancel_keyboard())

async def request_giveaway(update: Update, user_id):
    admin_panel_state[user_id] = "waiting_giveaway"
    await reply_or_edit(update, "GIVE FREE ACCOUNT\n\nSend: user_id count\nExample: 123456789 5", reply_markup=admin_cancel_keyboard())

async def exit_admin_callback_query(query, user_id, bot):
    admin_mode.pop(user_id, None)
    admin_panel_state.pop(user_id, None)
    try:
        await safe_edit_message(query, welcome_html(user_id, query.from_user.first_name or "User"),
                                reply_markup=main_menu_keyboard(user_id), parse_mode='HTML')
    except Exception:
        await bot.send_message(user_id, "Returned to main menu.", reply_markup=main_menu_keyboard(user_id))

# ==================== COUNTRY & SERVICE CALLBACKS (unchanged except added multi-admin check) ====================
async def country_manager_menu(update: Update, user_id):
    if not is_admin(user_id): await update.callback_query.answer("Admin mode required!", show_alert=True); return
    admin_panel_state[user_id] = "country_manager"
    rows = [
        [InlineKeyboardButton("Add New Country", callback_data="country_add", style=KBS.SUCCESS,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("COUNTRY_MANAGER", "")))],
        [InlineKeyboardButton("List All Countries", callback_data="country_list", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("COUNTRY_MANAGER", "")))],
        [InlineKeyboardButton("Edit Country", callback_data="country_edit_select", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("COUNTRY_MANAGER", "")))],
        [InlineKeyboardButton("Delete Country", callback_data="country_delete_select", style=KBS.DANGER,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", "")))],
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_back", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))],
    ]
    await reply_or_edit(update, "COUNTRY MANAGER\n\nSelect an option:", reply_markup=InlineKeyboardMarkup(rows))

async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id): await query.answer("Admin mode required!", show_alert=True); return
    await query.answer()
    data = query.data
    if data == "country_add":
        await country_add_start(update, user_id)
    elif data == "country_list":
        await country_list_show(update, user_id)
    elif data == "country_edit_select":
        await country_edit_select(update, user_id)
    elif data == "country_delete_select":
        await country_delete_select(update, user_id)
    elif data.startswith("country_edit|"):
        await country_edit_start(update, user_id, data.split('|', 1)[1])
    elif data.startswith("country_delete|"):
        await country_delete_direct(query, user_id, data.split('|', 1)[1])

async def country_add_start(update: Update, user_id):
    admin_panel_state[user_id] = "waiting_country_add"
    await reply_or_edit(update,
        "ADD NEW COUNTRY\n\nFormat: CountryName | Code | ISO | payout | emoji_id\n"
        "Example: Bangladesh | +880 | BD | 0.001$ | 5911365056594973179",
        reply_markup=admin_cancel_keyboard())

async def country_list_show(update: Update, user_id):
    lines = [f'ALL COUNTRIES {emoji_tag(CUSTOM_EMOJIS["CHANGE_COUNTRY"], "🌍")}', '']
    for name, info in COUNTRIES_DATA.items():
        lines.append(f'• {country_flag_emoji(name)} {name}')
        lines.append(f'  Code: {info["code"]} | ISO: {info["iso"]} | Payout: {info.get("payout", "0.001$")} | Emoji ID: {info.get("emoji_id") or "Not set"}')
        lines.append('')
    await reply_or_edit(update, '\n'.join(lines), reply_markup=admin_back_button(), parse_mode='HTML')

async def country_edit_select(update: Update, user_id):
    rows = []
    for name, info in COUNTRIES_DATA.items():
        icon = info.get("emoji_id") or CUSTOM_EMOJIS.get("DEFAULT_FLAG", "")
        rows.append([InlineKeyboardButton(f"{name} (Payout: {info.get('payout','0.001$')})",
                                          callback_data=f"country_edit|{name}",
                                          style=KBS.PRIMARY,
                                          icon_custom_emoji_id=safe_icon(icon))])
    rows.append([InlineKeyboardButton("Back", callback_data="admin_country_manager", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await reply_or_edit(update, "Select country to edit:", reply_markup=InlineKeyboardMarkup(rows))

async def country_edit_start(update: Update, user_id, country_name):
    admin_temp_data[user_id] = {"edit_country": country_name}
    admin_panel_state[user_id] = "waiting_country_edit"
    info = COUNTRIES_DATA[country_name]
    await reply_or_edit(update,
        f"EDIT COUNTRY: {country_name}\n\nCurrent:\nCode: {info['code']}\nISO: {info['iso']}\nPayout: {info.get('payout','0.001$')}\nEmoji ID: {info.get('emoji_id', 'Not set')}\n\nSend new details: Code | ISO | payout | emoji_id\nSend /skip to keep.",
        reply_markup=admin_cancel_keyboard())

async def country_delete_select(update: Update, user_id):
    rows = []
    for name in COUNTRIES_DATA:
        rows.append([InlineKeyboardButton(f"Delete {name}", callback_data=f"country_delete|{name}",
                                          style=KBS.DANGER,
                                          icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", "")))])
    rows.append([InlineKeyboardButton("Back", callback_data="admin_country_manager", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await reply_or_edit(update, "Select country to delete:", reply_markup=InlineKeyboardMarkup(rows))

async def country_delete_direct(query, user_id, country_name):
    if not is_admin(user_id): await query.answer("Admin mode required!", show_alert=True); return
    if country_name in COUNTRIES_DATA:
        del COUNTRIES_DATA[country_name]
        save_countries_db(COUNTRIES_DATA)
        db_exec("DELETE FROM available_numbers WHERE country = ?", (country_name,))
        db_exec("DELETE FROM countries WHERE name = ?", (country_name,))
        await query.answer(f"{country_name} deleted!")
    else:
        await query.answer("Country not found!", show_alert=True)
    await country_delete_select(query, user_id)

async def country_add_service_selection(update: Update, user_id, country_name):
    services = db_fetch_all("SELECT name, display_name, emoji_id FROM services WHERE active = 1 ORDER BY name")
    rows = []
    for s in services:
        rows.append([InlineKeyboardButton(
            s[1],
            callback_data=f"cnt_add_svc|{country_name}|{s[0]}",
            style=KBS.PRIMARY,
            icon_custom_emoji_id=safe_icon(s[2]) if s[2] else None
        )])
    rows.append([InlineKeyboardButton("Skip", callback_data="admin_back", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    kb = InlineKeyboardMarkup(rows)
    text = f"Country '{country_name}' added. Select a service to link (or Skip):"
    await reply_or_edit(update, text, reply_markup=kb)

async def country_add_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split('|')
    if len(parts) != 3: await query.answer("Invalid.", show_alert=True); return
    country_name = parts[1]
    service_name = parts[2]
    db_exec("INSERT OR IGNORE INTO countries (name, service, flag, stock) VALUES (?, ?, ?, 0)", (country_name, service_name, country_name))
    await query.answer(f"{country_name} now available for {service_name}!")
    admin_panel_state[user_id] = "main"
    await safe_edit_message(query, "Country linked successfully.", reply_markup=admin_panel_keyboard())

# ==================== SERVICE MANAGER ====================
async def service_manager_menu(update: Update, user_id):
    if not is_admin(user_id):
        await update.callback_query.answer("Admin mode required!", show_alert=True)
        return
    admin_panel_state[user_id] = "service_manager"
    rows = [
        [InlineKeyboardButton("Add New Service", callback_data="service_add", style=KBS.SUCCESS,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("ADD", "")))],
        [InlineKeyboardButton("Remove Service", callback_data="service_remove", style=KBS.DANGER,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", "")))],
        [InlineKeyboardButton("Toggle Service Active", callback_data="service_toggle", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon("4956583802240500602"))],
        [InlineKeyboardButton("Set Service Emoji", callback_data="service_set_emoji", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon("4956214413578207998"))],
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_back", style=KBS.PRIMARY,
                              icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))],
    ]
    await reply_or_edit(update, "SERVICE MANAGER\n\nSelect an option:", reply_markup=InlineKeyboardMarkup(rows))

async def service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("Admin mode required!", show_alert=True)
        return
    await query.answer()
    data = query.data
    if data == "service_add":
        await service_add_start(update, user_id)
    elif data == "service_remove":
        await service_remove_select(query, user_id)
    elif data.startswith("service_remove|"):
        await service_remove_execute(query, data.split('|', 1)[1])
    elif data == "service_toggle":
        await service_toggle_select(query, user_id)
    elif data == "service_set_emoji":
        await service_set_emoji_select(update, user_id)
    elif data.startswith("service_toggle|"):
        await service_toggle_execute(query, data.split('|', 1)[1])
    elif data.startswith("service_emoji_set|"):
        await service_set_emoji_start(update, user_id, data.split('|', 1)[1])

async def service_add_start(update: Update, user_id):
    admin_panel_state[user_id] = "waiting_service_name"
    await reply_or_edit(update, "Send the service name.", reply_markup=admin_cancel_keyboard())

async def service_remove_select(target, user_id):
    services = db_fetch_all("SELECT name, display_name FROM services ORDER BY name")
    rows = []
    for s in services:
        rows.append([InlineKeyboardButton(f"Remove {s[1]}",
                                          callback_data=f"service_remove|{s[0]}",
                                          style=KBS.DANGER,
                                          icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("DELETE", "")))])
    rows.append([InlineKeyboardButton("Back", callback_data="admin_service_manager", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await reply_or_edit(target, "Select service to remove:", reply_markup=InlineKeyboardMarkup(rows))

async def service_remove_execute(query, service_name):
    db_exec("DELETE FROM services WHERE name = ?", (service_name,))
    db_exec("DELETE FROM countries WHERE service = ?", (service_name,))
    await query.answer(f"Service '{service_name}' removed!")
    await service_remove_select(query, query.from_user.id)

async def service_toggle_select(target, user_id):
    services = db_fetch_all("SELECT name, display_name, active FROM services ORDER BY name")
    rows = []
    for s in services:
        status = "Active" if s[2] else "Inactive"
        style = KBS.SUCCESS if s[2] else KBS.DANGER
        rows.append([InlineKeyboardButton(f"{s[1]} ({status})",
                                          callback_data=f"service_toggle|{s[0]}",
                                          style=style,
                                          icon_custom_emoji_id=safe_icon("4956583802240500602"))])
    rows.append([InlineKeyboardButton("Back", callback_data="admin_service_manager", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await reply_or_edit(target, "Select service to toggle:", reply_markup=InlineKeyboardMarkup(rows))

async def service_toggle_execute(query, service_name):
    result = db_fetch_one("SELECT active FROM services WHERE name = ?", (service_name,))
    if result:
        new_status = 0 if result[0] else 1
        db_exec("UPDATE services SET active = ? WHERE name = ?", (new_status, service_name))
        await query.answer(f"Service {'activated' if new_status else 'deactivated'}!")
    await service_toggle_select(query, query.from_user.id)

async def service_set_emoji_select(update: Update, user_id):
    if not is_admin(user_id): await update.callback_query.answer("Admin mode required!", show_alert=True); return
    services = db_fetch_all("SELECT name, display_name FROM services WHERE active = 1 ORDER BY name")
    rows = []
    for s in services:
        rows.append([InlineKeyboardButton(f"{s[1]} ({s[0]})",
                                          callback_data=f"service_emoji_set|{s[0]}",
                                          style=KBS.PRIMARY,
                                          icon_custom_emoji_id=safe_icon("4956214413578207998"))])
    rows.append([InlineKeyboardButton("Back", callback_data="admin_service_manager", style=KBS.PRIMARY,
                                      icon_custom_emoji_id=safe_icon(CUSTOM_EMOJIS.get("BACK", "")))])
    await reply_or_edit(update, "Select service to set emoji:", reply_markup=InlineKeyboardMarkup(rows))

async def service_set_emoji_start(update: Update, user_id, service_name):
    admin_temp_data[user_id] = {"set_emoji_service": service_name}
    admin_panel_state[user_id] = "waiting_service_emoji"
    await reply_or_edit(update, f"Send custom emoji ID for '{service_name}'.\nSend /skip to keep.", reply_markup=admin_cancel_keyboard())

async def handle_service_emoji_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    service_name = admin_temp_data.get(user_id, {}).get("set_emoji_service")
    if not service_name: await update.message.reply_text("Session expired."); return True
    if text == "/skip": text = ""
    db_exec("UPDATE services SET emoji_id = ? WHERE name = ?", (text, service_name))
    await update.message.reply_text(f"Emoji for {service_name} updated!")
    admin_panel_state[user_id] = "service_manager"
    await service_manager_menu(update, user_id)
    return True

# ==================== FILE UPLOAD ====================
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) or admin_panel_state.get(user_id) != "waiting_file": return
    try:
        document = update.message.document
        if not document.file_name.endswith('.txt'): 
            await update.message.reply_text("Please upload a .txt file!"); return
        file = await context.bot.get_file(document.file_id)
        os.makedirs("uploads", exist_ok=True)
        file_path = f"uploads/{document.file_name}"
        await file.download_to_drive(file_path)
        
        count, country, service = load_numbers_from_file(file_path, document.file_name)
        if count > 0:
            emoji_row = db_fetch_one("SELECT emoji_id FROM services WHERE name = ?", (service,))
            if not emoji_row:
                admin_temp_data[user_id] = {"pending_service_emoji": service, "country": country, "count": count}
                admin_panel_state[user_id] = "waiting_service_emoji_upload"
                await update.message.reply_text(
                    f"✅ {count} numbers loaded for {country}.\n"
                    f"New service '{service}' detected.\n"
                    "Please send the custom emoji ID for this service (or /skip to use default).",
                    reply_markup=admin_cancel_keyboard())
                return
            
            msg = stock_added_message(country, service, count)
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=admin_panel_keyboard())
            
            broadcast_msg = stock_added_broadcast(country, service, count)
            users = db_fetch_all("SELECT user_id FROM users")
            for user in users:
                try:
                    await context.bot.send_message(user[0], broadcast_msg, parse_mode='HTML')
                    await asyncio.sleep(0.05)
                except Exception:
                    continue
            
            admin_panel_state[user_id] = "main"
        else:
            await update.message.reply_text("No valid numbers found in file!", reply_markup=admin_panel_keyboard())
            admin_panel_state[user_id] = "main"
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        admin_panel_state[user_id] = "main"

# ==================== ADMIN TEXT HANDLER (FIXED BROADCAST & STATE-BASED SEARCH) ====================
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = admin_panel_state.get(user_id)
    if not is_admin(user_id):
        return False

    if state == "waiting_broadcast":
        msg = update.message
        users = db_fetch_all("SELECT user_id FROM users WHERE banned=0")
        sent = 0
        for u in users:
            try:
                await msg.copy(chat_id=u[0])
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                continue
        admin_panel_state[user_id] = "main"
        await msg.reply_text(f"Broadcast sent to {sent} users!", reply_markup=admin_panel_keyboard())
        return True

    if state == "waiting_db_upload":
        return False

    if not update.message or not update.message.text:
        return False

    text = update.message.text.strip()

    if state == "um_searching":
        user = db_fetch_one("SELECT user_id, first_name, username, balance, withdrawn, total_otp, banned, joined_date, last_active FROM users WHERE user_id=? OR username=?", (text, text))
        if not user and text.isdigit():
            user = db_fetch_one("SELECT user_id, first_name, username, balance, withdrawn, total_otp, banned, joined_date, last_active FROM users WHERE user_id=?", (int(text),))
        if not user:
            await update.message.reply_text("User not found.")
            return True
        admin_panel_state[user_id] = "user_manager"
        await show_user_detail(update, context, user)
        return True

    if state == "um_editbal":
        data = admin_temp_data.pop(user_id, {})
        target_uid = data.get("target_uid")
        if not target_uid:
            await update.message.reply_text("Session expired.")
            return True
        try:
            parts = text.split(' ', 1)
            amount_str = parts[0]
            amount = float(amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount. Use format: +0.5 or -0.2")
            return True
        current = db_fetch_one("SELECT balance FROM users WHERE user_id=?", (target_uid,))
        if not current:
            await update.message.reply_text("User not found.")
            return True
        new_balance = (current[0] or 0.0) + amount
        db_exec("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, target_uid))
        await update.message.reply_text(f"Balance updated for {target_uid}. New balance: ${new_balance:.3f}")
        admin_panel_state[user_id] = "main"
        await admin_panel_menu(update, user_id)
        return True

    if state == "waiting_giveaway":
        parts = text.split()
        try:
            target, count = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
            await update.message.reply_text(f"Given {count} free account(s) to {target}.", reply_markup=admin_panel_keyboard())
            admin_panel_state[user_id] = "main"
        except:
            await update.message.reply_text("Invalid format!")
        return True

    elif state == "waiting_country_add":
        try:
            parts = [p.strip() for p in text.split('|')]
            if len(parts) < 4: await update.message.reply_text("Format: CountryName | Code | ISO | payout | emoji_id"); return True
            name, code, iso, payout = parts[0], parts[1], parts[2].upper(), parts[3]
            emoji_id = parts[4] if len(parts) >= 5 else ""
            COUNTRIES_DATA[name] = {"code": code, "iso": iso, "payout": payout, "emoji_id": emoji_id}
            save_countries_db(COUNTRIES_DATA)
            await country_add_service_selection(update, user_id, name)
            return True
        except Exception as e: await update.message.reply_text(f"Error: {e}")
        return True

    elif state == "waiting_country_edit":
        if text.strip() == "/skip":
            admin_panel_state[user_id] = "country_manager"
            await update.message.reply_text("No changes.")
            await country_manager_menu(update, user_id)
            return True
        try:
            parts = [p.strip() for p in text.split('|')]
            if len(parts) < 3: await update.message.reply_text("At least Code | ISO | payout required."); return True
            code, iso, payout = parts[0], parts[1].upper(), parts[2]
            emoji_id = parts[3] if len(parts) >= 4 else ""
            country_name = admin_temp_data.get(user_id, {}).get("edit_country")
            COUNTRIES_DATA[country_name].update({"code": code, "iso": iso, "payout": payout, "emoji_id": emoji_id})
            save_countries_db(COUNTRIES_DATA)
            admin_panel_state[user_id] = "country_manager"
            await update.message.reply_text(f"Country {country_name} updated!")
            await country_manager_menu(update, user_id)
        except Exception as e: await update.message.reply_text(f"Error: {e}")
        return True

    elif state == "waiting_service_name":
        try:
            db_exec("INSERT INTO services (name, display_name, active, emoji_id) VALUES (?, ?, 1, '')", (text, text))
            await update.message.reply_text(f"Service {text} added!")
        except sqlite3.IntegrityError: await update.message.reply_text(f"Service {text} already exists!")
        admin_panel_state[user_id] = "service_manager"
        await service_manager_menu(update, user_id)
        return True

    elif state == "waiting_service_emoji":
        return await handle_service_emoji_set(update, context)

    elif state == "waiting_service_emoji_upload":
        if text.strip() == "/skip": text = ""
        data = admin_temp_data.get(user_id, {})
        service = data.get("pending_service_emoji")
        country = data.get("country")
        count = data.get("count")
        db_exec("INSERT OR IGNORE INTO services (name, display_name, active, emoji_id) VALUES (?, ?, 1, ?)", (service, service, text))
        if text:
            db_exec("UPDATE services SET emoji_id = ? WHERE name = ?", (text, service))
        msg = stock_added_message(country, service, count)
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=admin_panel_keyboard())
        broadcast_msg = stock_added_broadcast(country, service, count)
        users = db_fetch_all("SELECT user_id FROM users")
        for u in users:
            try:
                await context.bot.send_message(u[0], broadcast_msg, parse_mode='HTML')
                await asyncio.sleep(0.05)
            except Exception:
                continue
        admin_panel_state[user_id] = "main"
        admin_temp_data.pop(user_id, None)
        return True

    return False

# ==================== OTP DUPLICATE CHECK ====================
def is_duplicate_otp(number, otp_code, current_ts_str):
    try:
        current_ts = datetime.strptime(current_ts_str, "%Y-%m-%d %H:%M:%S")
    except:
        return False
    rows = db_fetch_all("SELECT timestamp FROM otps WHERE number=? AND otp=? ORDER BY timestamp DESC LIMIT 1", (number, otp_code))
    if not rows:
        return False
    last_ts_str = rows[0][0]
    try:
        last_ts = datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
    except:
        return False
    diff = abs((current_ts - last_ts).total_seconds())
    return diff <= 0.5

# ==================== GROUP OTP MESSAGE BUILDER (NEW FORMAT) ====================
COUNTRY_CODE_MAP = {
    "1": ("US", "🇺🇸", "USA"), "7": ("RU", "🇷🇺", "RUSSIA"), "20": ("EG", "🇪🇬", "EGYPT"),
    "27": ("ZA", "🇿🇦", "SOUTH AFRICA"), "30": ("GR", "🇬🇷", "GREECE"), "31": ("NL", "🇳🇱", "NETHERLANDS"),
    "33": ("FR", "🇫🇷", "FRANCE"), "34": ("ES", "🇪🇸", "SPAIN"), "39": ("IT", "🇮🇹", "ITALY"),
    "40": ("RO", "🇷🇴", "ROMANIA"), "41": ("CH", "🇨🇭", "SWITZERLAND"), "43": ("AT", "🇦🇹", "AUSTRIA"),
    "44": ("GB", "🇬🇧", "UNITED KINGDOM"), "46": ("SE", "🇸🇪", "SWEDEN"), "48": ("PL", "🇵🇱", "POLAND"),
    "49": ("DE", "🇩🇪", "GERMANY"), "51": ("PE", "🇵🇪", "PERU"), "52": ("MX", "🇲🇽", "MEXICO"),
    "54": ("AR", "🇦🇷", "ARGENTINA"), "55": ("BR", "🇧🇷", "BRAZIL"), "56": ("CL", "🇨🇱", "CHILE"),
    "57": ("CO", "🇨🇴", "COLOMBIA"), "58": ("VE", "🇻🇪", "VENEZUELA"), "60": ("MY", "🇲🇾", "MALAYSIA"),
    "62": ("ID", "🇮🇩", "INDONESIA"), "63": ("PH", "🇵🇭", "PHILIPPINES"), "66": ("TH", "🇹🇭", "THAILAND"),
    "81": ("JP", "🇯🇵", "JAPAN"), "82": ("KR", "🇰🇷", "SOUTH KOREA"), "84": ("VN", "🇻🇳", "VIETNAM"),
    "86": ("CN", "🇨🇳", "CHINA"), "90": ("TR", "🇹🇷", "TURKEY"), "91": ("IN", "🇮🇳", "INDIA"),
    "92": ("PK", "🇵🇰", "PAKISTAN"), "93": ("AF", "🇦🇫", "AFGHANISTAN"), "94": ("LK", "🇱🇰", "SRI LANKA"),
    "95": ("MM", "🇲🇲", "MYANMAR"), "98": ("IR", "🇮🇷", "IRAN"), "211": ("SS", "🇸🇸", "SOUTH SUDAN"),
    "212": ("MA", "🇲🇦", "MOROCCO"), "213": ("DZ", "🇩🇿", "ALGERIA"), "216": ("TN", "🇹🇳", "TUNISIA"),
    "218": ("LY", "🇱🇾", "LIBYA"), "220": ("GM", "🇬🇲", "GAMBIA"), "221": ("SN", "🇸🇳", "SENEGAL"),
    "222": ("MR", "🇲🇷", "MAURITANIA"), "223": ("ML", "🇲🇱", "MALI"), "224": ("GN", "🇬🇳", "GUINEA"),
    "225": ("CI", "🇨🇮", "IVORY COAST"), "226": ("BF", "🇧🇫", "BURKINA FASO"), "227": ("NE", "🇳🇪", "NIGER"),
    "228": ("TG", "🇹🇬", "TOGO"), "229": ("BJ", "🇧🇯", "BENIN"), "230": ("MU", "🇲🇺", "MAURITIUS"),
    "231": ("LR", "🇱🇷", "LIBERIA"), "232": ("SL", "🇸🇱", "SIERRA LEONE"), "233": ("GH", "🇬🇭", "GHANA"),
    "234": ("NG", "🇳🇬", "NIGERIA"), "235": ("TD", "🇹🇩", "CHAD"), "236": ("CF", "🇨🇫", "CENTRAL AFRICAN REPUBLIC"),
    "237": ("CM", "🇨🇲", "CAMEROON"), "238": ("CV", "🇨🇻", "CAPE VERDE"), "239": ("ST", "🇸🇹", "SAO TOME AND PRINCIPE"),
    "240": ("GQ", "🇬🇶", "EQUATORIAL GUINEA"), "241": ("GA", "🇬🇦", "GABON"), "242": ("CG", "🇨🇬", "CONGO"),
    "243": ("CD", "🇨🇩", "DR CONGO"), "244": ("AO", "🇦🇴", "ANGOLA"), "245": ("GW", "🇬🇼", "GUINEA-BISSAU"),
    "246": ("IO", "🇮🇴", "BRITISH INDIAN OCEAN TERRITORY"), "248": ("SC", "🇸🇨", "SEYCHELLES"),
    "249": ("SD", "🇸🇩", "SUDAN"), "250": ("RW", "🇷🇼", "RWANDA"), "251": ("ET", "🇪🇹", "ETHIOPIA"),
    "252": ("SO", "🇸🇴", "SOMALIA"), "253": ("DJ", "🇩🇯", "DJIBOUTI"), "254": ("KE", "🇰🇪", "KENYA"),
    "255": ("TZ", "🇹🇿", "TANZANIA"), "256": ("UG", "🇺🇬", "UGANDA"), "257": ("BI", "🇧🇮", "BURUNDI"),
    "258": ("MZ", "🇲🇿", "MOZAMBIQUE"), "260": ("ZM", "🇿🇲", "ZAMBIA"), "261": ("MG", "🇲🇬", "MADAGASCAR"),
    "262": ("RE", "🇷🇪", "REUNION"), "263": ("ZW", "🇿🇼", "ZIMBABWE"), "264": ("NA", "🇳🇦", "NAMIBIA"),
    "265": ("MW", "🇲🇼", "MALAWI"), "266": ("LS", "🇱🇸", "LESOTHO"), "267": ("BW", "🇧🇼", "BOTSWANA"),
    "268": ("SZ", "🇸🇿", "ESWATINI"), "269": ("KM", "🇰🇲", "COMOROS"), "290": ("SH", "🇸🇭", "SAINT HELENA"),
    "291": ("ER", "🇪🇷", "ERITREA"), "297": ("AW", "🇦🇼", "ARUBA"), "298": ("FO", "🇫🇴", "FAROE ISLANDS"),
    "299": ("GL", "🇬🇱", "GREENLAND"), "350": ("GI", "🇬🇮", "GIBRALTAR"), "351": ("PT", "🇵🇹", "PORTUGAL"),
    "352": ("LU", "🇱🇺", "LUXEMBOURG"), "353": ("IE", "🇮🇪", "IRELAND"), "354": ("IS", "🇮🇸", "ICELAND"),
    "355": ("AL", "🇦🇱", "ALBANIA"), "356": ("MT", "🇲🇹", "MALTA"), "357": ("CY", "🇨🇾", "CYPRUS"),
    "358": ("FI", "🇫🇮", "FINLAND"), "359": ("BG", "🇧🇬", "BULGARIA"), "370": ("LT", "🇱🇹", "LITHUANIA"),
    "371": ("LV", "🇱🇻", "LATVIA"), "372": ("EE", "🇪🇪", "ESTONIA"), "373": ("MD", "🇲🇩", "MOLDOVA"),
    "374": ("AM", "🇦🇲", "ARMENIA"), "375": ("BY", "🇧🇾", "BELARUS"), "376": ("AD", "🇦🇩", "ANDORRA"),
    "377": ("MC", "🇲🇨", "MONACO"), "378": ("SM", "🇸🇲", "SAN MARINO"), "380": ("UA", "🇺🇦", "UKRAINE"),
    "381": ("RS", "🇷🇸", "SERBIA"), "382": ("ME", "🇲🇪", "MONTENEGRO"), "383": ("XK", "🇽🇰", "KOSOVO"),
    "385": ("HR", "🇭🇷", "CROATIA"), "386": ("SI", "🇸🇮", "SLOVENIA"), "387": ("BA", "🇧🇦", "BOSNIA AND HERZEGOVINA"),
    "389": ("MK", "🇲🇰", "NORTH MACEDONIA"), "420": ("CZ", "🇨🇿", "CZECH REPUBLIC"), "421": ("SK", "🇸🇰", "SLOVAKIA"),
    "423": ("LI", "🇱🇮", "LIECHTENSTEIN"), "500": ("FK", "🇫🇰", "FALKLAND ISLANDS"), "501": ("BZ", "🇧🇿", "BELIZE"),
    "502": ("GT", "🇬🇹", "GUATEMALA"), "503": ("SV", "🇸🇻", "EL SALVADOR"), "504": ("HN", "🇭🇳", "HONDURAS"),
    "505": ("NI", "🇳🇮", "NICARAGUA"), "506": ("CR", "🇨🇷", "COSTA RICA"), "507": ("PA", "🇵🇦", "PANAMA"),
    "509": ("HT", "🇭🇹", "HAITI"), "590": ("GP", "🇬🇵", "GUADELOUPE"), "591": ("BO", "🇧🇴", "BOLIVIA"),
    "592": ("GY", "🇬🇾", "GUYANA"), "593": ("EC", "🇪🇨", "ECUADOR"), "594": ("GF", "🇬🇫", "FRENCH GUIANA"),
    "595": ("PY", "🇵🇾", "PARAGUAY"), "596": ("MQ", "🇲🇶", "MARTINIQUE"), "597": ("SR", "🇸🇷", "SURINAME"),
    "598": ("UY", "🇺🇾", "URUGUAY"), "599": ("BQ", "🇧🇶", "CARIBBEAN NETHERLANDS"), "880": ("BD", "🇧🇩", "BANGLADESH"),
    "960": ("MV", "🇲🇻", "MALDIVES"), "961": ("LB", "🇱🇧", "LEBANON"), "962": ("JO", "🇯🇴", "JORDAN"),
    "963": ("SY", "🇸🇾", "SYRIA"), "964": ("IQ", "🇮🇶", "IRAQ"), "965": ("KW", "🇰🇼", "KUWAIT"),
    "966": ("SA", "🇸🇦", "SAUDI ARABIA"), "967": ("YE", "🇾🇪", "YEMEN"), "968": ("OM", "🇴🇲", "OMAN"),
    "970": ("PS", "🇵🇸", "PALESTINE"), "971": ("AE", "🇦🇪", "UAE"), "972": ("IL", "🇮🇱", "ISRAEL"),
    "973": ("BH", "🇧🇭", "BAHRAIN"), "974": ("QA", "🇶🇦", "QATAR"), "975": ("BT", "🇧🇹", "BHUTAN"),
    "976": ("MN", "🇲🇳", "MONGOLIA"), "977": ("NP", "🇳🇵", "NEPAL"), "992": ("TJ", "🇹🇯", "TAJIKISTAN"),
    "993": ("TM", "🇹🇲", "TURKMENISTAN"), "994": ("AZ", "🇦🇿", "AZERBAIJAN"), "995": ("GE", "🇬🇪", "GEORGIA"),
    "996": ("KG", "🇰🇬", "KYRGYZSTAN"), "998": ("UZ", "🇺🇿", "UZBEKISTAN"),
}
ISO_TO_INFO = {v[0]: (v[1], v[2]) for v in COUNTRY_CODE_MAP.values()}

def get_country_code(country_name):
    if not country_name:
        return ""
    lower = country_name.lower()
    for code, (iso, flag, name) in COUNTRY_CODE_MAP.items():
        if lower == name.lower() or lower == iso.lower() or lower == code:
            return iso
    for code, (iso, flag, name) in COUNTRY_CODE_MAP.items():
        if lower in name.lower() or name.lower() in lower:
            return iso
    return country_name.upper()[:2]

def format_group_otp(entry):
    number = entry.get("number", "")
    otp_code = entry.get("otp", "")
    service_name = entry.get("service", "Unknown")
    country_raw = entry.get("country", entry.get("country_code", "?"))
    country_iso = entry.get("country_code", "")
    if not country_iso and country_raw:
        country_iso = get_country_code(country_raw) or "??"
    
    # Country emoji from group_emojis or DEFAULT_EMOJIS
    country_emoji_id = None
    if country_iso:
        row = db_fetch_one("SELECT emoji_id FROM group_emojis WHERE type='country' AND key=?", (country_iso.upper(),))
        if not row:
            row = db_fetch_one("SELECT emoji_id FROM group_emojis WHERE type='country' AND key=?", (country_iso.lower(),))
        if row and row[0]:
            country_emoji_id = row[0]
    if not country_emoji_id and country_iso and country_iso.lower() in DEFAULT_EMOJIS["countries"]:
        country_emoji_id = DEFAULT_EMOJIS["countries"][country_iso.lower()]
    if not country_emoji_id and country_raw and country_raw.lower() in DEFAULT_EMOJIS["countries"]:
        country_emoji_id = DEFAULT_EMOJIS["countries"][country_raw.lower()]
    
    flag_fallback = ISO_TO_INFO.get(country_iso, ("🏳", ""))[0] if country_iso else "🏳"
    if country_emoji_id:
        country_display = f'<tg-emoji emoji-id="{country_emoji_id}">{flag_fallback}</tg-emoji><b>{country_iso}</b>'
    else:
        country_display = f'{flag_fallback}<b>{country_iso}</b>'
    
    # Service emoji from group_emojis or DEFAULT_EMOJIS
    service_emoji_id = None
    row = db_fetch_one("SELECT emoji_id FROM group_emojis WHERE type='service' AND key=?", (service_name.lower(),))
    if row and row[0]:
        service_emoji_id = row[0]
    if not service_emoji_id and service_name.lower() in DEFAULT_EMOJIS["services"]:
        service_emoji_id = DEFAULT_EMOJIS["services"][service_name.lower()]
    if service_emoji_id:
        service_display = f'<tg-emoji emoji-id="{service_emoji_id}">🔧</tg-emoji>'
    else:
        service_display = f'#{service_name.capitalize()}'
    
    # Masked number with separator
    clean = number.replace('+', '').replace(' ', '').strip()
    if len(clean) >= 9:
        prefix, suffix = clean[:5], clean[-4:]
    else:
        prefix, suffix = clean, ""
    separator_tag = f'<tg-emoji emoji-id="{EMOJI_SEPARATOR}">➖</tg-emoji>'
    if suffix:
        masked = f'<b>+{prefix}{separator_tag}{suffix}</b>'
    else:
        masked = f'<b>+{clean}</b>'
    
    prefix_tag = f'<tg-emoji emoji-id="{EMOJI_PREFIX}">🤖</tg-emoji>'
    text = f"{prefix_tag} {country_display} | {service_display} {masked}"
    
    # Buttons (OTP copy, CHANNEL, BOT)
    otp_btn = InlineKeyboardButton(
        "𝐎𝐓𝐏",
        copy_text=CopyTextButton(text=otp_code),
        style=KBS.SUCCESS,
        icon_custom_emoji_id=EMOJI_OTP_BUTTON
    )
    channel_btn = InlineKeyboardButton(
        "𝐂𝐇𝐀𝐍𝐍𝐄𝐋", url=CHANNEL_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=EMOJI_CHANNEL_BUTTON
    )
    bot_btn = InlineKeyboardButton(
        "𝐁𝐎𝐓", url=BOT_URL,
        style=KBS.PRIMARY,
        icon_custom_emoji_id=EMOJI_BOT_BUTTON
    )
    keyboard = InlineKeyboardMarkup([[otp_btn], [channel_btn, bot_btn]])
    return text, keyboard

# ==================== OTP API MONITOR (DM + GROUP) ====================
async def monitor_otp_api(context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(f"{OTP_API_URL}?token={OTP_API_TOKEN}", timeout=10)
        if response.status_code != 200:
            return
        data = response.json()
        if data.get("status") != "success":
            return
        otps = data.get("data", {}).get("otps", [])
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        active_rows = db_fetch_all(
            "SELECT number, user_id, country, assigned_date FROM numbers WHERE status='active' AND expiry_time > ?",
            (now_str,))
        num_map = {}
        for num, uid, country, assigned in active_rows:
            clean = num.replace('+', '')
            num_map.setdefault(clean, []).append((uid, country, assigned))
        
        for otp_entry in otps:
            number = otp_entry.get("number", "")
            otp_code = otp_entry.get("otp", "")
            service_name = otp_entry.get("service", "Unknown")
            otp_timestamp_str = otp_entry.get("timestamp", now_str)
            message = otp_entry.get("message", "")[:200]
            
            if not number or not otp_code:
                continue
            
            # Duplicate check (0.5s) for both group and DM
            if is_duplicate_otp(number, otp_code, otp_timestamp_str):
                continue
            
            # Insert a record into otps for group duplicate tracking (user_id = 0 for group)
            db_exec("INSERT INTO otps (number, otp, message, timestamp, forwarded, user_id) VALUES (?,?,?,?,1,?)",
                    (number, otp_code, message, otp_timestamp_str, 0))
            
            # ---- SEND TO GROUP ----
            if GROUP_ID:
                try:
                    grp_text, grp_kb = format_group_otp({
                        "number": number,
                        "otp": otp_code,
                        "service": service_name,
                        "country_code": otp_entry.get("country_code", ""),
                        "country": otp_entry.get("country", "")
                    })
                    await context.bot.send_message(chat_id=GROUP_ID, text=grp_text, parse_mode="HTML", reply_markup=grp_kb)
                except Exception as e:
                    print(f"Group OTP failed: {e}")
            
            # ---- SEND TO DM (only to assigned users) ----
            if number in num_map:
                try:
                    otp_timestamp = datetime.strptime(otp_timestamp_str, "%Y-%m-%d %H:%M:%S")
                except:
                    otp_timestamp = now
                
                for user_id, country, assigned_date_str in num_map[number]:
                    if db_fetch_one("SELECT banned FROM users WHERE user_id=? AND banned=1", (user_id,)):
                        continue
                    try:
                        assigned_date = datetime.strptime(assigned_date_str, "%Y-%m-%d %H:%M:%S")
                    except:
                        assigned_date = now
                    if otp_timestamp < assigned_date:
                        continue
                    
                    country_data = get_country_info(country)
                    payout_str = country_data.get("payout", "0.001$")
                    try:
                        reward = parse_payout(payout_str)
                    except:
                        reward = 0.001
                    db_exec("UPDATE users SET balance = balance + ?, total_otp = total_otp + 1 WHERE user_id = ?",
                            (reward, user_id))
                    # Already inserted into otps above, so no need to re-insert
                    
                    flag_eid = country_data.get("emoji_id") or CUSTOM_EMOJIS["DEFAULT_FLAG"]
                    country_iso = country_data.get("iso", "").upper()
                    svc_row = db_fetch_one("SELECT emoji_id FROM services WHERE LOWER(name) = LOWER(?)", (service_name,))
                    svc_eid = svc_row[0] if svc_row and svc_row[0] else CUSTOM_EMOJIS["DEFAULT_SERVICE"]
                    
                    header = (
                        f'{emoji_tag("5278576134622056695", "🆕")} <b>NEW</b> '
                        f'{emoji_tag(flag_eid, "🏁")}<b>{country_iso} OTP ARRIVED</b>\n'
                        f'{emoji_tag("6204108584381322968", "📱")} <b>NUMBER</b>: +{number}\n'
                        f'{emoji_tag("5976327845696251345", "📲")} <b>APP</b>: {emoji_tag(svc_eid, "⚙️")} <b>{service_name}</b>\n'
                        f'💰 <b>BALANCE ADDED</b>: <code>+${reward}</code>{emoji_tag("5976788549658221281", "💵")}'
                    )
                    button = InlineKeyboardMarkup([[
                        InlineKeyboardButton(text=otp_code, copy_text=CopyTextButton(text=otp_code),
                                             style=KBS.SUCCESS, icon_custom_emoji_id=safe_icon("5330115548900501467"))
                    ]])
                    try:
                        await context.bot.send_message(user_id, header, reply_markup=button, parse_mode='HTML')
                    except Exception as e:
                        print(f"DM OTP failed for {user_id}: {e}")
    except Exception as e:
        print(f"OTP API Error: {e}")

async def cleanup_expired_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_exec("UPDATE numbers SET status = 'expired' WHERE expiry_time < ? AND status = 'active'", (now,))
        db_exec("UPDATE users SET current_number=NULL, current_country=NULL, current_service=NULL, number_expiry=NULL WHERE number_expiry < ?", (now,))
    except Exception as e:
        print(f"Cleanup Error: {e}")

# ==================== /country & /service COMMANDS (GROUP EMOJIS) ====================
async def group_country_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /country ISO|EMOJI_ID\nExample: /country GB|123456789")
        return
    parts = " ".join(context.args).split("|")
    if len(parts) != 2:
        await update.message.reply_text("Invalid format. Use ISO|EMOJI_ID")
        return
    iso = parts[0].strip().upper()
    eid = parts[1].strip()
    db_exec("INSERT OR REPLACE INTO group_emojis (type, key, emoji_id) VALUES ('country', ?, ?)", (iso, eid))
    # Also update DEFAULT_EMOJIS
    DEFAULT_EMOJIS["countries"][iso.lower()] = eid
    await update.message.reply_text(f"✅ Group country emoji for {iso} set to <code>{eid}</code>", parse_mode="HTML")

async def group_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /service NAME|EMOJI_ID\nExample: /service PayPal|123456789")
        return
    parts = " ".join(context.args).split("|")
    if len(parts) != 2:
        await update.message.reply_text("Invalid format. Use NAME|EMOJI_ID")
        return
    name = parts[0].strip().lower()
    eid = parts[1].strip()
    db_exec("INSERT OR REPLACE INTO group_emojis (type, key, emoji_id) VALUES ('service', ?, ?)", (name, eid))
    DEFAULT_EMOJIS["services"][name.lower()] = eid
    await update.message.reply_text(f"✅ Group service emoji for {name} set to <code>{eid}</code>", parse_mode="HTML")

# ==================== BOTTOM MENU TEXT ROUTERS ====================
async def send_get_number_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await ban_check(update, context): return
    ensure_user(user_id, update.effective_user.username, update.effective_user.first_name)
    db_exec("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    await update.message.reply_text("Select a Service:", reply_markup=services_keyboard())

async def send_balance_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await ban_check(update, context): return
    ensure_user(user_id, update.effective_user.username, update.effective_user.first_name)
    user = db_fetch_one("SELECT first_name, balance, withdrawn, total_otp FROM users WHERE user_id = ?", (user_id,))
    if not user:
        return
    first_name, balance, withdrawn, total_otp = user
    balance = balance or 0.0
    withdrawn = withdrawn or 0.0
    total_otp = total_otp or 0
    text = (
        f'{emoji_tag("4958534696645428119", "👤")} {first_name} YOUR DETAILS {emoji_tag("4958506272551863292", "📋")}\n'
        f'------------------------------------------------\n'
        f'{emoji_tag("5197269100878907942", "🆔")} USER ID: {user_id}\n'
        f'{emoji_tag("4958926882994127612", "💰")} BALANCE: ${balance:.3f}\n'
        f'{emoji_tag("5445221832074483553", "💸")} WITHDRAWED: ${withdrawn:.3f}\n'
        f'{emoji_tag("4958534696645428119", "⚠️")} MINIMUM WITHDRAW: $0.1\n'
        f'{emoji_tag("5197288647275071607", "📨")} TOTAL OTP: {total_otp}'
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"WITHDRAW", callback_data="withdraw", style=KBS.SUCCESS,
                             icon_custom_emoji_id=safe_icon("5445353829304387411"))
    ]])
    await update.message.reply_text(text, reply_markup=kb, parse_mode='HTML')

async def send_support_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("CONTACT SUPPORT\n\n━━━━━━━━━━━━━━━━━━━━\nContact admin directly.\n\nDeveloper: SR NUMBER HUB", reply_markup=support_keyboard())

async def send_admin_panel_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id): await update.message.reply_text("Unauthorized!"); return
    admin_mode[user_id] = True
    admin_panel_state[user_id] = "main"
    await update.message.reply_text("ADMIN PANEL\n\nDeveloper: SR NUMBER HUB", reply_markup=admin_panel_keyboard())

# ==================== GENERIC TEXT HANDLER ====================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if await handle_admin_text(update, context): return
    user_id = update.effective_user.id
    if await ban_check(update, context): return
    text = update.message.text.strip()
    if text == BTN_GET_NUMBER: await send_get_number_panel(update, context)
    elif text == BTN_BALANCE: await send_balance_panel(update, context)
    elif text == BTN_SUPPORT: await send_support_panel(update, context)
    elif text == BTN_ADMIN: await send_admin_panel_msg(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

# ==================== MAIN ====================
def main():
    print("🔥 SR NUMBER HUB Bot STARTING...")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("enteradmin", enter_admin_command))
    application.add_handler(CommandHandler("exitadmin", exit_admin_command))
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("removeadmin", remove_admin_command))
    application.add_handler(CommandHandler("country", group_country_command))
    application.add_handler(CommandHandler("service", group_service_command))
    application.add_handler(CallbackQueryHandler(service_selection_callback, pattern="^svc_sel\|"))
    application.add_handler(CallbackQueryHandler(country_selection_callback, pattern="^cnt_sel\|"))
    application.add_handler(CallbackQueryHandler(back_to_services_callback, pattern="^back_to_services$"))
    application.add_handler(CallbackQueryHandler(country_add_service_callback, pattern="^cnt_add_svc\|"))
    application.add_handler(CallbackQueryHandler(next_number_callback, pattern="^next_number$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_del\|"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(service_callback, pattern="^service_"))
    application.add_handler(CallbackQueryHandler(service_callback, pattern="^service_set_emoji$"))
    application.add_handler(CallbackQueryHandler(service_callback, pattern=r"^service_emoji_set\|"))
    application.add_handler(CallbackQueryHandler(balance_menu_callback, pattern="^menu_balance$"))
    application.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^withdraw$"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    application.add_handler(CallbackQueryHandler(toggle_cc_callback, pattern="^toggle_cc$"))
    # User Manager
    application.add_handler(CallbackQueryHandler(lambda u,c: user_manager_menu(u,c,u.callback_query.from_user.id), pattern="^admin_user_manager$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: um_search_prompt(u,c,u.callback_query.from_user.id), pattern="^um_search$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: send_user_list_file(u,c), pattern="^um_download$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: um_stats(u,c), pattern="^um_stats$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: um_edit_balance_prompt(u.callback_query, u.callback_query.from_user.id, c), pattern=r"^um_editbal\|"))
    application.add_handler(CallbackQueryHandler(lambda u,c: um_ban_toggle(u.callback_query, u.callback_query.from_user.id, c), pattern=r"^um_ban\|"))
    application.add_handler(CallbackQueryHandler(lambda u,c: user_manager_menu(u,c,u.callback_query.from_user.id), pattern="^um_back$"))
    # Database
    application.add_handler(CallbackQueryHandler(lambda u,c: database_menu(u,c,u.callback_query.from_user.id), pattern="^admin_database$"))
    application.add_handler(CallbackQueryHandler(db_download, pattern="^db_download$"))
    application.add_handler(CallbackQueryHandler(db_upload_prompt, pattern="^db_upload$"))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_db_upload), group=0)
    # Broadcast & file upload
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_text), group=1)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_error_handler(error_handler)
    
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(monitor_otp_api, interval=OTP_POLL_INTERVAL, first=OTP_POLL_INTERVAL)
        job_queue.run_repeating(cleanup_expired_job, interval=60, first=60)
    
    print(f"✅ Multi-admin, User Manager, Broadcast, Group OTP, Database active")
    print("🔄 Starting polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
