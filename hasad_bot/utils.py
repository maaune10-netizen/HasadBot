#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility functions for HASAD Bot
"""

# Re-export datetime utilities
from hasad_bot.datetime_utils import (
    now_timestamp,
    now,
    now_riyadh,
    format_datetime,
    parse_datetime,
    datetime,
    timedelta
)

import base64
import hashlib
import os
import re
import time
import asyncio
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

# Try to import rich
try:
    from rich.console import Console
    from rich.text import Text
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

# Try to import hijri_converter
try:
    from hijri_converter import Hijri
    HIJRI_AVAILABLE = True
except ImportError:
    HIJRI_AVAILABLE = False

from hasad_bot.config import config




# utils.py - أضف هذا

import traceback

async def handle_error_safely(update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception, user_message: str = None):
    """
    معالج أخطاء موحد - يخفي التفاصيل التقنية عن المستخدم
    ويرسلها للإدارة فقط
    """
    uid = update.effective_user.id if update.effective_user else "UNKNOWN"
    name = update.effective_user.first_name if update.effective_user else "مستخدم"
    
    # تفاصيل الخطأ التقني الكامل
    error_trace = traceback.format_exc()
    error_type = type(error).__name__
    error_msg = str(error)
    
    # ✅ رسالة ودية للمستخدم
    friendly_msg = user_message or "⚠️ عذراً، حدث خطأ غير متوقع. فريق الدعم تم إبلاغه وسيتم حل المشكلة قريباً."
    
    # ✅ إرسال رسالة ودية للمستخدم
    try:
        await update.message.reply_text(friendly_msg, parse_mode="HTML")
    except:
        pass
    
    # ✅ إرسال التفاصيل التقنية للإدارة (في القناة أو للأدمن)
    admin_msg = (
        f"🚨 **خطأ تقني** 🚨\n\n"
        f"👤 المستخدم: {name} (ID: `{uid}`)\n"
        f"📅 الوقت: {now_hijri()}\n"
        f"🐞 نوع الخطأ: `{error_type}`\n"
        f"📝 الرسالة: `{error_msg[:200]}`\n\n"
        f"```\n{error_trace[:1500]}\n```"
    )
    
    # أرسل للإدارة
    try:
        await context.bot.send_message(
            chat_id=config.admin_id,
            text=admin_msg,
            parse_mode="Markdown"
        )
    except:
        pass
    
    # سجل في ملف الأخطاء
    logger.error(f"User {uid}: {error_type} - {error_msg}\n{error_trace}")










# ==============================================================================
# نظام أخطاء HASAD الموحد
# ==============================================================================

ERROR_CODES = {
    101: "بيانات الدخول غير صحيحة",
    102: "الحساب مقفل مؤقتاً",
    103: "انتهت صلاحية الحساب",
    104: "تم تسجيل الدخول من جهاز آخر",
    201: "فشل فتح المتصفح",
    202: "انتهت مهلة تحميل الصفحة",
    203: "عنصر غير موجود في الصفحة",
    204: "المتصفح مغلق بشكل غير متوقع",
    301: "السؤال غير موجود في قاعدة البيانات",
    302: "فشل حفظ السؤال في قاعدة المعرفة",
    303: "خطأ في قراءة قاعدة المعرفة",
    401: "فشل الاتصال بـ Groq API",
    402: "فشل الاتصال بـ Gemini API",
    403: "تم تجاوز حد الاستخدام اليومي",
    404: "مفتاح API غير صالح",
    501: "لم يتم ربط حساب المنصة",
    502: "انتهت الواجبات المجانية",
    503: "الاشتراك منتهي",
    504: "حسابك معلم (غير مسموح بحل الواجبات)",
    601: "خطأ في قاعدة البيانات",
    602: "تعارض في الجلسات",
    603: "نفاد الذاكرة",
    604: "خطأ غير متوقع",
}

def get_error_message(code: int) -> str:
    """الحصول على رسالة الخطأ من الرقم"""
    return ERROR_CODES.get(code, f"خطأ غير معروف ({code})")

def log_error_with_code(user_id: int, code: int, details: str = "") -> str:
    """تسجيل خطأ برقم موحد وإرجاع رسالة للمستخدم"""
    message = get_error_message(code)
    admin_trace(f"ERROR_{code}", f"{message} | {details}", user_id)
    
    try:
        from hasad_bot.logger import log_event
        asyncio.create_task(log_event(user_id, 'ERROR', f"CODE_{code}", 
                                      details={'message': message, 'details': details},
                                      success=False, error=message))
    except ImportError:
        logger.error(f"Error {code}: {message} | {details}")
    except Exception as e:
        logger.error(f"Failed to log error: {e}")
    

# ==============================================================================
# دالة للتوافق مع الكود القديم
# ==============================================================================

async def log_error_event(user_id: int, error_message: str, source: str = "SYSTEM"):
    """
    دالة للتوافق مع الكود القديم
    تسجل خطأ في قاعدة البيانات
    """
    try:
        from hasad_bot.logger import log_event
        
        # استخراج رقم الخطأ من الرسالة إذا كان موجود
        import re
        match = re.search(r'خطأ (\d+)', error_message)
        if match:
            code = int(match.group(1))
            message = get_error_message(code)
            await log_event(user_id, 'ERROR', f"CODE_{code}", 
                           details={'message': message, 'original': error_message},
                           success=False, error=error_message)
        else:
            await log_event(user_id, 'ERROR', source, 
                           success=False, error=error_message)
        
        admin_trace("ERROR", f"{source}: {error_message}", user_id)
        
    except Exception as e:
        logger.error(f"Failed to log error event: {e}")








# ==============================================================================
# دوال موحدة لقاعدة المعرفة (متوافقة مع ON--TEST--DB.py)
# ==============================================================================

import hashlib
import re

def generate_knowledge_uuid(question_text: str, img_src: str = "") -> str:
    """
    إنشاء UUID موحد للسؤال
    نفس الطريقة المستخدمة في ON--TEST--DB.py
    """
    clean_text = re.sub(r'\s+', ' ', question_text).strip() if question_text else ""
    
    # إذا كان هناك صورة
    if img_src:
        match = re.search(r'FileStorage/([^.]+)', img_src)
        if match:
            return match.group(1)
        return hashlib.md5(img_src.encode('utf-8')).hexdigest()
    
    # سؤال نصي
    if clean_text:
        text_hash = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
        return f"TXT_{text_hash}"
    
    return hashlib.md5(str(time.time()).encode()).hexdigest()


def clean_question_text(text: str) -> str:
    """تنظيف النص بنفس طريقة ON--TEST--DB.py"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def get_full_image_url(img_src: str, domain: str = "https://alamjad1.dars360.com") -> str:
    """تحويل رابط الصورة إلى رابط كامل"""
    if not img_src:
        return ""
    if img_src.startswith('http'):
        return img_src
    return f"{domain}{img_src}"












