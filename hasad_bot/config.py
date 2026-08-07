#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration module for HASAD Bot
دعم متعدد لمفاتيح Groq و Gemini
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

# ==============================================================================
# تحميل متغيرات البيئة (يجب أن يكون أول شيء - قبل قراءة أي متغير!)
# ==============================================================================

env_path = Path(".env")
if env_path.exists():
    try:
        with open(env_path, 'rb') as f:
            raw_data = f.read()

        content = None
        for encoding in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
            try:
                content = raw_data.decode(encoding)
                print(f"✅ Successfully read .env with {encoding}")
                break
            except UnicodeDecodeError:
                continue

        if content:
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value
    except Exception as e:
        print(f"Warning: Could not read .env file: {e}")

# ==============================================================================
# مسارات الملفات والمجلدات
# ==============================================================================


# config.py - أضف هذه الأسطر

# ==============================================================================
# إعدادات حل الاختبارات (Exams)
# ==============================================================================
# config.py

# ==============================================================================
# إعدادات حل الاختبارات (Exams)
# ==============================================================================

EXAM_FEATURE_BETA = True  # <- غير إلى False عندما تصبح الميزة مستقرة

# كم واجب يستهلكه الاختبار الواحد للمشتركين (من رصيد الاشتراك)
EXAM_COST_IN_HOMEWORKS = 2  # اختبار واحد = 2 واجبات
# عدد المحاولات المجانية لحل الاختبارات للمستخدمين غير المشتركين
FREE_EXAM_ATTEMPTS = 3  # مثلاً 3 محاولات فقط

# الحد الأقصى للمحاولات للمشتركين (0 = غير محدود)

SUBSCRIBED_EXAM_LIMIT = 0  # 0 يعني غير محدود

try:
    DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "9000"))
except ValueError:
    DASHBOARD_PORT = 9000

# Cache TTL (ثوانٍ) - Web Dashboard L1 cache
try:
    DASHBOARD_CACHE_TTL = float(os.environ.get("DASHBOARD_CACHE_TTL", "15"))
except ValueError:
    DASHBOARD_CACHE_TTL = 15.0

# ==============================================================================
# Dashboard Security (جديد - Authentication & Session)
# ==============================================================================
# هذه الإعدادات إجبارية - البوت لن يعمل بدونها!
# شغّل: python generate_dashboard_password.py لتوليد القيم

DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD_HASH = os.environ.get("DASHBOARD_PASSWORD_HASH", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

# Session Duration
try:
    DASHBOARD_JWT_EXPIRY_HOURS = int(os.environ.get("DASHBOARD_JWT_EXPIRY_HOURS", "8"))
except ValueError:
    DASHBOARD_JWT_EXPIRY_HOURS = 8

try:
    DASHBOARD_JWT_ABSOLUTE_HOURS = int(os.environ.get("DASHBOARD_JWT_ABSOLUTE_HOURS", "24"))
except ValueError:
    DASHBOARD_JWT_ABSOLUTE_HOURS = 24

# Brute Force Protection
try:
    DASHBOARD_MAX_LOGIN_ATTEMPTS = int(os.environ.get("DASHBOARD_MAX_LOGIN_ATTEMPTS", "5"))
except ValueError:
    DASHBOARD_MAX_LOGIN_ATTEMPTS = 5

try:
    DASHBOARD_LOGIN_WINDOW_SECONDS = int(os.environ.get("DASHBOARD_LOGIN_WINDOW_SECONDS", "300"))
except ValueError:
    DASHBOARD_LOGIN_WINDOW_SECONDS = 300

try:
    DASHBOARD_LOGIN_LOCKOUT_SECONDS = int(os.environ.get("DASHBOARD_LOGIN_LOCKOUT_SECONDS", "900"))
except ValueError:
    DASHBOARD_LOGIN_LOCKOUT_SECONDS = 900

# IP Whitelist (comma-separated)
DASHBOARD_ALLOWED_IPS = [
    ip.strip() for ip in os.environ.get("DASHBOARD_ALLOWED_IPS", "").split(",")
    if ip.strip()
]

# Cookie Security
DASHBOARD_COOKIE_SECURE = os.environ.get("DASHBOARD_COOKIE_SECURE", "false").lower() == "true"


# ✅ مجلد البيانات الرئيسي (خارج مجلد المشروع)
# الترتيب:
#   1) HASAD_DATA_DIR من الـ env (override صريح — يُستخدم كما هو حتى لو لم يوجد)
#   2) <project_root>/Hasad_Data (sibling portable — يُنشأ إن لم يوجد)
#   3) P:\Hasad_Data (backward compat — إن وُجد)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

if os.environ.get("HASAD_DATA_DIR"):
    DATA_DIR = Path(os.environ["HASAD_DATA_DIR"])
else:
    _SIBLING = _PROJECT_ROOT.parent / "Hasad_Data"
    _P_DRIVE = Path(r"P:\Hasad_Data")
    if _SIBLING.exists() and _SIBLING.is_dir():
        DATA_DIR = _SIBLING
    elif _P_DRIVE.exists() and _P_DRIVE.is_dir():
        DATA_DIR = _P_DRIVE
    else:
        DATA_DIR = _SIBLING

# مجلد قاعدة المعرفة
KNOWLEDGE_DIR = DATA_DIR / "knowledge_db"

# مجلد اللوج
LOG_DIR = DATA_DIR / "logers"
ADMIN_LOG_DIR = LOG_DIR / "admin"

# إنشاء المجلدات
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_LOG_DIR.mkdir(parents=True, exist_ok=True)

# مجلدات فرعية داخل knowledge_db
IMAGES_DIR = KNOWLEDGE_DIR / "images"
STORAGE_DIR = KNOWLEDGE_DIR / "storage"
DEBUG_DIR = KNOWLEDGE_DIR / "admin_debug_images"

IMAGES_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)
DEBUG_DIR.mkdir(exist_ok=True)

