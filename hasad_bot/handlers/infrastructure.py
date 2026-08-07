"""
infrastructure.py - cross-cutting handler infrastructure.

This module gathers helpers and middleware that don't belong to a single
feature:

* ``RateLimiter`` + ``rate_limit`` decorator (anti-spam)
* ``PlaywrightError`` + ``safe_playwright_execute`` (Playwright error wrapper)
* ``check_access`` (subscription/access check used by feature handlers)
* ``log_any_message`` (per-message audit logging)
* ``_cancel_handler`` and ``error_handler`` (catch-all handlers)
* ``send_loading`` / ``update_loading`` (UX spinners for slow operations)

It must not import from any other ``hasad_bot.handlers`` submodule so it can
be the lowest layer in the handlers package.
"""
from __future__ import annotations

import asyncio
import functools
import time
from collections import defaultdict
from typing import Dict, List

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU
from hasad_bot.database import (
    is_admin,
    is_public_mode,
    is_subscribed,
    db_get_user,
    db_log,
    update_user_last_active,
    log_user_message,
)
from hasad_bot.logger import log_button_click
from hasad_bot.utils import kb_main, now_hijri
from hasad_bot.playwright_engine import _browser_pool


# ==============================================================================
# Rate Limiter (anti-spam)
# ==============================================================================

class RateLimiter:
    """Rate limiter for anti-spam protection"""

    def __init__(self, max_calls: int = 2, time_window: float = 1.0):
        self.max_calls = max_calls
        self.time_window = time_window
        self.user_calls: Dict[int, List[float]] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to make a call"""
        async with self.lock:
            now = time.time()
            # Remove old calls outside time window
            self.user_calls[user_id] = [
                ts for ts in self.user_calls[user_id]
                if now - ts < self.time_window
            ]

            if len(self.user_calls[user_id]) >= self.max_calls:
                return False

            self.user_calls[user_id].append(now)
            return True

    async def get_remaining(self, user_id: int) -> int:
        """Get remaining calls for user"""
        async with self.lock:
            now = time.time()
            self.user_calls[user_id] = [
                ts for ts in self.user_calls[user_id]
                if now - ts < self.time_window
            ]
            return max(0, self.max_calls - len(self.user_calls[user_id]))


# Global rate limiter instance
_rate_limiter = RateLimiter(max_calls=2, time_window=1.0)


def rate_limit(func):
    """Decorator to rate-limit handler functions"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0

        # Check if user is admin - bypass rate limit
        from hasad_bot.database import is_admin
        try:
            is_admin_user = await is_admin(user_id)
        except:
            is_admin_user = False

        if is_admin_user:
            return await func(update, context)

        # Check rate limit
        if not await _rate_limiter.is_allowed(user_id):
            remaining = await _rate_limiter.get_remaining(user_id)
            # جلب التاريخ الهجري الحالي ديناميكياً
            current_date = now_hijri()

            await update.message.reply_text(
                f"⏳ <b>تنبيه: سرعة الإرسال محدودة</b>\n\n"
                f"نرجو إرسال الطلبات بهدوء، الحد المسموح هو <b>أمرين لكل ثانية</b> فقط.\n\n"
                f"📅 {current_date}",
                parse_mode="HTML"
            )

            # اللوج يسجل التاريخ والوقت تلقائياً عند وقوع الحدث
            logger.warning(f"⚠️ [Rate Limit] المستخدم {user_id} تجاوز الحد المسموح | التاريخ: {current_date}")
            return

        return await func(update, context)

    return wrapper


# ==============================================================================
# Global Playwright exception wrapper
# ==============================================================================

class PlaywrightError(Exception):
    """Custom exception for Playwright errors"""
    pass


async def safe_playwright_execute(user_id: int, operation_name: str, operation_func, *args, **kwargs):
    """
    Execute Playwright operations with global exception handling
    """
    try:
        return await operation_func(*args, **kwargs)
    except Exception as e:
        error_msg = str(e).lower()

        # Categorize errors
        if "timeout" in error_msg or "timed out" in error_msg:
            logger.error(f"⏱️ Playwright timeout for user {user_id} | {operation_name} | 24 Shawwal 1447")
            return {
                "success": False,
                "error": "timeout",
                "message": "⏱️ انتهت مهلة الطلب. يرجى المحاولة مرة أخرى.",
                "user_message": "⏱️ **انتهت مهلة الاتصال!**\n"
                              f"🔄 جاري إعادة تشغيل النظام...\n"
                              f"📅 {now_hijri()}\n\n"
                              f"⏳ حاول مرة أخرى بعد 10 ثواني"
            }

        elif "browser" in error_msg or "context" in error_msg or "page" in error_msg:
            logger.error(f"🌐 Playwright browser crash for user {user_id} | {operation_name} | 24 Shawwal 1447")

            # Try to restart browser context
            try:
                from hasad_bot.playwright_engine import _browser_pool
                await _browser_pool.close_context(user_id, force=True)
                logger.info(f"♻️ Browser context recreated for user {user_id} | 24 Shawwal 1447")
            except:
                pass

            return {
                "success": False,
                "error": "browser_crash",
                "message": "🌐 تم إعادة تشغيل المتصفح",
                "user_message": "🔄 **جاري إعادة تشغيل النظام...**\n\n"
                              f"🌐 تم اكتشاف مشكلة في المتصفح\n"
                              f"✅ جاري إعادة التشغيل...\n"
                              f"📅 {now_hijri()}\n\n"
                              f"⏳ Please wait 5 seconds and try again"
            }

        elif "login" in error_msg or "credentials" in error_msg or "password" in error_msg:
            logger.error(f"🔐 Playwright login error for user {user_id} | {operation_name} | 24 Shawwal 1447")
            return {
                "success": False,
                "error": "login_failed",
                "message": "فشل تسجيل الدخول",
                "user_message": "🔐 **فشل تسجيل الدخول!**\n\n"
                              f"⚠️ تحقق من رقم المرور\n"
                              f"🔄 حاول مرة أخرى\n"
                              f"📅 {now_hijri()}"
            }

        else:
            logger.error(f"❌ Playwright error for user {user_id} | {operation_name} | {e} | 24 Shawwal 1447")
            return {
                "success": False,
                "error": "unknown",
                "message": str(e),
                "user_message": "❌ **حدث خطأ غير متوقع**\n\n"
                              f"🔄 جاري إعادة التشغيل...\n"
                              f"📅 {now_hijri()}\n\n"
                              f"⏳ Try again in 10 seconds"
            }