def get_current_hijri_date() -> str:
    """Get current Hijri date"""
    if HIJRI_AVAILABLE:
        try:
            hijri_date = Hijri.today()
            return f"{hijri_date.day} {hijri_date.month_name()} {hijri_date.year} AH"
        except Exception:
            pass
    # Fallback: Use the calculated date
    return gregorian_to_hijri(now())


def gregorian_to_hijri(g) -> str:  # بدون نوع (أسهل)    """Convert Gregorian to Hijri"""
    y, m, d = g.year, g.month, g.day
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    l = jdn - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    hm = (24 * l) // 709
    hd = l - (709 * hm) // 24
    hy = 30 * n + j - 30
    mn = ["محرم", "صفر", "ربيع الأول", "ربيع الثاني", "جمادى الأولى", "جمادى الآخرة",
          "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]
    return f"{hd} {mn[max(0, min(hm - 1, 11))]} {hy}هـ"


def now_hijri() -> str:
    """Get current Hijri date as string"""
    return gregorian_to_hijri(now())


def _get_crypto_key() -> bytes:
    """Get or create crypto key"""
    crypto_key_path = config.data_dir / ".crypto_key"
    if crypto_key_path.exists():
        return base64.b64decode(crypto_key_path.read_bytes())
    key = os.urandom(32)
    crypto_key_path.write_bytes(base64.b64encode(key))
    logger.info("🔑 Crypto key generated")
    return key


_CRYPTO_KEY = _get_crypto_key()


def encrypt_password(plain: str) -> str:
    """Encrypt password"""
    if not plain:
        return ""
    enc = bytes(b ^ _CRYPTO_KEY[i % len(_CRYPTO_KEY)] for i, b in enumerate(plain.encode()))
    return base64.b64encode(enc).decode()


def decrypt_password(enc_b64: str) -> str:
    """Decrypt password"""
    if not enc_b64:
        return ""
    try:
        enc = base64.b64decode(enc_b64.encode())
        return bytes(b ^ _CRYPTO_KEY[i % len(_CRYPTO_KEY)] for i, b in enumerate(enc)).decode()
    except Exception:
        return enc_b64


# utils.py - استبدل دالة safe_error_message بهذه

def safe_error_message(error: Exception, context: str = "") -> str:
    """
    تحويل أي خطأ تقني إلى رسالة ودية للمستخدم
    """
    error_str = str(error).lower()
    
    # ========== رسائل خطأ تسجيل الدخول ==========
    if "login" in error_str or "credentials" in error_str or "password" in error_str:
        return "🔐 **فشل تسجيل الدخول**\nتأكد من اسم المستخدم وكلمة المرور ثم حاول مرة أخرى."
    
    # ========== رسائل خطأ المتصفح ==========
    if "closed" in error_str or "browser" in error_str or "context" in error_str:
        return "🔒 **تم إغلاق الجلسة**\nيمكنك بدء جلسة جديدة بالضغط على 🤖 حل الواجبات"
    
    if "timeout" in error_str:
        return "⏰ **انتهت المهلة**\nيرجى التحقق من اتصال الإنترنت والمحاولة مرة أخرى."
    
    # ========== رسائل خطأ قاعدة البيانات ==========
    if "database" in error_str or "sqlite" in error_str:
        return "💾 **حدث خطأ في قاعدة البيانات**\nتم إبلاغ فريق الدعم، سيتم حل المشكلة قريباً."
    
    # ========== رسائل خطأ الذكاء الاصطناعي (حصاد AI) ==========
    if "groq" in error_str or "gemini" in error_str or "ai" in error_str or "api" in error_str:
        return "🤖 **حدث خطأ في ذكاء حصاد الاصطناعي**\n"
    
    # ========== رسائل خطأ عامة ==========
    return "⚠️ **حدث خطأ غير متوقع**\nفريق الدعم تم إبلاغه، سيتم حل المشكلة قريباً."

def admin_trace(step: str, detail: str, uid: str = "SYSTEM"):
    """Admin logging - تسجيل في مجلد logers/admin/"""
    try:
        from pathlib import Path
        from hasad_bot.config import config  # ✅ استيراد config
        import time  # ✅ استخدم time

# ✅ بعد
        from datetime import datetime  # أضف هذا الاستيراد داخل الدالة
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")  # ✅ بدون datetime
        hijri_date_str = get_current_hijri_date()
        
        # ✅ استخدم المسار من config بدلاً من المسار الثابت
        admin_log_dir = Path(config.log_dir) / "admin"
        admin_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = admin_log_dir / "admin_accounts_details.log"
        
        # Log to file
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{hijri_date_str}] [ID: {uid}] [{step}] >> {detail}\n")
        
        # Log to console with rich if available
        if RICH_AVAILABLE:
            text = Text()
            text.append(f"[{timestamp}] ", style="bold cyan")
            text.append(f"[{hijri_date_str}] ", style="bold green")
            text.append(f"[ID: {uid}] ", style="dim white")
            text.append(f"[{step}] ", style="bold magenta")
            text.append(">> ", style="bold yellow")
            text.append(f"{detail}", style="bold white")
            console.print(text)
        else:
            logger.debug(f"[{timestamp}] [{hijri_date_str}] [ID: {uid}] [{step}] >> {detail}")
            
    except Exception as e:
        logger.error(f"Logging failure: {e}")        