# مسارات الملفات داخل knowledge_db
DB_FILE = KNOWLEDGE_DIR / "hasad.db"
HARVEST_DB = KNOWLEDGE_DIR / "harvest_cv.db"
KNOWLEDGE_DB = KNOWLEDGE_DIR / "hasad_knowledge_base123.db"
CRYPTO_KEY = KNOWLEDGE_DIR / ".crypto_key"

# سجلات الأدمن (في logers/admin)
ACCOUNTS_LOG = ADMIN_LOG_DIR / "admin_accounts_details.log"
AUDIT_LOG = ADMIN_LOG_DIR / "admin_audit.log"

# ==============================================================================
# تحميل متغيرات البيئة (تم نقله للأعلى)
# ==============================================================================


# ==============================================================================
# إعدادات البوت
# ==============================================================================

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
    print("Warning: ADMIN_ID must be a number")

ADMIN_DARS_USER = os.environ.get("DEFAULT_USER", "")
ADMIN_DARS_PASS = os.environ.get("DEFAULT_PASS", "")
BACKUP_CHANNEL_ID = os.environ.get("BACKUP_CHANNEL_ID", "")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "hasad2026")
try:
    MAX_FULL_ADMINS = int(os.environ.get("MAX_FULL_ADMINS", "5"))
except ValueError:
    MAX_FULL_ADMINS = 5

# Playwright: افتراضياً False ليُعرض المتصفح للمستخدم (يمكن تغييره عبر PLAYWRIGHT_HEADLESS=true)
PLAYWRIGHT_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "false").lower() in ("1", "true", "yes")

# تعطيل الرادار مؤقتاً (لتفادي الأخطاء المتكررة)
RADAR_ENABLED = os.environ.get("RADAR_ENABLED", "false").lower() in ("1", "true", "yes")

# بيئة التشغيل (production | test | ...) وسماح العمليات ذات الأثر الخارجي في الاختبار
APP_ENV = os.environ.get("APP_ENV", "production").strip().lower() or "production"
ALLOW_LIVE_TESTS = os.environ.get("ALLOW_LIVE_TESTS", "").strip().lower() in ("1", "true", "yes")

# ==============================================================================
# GROQ Keys
# ==============================================================================
groq_keys = []

for key_name, value in os.environ.items():
    if key_name.startswith("GROQ_KEY_"):
        if value and value.strip():
            groq_keys.append(value.strip())

if not groq_keys:
    groq_keys_env = os.environ.get("GROQ_KEYS", "")
    if groq_keys_env:
        groq_keys = [k.strip() for k in groq_keys_env.split(",") if k.strip()]

if not groq_keys:
    groq_key_old = os.environ.get("GROQ_KEY", "")
    if groq_key_old:
        groq_keys.append(groq_key_old)

GROQ_KEYS = groq_keys
GROQ_KEY = GROQ_KEYS[0] if GROQ_KEYS else ""

# ==============================================================================
# Gemini Keys
# ==============================================================================
gemini_keys = []

for key_name, value in os.environ.items():
    if key_name.startswith("GEMINI_KEY_"):
        if value and value.strip():
            gemini_keys.append(value.strip())

if not gemini_keys:
    gemini_keys_env = os.environ.get("GEMINI_KEYS", "")
    if gemini_keys_env:
        gemini_keys = [k.strip() for k in gemini_keys_env.split(",") if k.strip()]

GEMINI_KEYS = gemini_keys