# ==============================================================================
# Access control
# ==============================================================================

async def check_access(update: Update, _: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من صلاحية المستخدم"""
    uid = update.effective_user.id
    if uid == config.admin_id or await is_admin(uid) or await is_public_mode():
        return True
    if await is_subscribed(uid):
        return True

    u = await db_get_user(uid)
    trials = u.get("free_attempts", 0) if u else 0

    if trials > 0:
        return True

    await update.message.reply_text(
        "🔒 <b>انتهت الواجبات المجانية</b>\n\n"
        f"📅 {now_hijri()}\n\n"
        "💎 استخدم الواجبات المجانية أو فعّل اشتراكك.",
        parse_mode=ParseMode.HTML,
    )
    await db_log(uid, "ACCESS_DENIED")
    return False


# ==============================================================================
# Per-message audit log
# ==============================================================================

async def log_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تسجيل أي رسالة يرسلها المستخدم - بدون إزعاج الإدارة"""

    try:
        if update.channel_post:
            return

        if not update.effective_user:
            return

        uid = update.effective_user.id
        name = update.effective_user.full_name or update.effective_user.first_name

        # ✅ قائمة الأزرار التي نتجاهلها
        ignored_buttons = ["👤 حسابي", "🤖 حل الواجبات", "🎁 شارك واربح", "🔗 ربط المنصة", "⭐ المتجر", "🆘 الدعم الفني", "🔙 الرئيسية", "👑 لوحة الإدارة"]

        # تحديد المحتوى
        if update.message.text:
            content = update.message.text
            msg_type = "text"
        elif update.message.photo:
            content = "[صورة]"
            msg_type = "photo"
        elif update.message.document:
            content = f"[ملف] {update.message.document.file_name}"
            msg_type = "document"
        else:
            content = "[نوع غير معروف]"
            msg_type = "unknown"

        # ✅ فقط سجل في قاعدة البيانات (بدون إرسال للإدارة)
        from hasad_bot.database import log_user_message
        await log_user_message(
            user_id=uid,
            user_name=name,
            message_text=content[:1000],
            message_type=msg_type,
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            is_response=False
        )

        # ✅ لا ترسل أي شيء للإدارة (تم التعطيل)

    except Exception as e:
        # سجل الخطأ فقط في اللوج
        logger.error(f"Error in log_any_message: {e}")


# ==============================================================================
# Cancel + global error handler
# ==============================================================================

async def _cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation - يدعم الرسائل النصية والأزرار المضمنة"""
    # تحديد user_id من update (نصي أو callback)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        uid = query.from_user.id
        message = query.message
    else:
        uid = update.effective_user.id
        message = update.message

    adm = await is_admin(uid)
    from hasad_bot.database import is_reseller as _is_reseller
    reseller = await _is_reseller(uid)
    context.user_data.clear()
    await update_user_last_active(uid)

    # إرسال الرد (لمنع تكرار الرسائل)
    if update.callback_query:
        await message.reply_text(
            "❌ تم الإلغاء.",
            reply_markup=kb_main(uid, admin=adm, is_reseller=reseller)
        )
        # حذف الأزرار من الرسالة القديمة
        await query.edit_message_reply_markup(reply_markup=None)
    else:
        await message.reply_text(
            "❌ تم الإلغاء.",
            reply_markup=kb_main(uid, admin=adm, is_reseller=reseller)
        )
    return MAIN_MENU


# ==============================================================================
# UX Loading Spinners
# ==============================================================================

# Animate dots: ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏
_SPIN_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']


async def send_loading(chat, text: str = "جاري المعالجة"):
    """
    Send a loading spinner message and return it.

    Usage::

        loading_msg = await send_loading(update.message.chat)
        # ... do slow work ...
        await update_loading(context.bot, loading_msg.chat_id,
                             loading_msg.message_id, "✅ تم!")

    Parameters
    ----------
    chat : Chat or Message
        The chat to send into (use ``update.message.chat``).
    text : str
        The base text shown beside the spinner.
    """
    spinner = _SPIN_CHARS[0]
    return await chat.reply_text(
        f"{spinner} <b>{text}...</b>\n\n"
        "⏳ يرجى الانتظار، قد يستغرق هذا بضع ثوانٍ.",
        parse_mode=ParseMode.HTML,
    )


async def update_loading(bot, chat_id: int, message_id: int, text: str,
                         done: bool = False):
    """
    Update a loading spinner message.

    Parameters
    ----------
    bot : Bot
        ``context.bot``
    chat_id, message_id : int
        Identifiers of the message to edit.
    text : str
        The new message text.
    done : bool
        If ``True``, shows a checkmark instead of the spinner.
    """
    prefix = "✅" if done else _SPIN_CHARS[int(time.time() * 3) % len(_SPIN_CHARS)]
    try:
        await bot.edit_message_text(
            f"{prefix} {text}",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass  # message unchanged or deleted — safe to ignore


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Unhandled error: {context.error}")