def generate_stable_uuid(text: str) -> str:
    """Generate stable UUID from text"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def clean_text_universal(text: str) -> str:
    """Clean text for comparison"""
    if not text:
        return ""
    try:
        text = str(text).lower()
        text = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e]', '', text)
        text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
        text = re.sub(r'[^\w\s\u0600-\u06FF]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception:
        return str(text).strip().lower()





# ==============================================================================
# تحويل الأخطاء التقنية إلى رسائل ودية للمستخدم
# ==============================================================================


def friendly_error_message(error: Exception) -> str:
    """تحويل الخطأ التقني إلى رسالة بسيطة للمستخدم"""
    error_str = str(error).lower()

    # أخطاء المتصفح والإغلاق
    if "closed" in error_str or "browser" in error_str or "context" in error_str:
        return "🔒 تم إغلاق المحرك بنجاح. يمكنك بدء جلسة جديدة متى شئت."
    if "timeout" in error_str:
        return "⏰ انتهت المهلة. يرجى التحقق من اتصال الإنترنت."
    if "selector" in error_str or "element" in error_str:
        return "🔍 لم يتم تحميل الصفحة بالكامل. حاول مرة أخرى."

    # أخطاء تسجيل الدخول
    if "login" in error_str or "credentials" in error_str:
        return "🔐 فشل تسجيل الدخول. تأكد من اسم المستخدم وكلمة المرور."

    # أخطاء قاعدة البيانات
    if "database" in error_str or "sqlite" in error_str:
        return "💾 حدث خطأ في نظام البيانات. يرجى المحاولة لاحقاً."

    # أخطاء API
    if "groq" in error_str or "gemini" in error_str:
        return "🤖 عطل مؤقت في خدمة الذكاء الاصطناعي. جارٍ الحل بطرق بديلة."

    # خطأ الإيقاف الطبيعي
    if "closed" in error_str:
        return "🛑 تم إيقاف المحرك. يمكنك البدء من جديد."

    # أي خطأ آخر
    return "⚠️ حدث خطأ غير متوقع. يرجى إعادة المحاولة."

# Banner texts
BANNER_TG = (
    "╔══════════════════════════════════════════╗\n"
    "║  ██╗  ██╗ █████╗ ███████╗ █████╗ ██████╗ ║\n"
    "║  ██║  ██║██╔══██╗██╔════╝██╔══██╗██╔══██╗║\n"
    "║  ███████║███████║███████╗███████║██║  ██║║\n"
    "║  ██╔══██║██╔══██║╚════██║██╔══██║██║  ██║║\n"
    "║  ██║  ██║██║  ██║███████║██║  ██║██████╔╝║\n"
    "║  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ ║\n"
    "║     V230  ◆ TELEGRAM UI EDITION           ║\n"
    "╚══════════════════════════════════════════╝"
)

BANNER_TERMINAL = (
    "\033[96m"
    "╔══════════════════════════════════════════════════════╗\n"
    "║  ██╗  ██╗ █████╗ ███████╗ █████╗ ██████╗             ║\n"
    "║  ██║  ██║██╔══██╗██╔════╝██╔══██╗██╔══██╗            ║\n"
    "║  ███████║███████║███████╗███████║██║  ██║            ║\n"
    "║  ██╔══██║██╔══██║╚════██║██╔══██║██║  ██║            ║\n"
    "║  ██║  ██║██║  ██║███████║██║  ██║██████╔╝            ║\n"
    "║  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝             ║\n"
    "║    V230  ◆ FULL ARCHITECTURE (UI+ENGINE)              ║\n"
    "╚══════════════════════════════════════════════════════╝"
    "\033[0m"
)


# Keyboard builders
# Keyboard builders
# utils.py

def kb_main(uid: int, admin: bool = False, is_subscribed: bool = False, is_reseller: bool = False):
    """Main keyboard"""
    from telegram import ReplyKeyboardMarkup
    from hasad_bot.config import config as _cfg
    
    btns = [
        ["🤖 حل الواجبات"],
        ["👤 حسابي", "🎁 شارك واربح", "⭐ المتجر"],
        ["🔗 ربط المنصة", "🆘 الدعم الفني"],
    ]
    
    # 🔑 لوحة الموزع — للموزعين والأدمنز (الادمن يدخل لوحة الادارة بـ /admin)
    if is_reseller or admin:
        btns.append(["🔑 لوحة الموزع"])
    
    # 👑 لوحة الإدارة — للمالك فقط (يدخل مباشرة بدون كلمة مرور)
    if uid == _cfg.admin_id:
        btns.append(["👑 لوحة الإدارة", "🏪 إدارة الموزعين"])
    
    return ReplyKeyboardMarkup(btns, resize_keyboard=True)

def kb_admin():
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup([
        ["📊 إحصائيات النظام", "📢 رسالة للكل"],
        ["➕ تجديد اشتراك", "🚫 إلغاء الأكسس"],
        ["🔑 توليد أكواد", "👥 قائمة المستخدمين"],
        ["👤 إضافة أدمن", "🏪 إدارة الموزعين"],
        ["💰 شحن رصيد أدمن", "👥 قائمة الأدمنز"],
        ["🔑 استخراج بيانات المنصة"],
        ["➕ إضافة واجبات"],
        ["🗑️ حذف أدمن", "🔙 الرئيسية"],
    ], resize_keyboard=True)