# ==============================================================================
# Constants
# ==============================================================================
DEFAULT_FREE_ATTEMPTS = 5
REFERRAL_BONUS_ATTEMPTS = 4

# Conversation States

# config.py - أضف هذه الأسطر مع بقية الحالات

(
    MAIN_MENU,
    ADMIN_PANEL,
    AWAIT_RENEW_USER,
    AWAIT_RENEW_DAYS,
    AWAIT_REVOKE_USER,
    AWAIT_GENKEY_COUNT,
    AWAIT_LOGIN_USERNAME,
    AWAIT_LOGIN_PASSWORD,
    AWAIT_ADD_ADMIN,
    AWAIT_SUPPORT_MSG,
    AWAIT_ADMIN_REPLY,
    AWAIT_BROADCAST_MSG,
    AWAIT_CUSTOM_REASON,
    AWAIT_CUSTOM_DAYS,
    AWAIT_BROADCAST_TARGET,
    AWAIT_ADD_HW_ID,
    AWAIT_ADD_HW_COUNT,
    AWAIT_ADD_HW_CONFIRM,
    AWAIT_ADD_HW_CHOICE,
    AWAIT_BROADCAST_CONFIRM,
    # Reseller states
    AWAIT_RESELLER_CREDIT_AMOUNT,
    AWAIT_RESELLER_CREDIT_USER,
    AWAIT_RESELLER_ACTIVATE_USER,
    AWAIT_RESELLER_PRICES,
    # Admin panel states
    AWAIT_ADMIN_PASSWORD,
    AWAIT_ADMIN_PANEL_USER_ID,
) = range(26)

class Config:
    """Application configuration - دعم متعدد المفاتيح لـ Groq و Gemini"""
    
    def __init__(self):
        self.bot_token = BOT_TOKEN
        self.admin_id = ADMIN_ID
        self.admin_dars_user = ADMIN_DARS_USER
        self.admin_dars_pass = ADMIN_DARS_PASS
        self.dashboard_port = DASHBOARD_PORT
        self.dashboard_cache_ttl = DASHBOARD_CACHE_TTL

        # Dashboard Security (جديد)
        self.dashboard_username = DASHBOARD_USERNAME
        self.dashboard_password_hash = DASHBOARD_PASSWORD_HASH
        self.jwt_secret = JWT_SECRET
        self.jwt_expiry_hours = DASHBOARD_JWT_EXPIRY_HOURS
        self.jwt_absolute_hours = DASHBOARD_JWT_ABSOLUTE_HOURS
        self.max_login_attempts = DASHBOARD_MAX_LOGIN_ATTEMPTS
        self.login_window_seconds = DASHBOARD_LOGIN_WINDOW_SECONDS
        self.login_lockout_seconds = DASHBOARD_LOGIN_LOCKOUT_SECONDS
        self.dashboard_allowed_ips = DASHBOARD_ALLOWED_IPS
        self.dashboard_cookie_secure = DASHBOARD_COOKIE_SECURE

        # Groq Keys (متعددة)
        self.groq_keys = GROQ_KEYS.copy() if GROQ_KEYS else []
        self.groq_key = GROQ_KEY
         
        # Gemini Keys (متعددة)
        self.gemini_keys = GEMINI_KEYS.copy() if GEMINI_KEYS else []
         
        self.backup_channel_id = BACKUP_CHANNEL_ID
        self.admin_password = ADMIN_PASSWORD
        self.max_full_admins = MAX_FULL_ADMINS
        self.free_attempts = DEFAULT_FREE_ATTEMPTS
        self.referral_bonus = REFERRAL_BONUS_ATTEMPTS

        # Playwright / Radar
        self.playwright_headless = PLAYWRIGHT_HEADLESS
        self.radar_enabled = RADAR_ENABLED

        # بيئة التشغيل وسماح الاختبارات الحية
        self.app_env = APP_ENV
        self.allow_live_tests = ALLOW_LIVE_TESTS
         
        # ✅ كلمة مرور النسخ الاحتياطي - MUST be set in .env
        self.backup_password = os.environ.get("BACKUP_PASSWORD", "")
        if not self.backup_password:
            print("❌ CRITICAL: BACKUP_PASSWORD not set in .env file!")
            sys.exit(1)
        
        # ✅ المسارات
        self.data_dir = KNOWLEDGE_DIR
        self.knowledge_dir = KNOWLEDGE_DIR
        self.log_dir = LOG_DIR
        self.images_dir = IMAGES_DIR
        self.storage_dir = STORAGE_DIR
        self.debug_dir = DEBUG_DIR
        
        # ✅ مسارات الملفات
        self.db_file = DB_FILE
        self.harvest_db = HARVEST_DB
        self.knowledge_db = str(KNOWLEDGE_DB)
        self.accounts_log = ACCOUNTS_LOG
        self.audit_log = AUDIT_LOG
       
                # ✅ ========== أضف هذا القسم (بالمسافات الصحيحة) ==========
        self.dirs = {
            'logs': Path(self.log_dir),                    # مجلد اللوجات
            'databases': Path(self.data_dir) / "databases", # مجلد قواعد البيانات
            'knowledge': Path(self.knowledge_dir),          # مجلد المعرفة
            'images': Path(self.images_dir),                # مجلد الصور
            'storage': Path(self.storage_dir),              # مجلد التخزين
            'backups': Path(self.data_dir) / "backups",     # مجلد النسخ الاحتياطي
        }
        
        # إنشاء المجلدات تلقائياً (هنا المسافات الصحيحة - داخل __init__)
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)




# Create config instance
config = Config()

# Validate critical config
if not config.bot_token:
    print("❌ CRITICAL ERROR: BOT_TOKEN is missing in .env file")
    sys.exit(1)

if not config.admin_id:
    print("❌ CRITICAL ERROR: ADMIN_ID is missing in .env file")
    sys.exit(1)

# ==============================================================================
# Validate Dashboard Security (جديد)
# ==============================================================================
# البوت لن يعمل بدون هذه الإعدادات - لا توجد قيم افتراضية!
# استخدم: python generate_dashboard_password.py لتوليد القيم

_dashboard_errors = []

if not config.dashboard_username:
    _dashboard_errors.append(
        "DASHBOARD_USERNAME غير معرّف في .env\n"
        "   ➜ أضف: DASHBOARD_USERNAME=your_username"
    )

if not config.dashboard_password_hash:
    _dashboard_errors.append(
        "DASHBOARD_PASSWORD_HASH غير معرّف في .env\n"
        "   ➜ شغّل: python generate_dashboard_password.py"
    )
elif not (config.dashboard_password_hash.startswith("$2b$") or
          config.dashboard_password_hash.startswith("$2a$")):
    _dashboard_errors.append(
        "DASHBOARD_PASSWORD_HASH لا يبدو كـ bcrypt hash صحيح\n"
        "   ➜ شغّل: python generate_dashboard_password.py"
    )

if not config.jwt_secret:
    _dashboard_errors.append(
        "JWT_SECRET غير معرّف في .env\n"
        "   ➜ أضف: JWT_SECRET=<32+ characters>\n"
        "   ➜ لتوليد قوي: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
elif len(config.jwt_secret) < 32:
    _dashboard_errors.append(
        f"JWT_SECRET قصير جداً ({len(config.jwt_secret)} حرف) - يجب 32 حرف على الأقل"
    )

if _dashboard_errors:
    print("\n" + "=" * 60)
    print("❌ أخطاء حرجة في إعدادات الداشبورد:")
    print("=" * 60)
    for err in _dashboard_errors:
        print(f"  • {err}")
    print("=" * 60)
    print("🛑 البوت لن يعمل حتى يتم إصلاح هذه الأخطاء!")
    print("=" * 60 + "\n")
    raise SystemExit(
        "Dashboard security not configured. "
        "Run: python generate_dashboard_password.py"
    )

# ==============================================================================
# طباعة معلومات التهيئة
# ==============================================================================
print(f"\n{'='*60}")
print(f"✅ Configuration loaded successfully")
print(f"{'='*60}")
print(f"📊 Admin ID: {config.admin_id}")
print(f"🤖 Bot Token: {config.bot_token[:15]}..." if config.bot_token else "❌ No token")
print(f"🔑 Groq Keys: {len(config.groq_keys)} loaded")
if config.groq_keys:
    for i, key in enumerate(config.groq_keys[:3], 1):
        print(f"   ├─ GROQ_KEY_{i}: {key[:20]}...{key[-10:]}")
    if len(config.groq_keys) > 3:
        print(f"   └─ ... and {len(config.groq_keys)-3} more")
print(f"✨ Gemini Keys: {len(config.gemini_keys)} loaded")
if config.gemini_keys:
    for i, key in enumerate(config.gemini_keys[:3], 1):
        print(f"   ├─ GEMINI_KEY_{i}: {key[:20]}...{key[-10:]}")
    if len(config.gemini_keys) > 3:
        print(f"   └─ ... and {len(config.gemini_keys)-3} more")
print(f"📁 Data Directory: {config.data_dir}")
print(f"📁 Knowledge Directory: {config.knowledge_dir}")
print(f"📁 Log Directory: {config.log_dir}")
print(f"📚 Knowledge DB: {config.knowledge_db}")
print(f"{'='*60}\n")