"""
onboarding.py - توجيه المستخدمين لربط المنصة.

المشكلة: كثير من المستخدمين يجون للبوت، يستكشفون الأزرار، لكن ما يربطون
حساب المنصة. يخسرون تجربة البوت الحقيقية.

الحل:
1. is_user_linked(uid) - هل المستخدم ربط حسابه
2. build_link_nudge() - يبني رسالة + كيبورد للتذكير
3. start command - لو ما ربط، يعرض الندج
4. solve_homework - لو ما ربط، يرفض ويعرض الندج
5. announcement: link_reminder يومي
"""
from __future__ import annotations

import time
from typing import Optional, Tuple, List

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from hasad_bot.config import config
from hasad_bot.database import db_get_user
from hasad_bot.utils import now_hijri, admin_trace


# ==============================================================================
# كشف حالة الربط
# ==============================================================================

async def is_user_linked(uid: int) -> bool:
    """هل المستخدم ربط حسابه بالمنصة (dars360)؟"""
    user = await db_get_user(uid)
    if not user:
        return False
    dars_user = user.get("dars360_user") or ""
    dars_pass = user.get("dars360_pass") or ""
    return bool(dars_user.strip()) and bool(dars_pass.strip())


async def get_link_info(uid: int) -> dict:
    """معلومات تفصيلية عن ربط المستخدم."""
    user = await db_get_user(uid)
    if not user:
        return {"exists": False, "linked": False, "user": None, "pass": None}
    return {
        "exists": True,
        "linked": await is_user_linked(uid),
        "user": user.get("dars360_user") or "",
        "pass": "***" if user.get("dars360_pass") else "",
    }


# ==============================================================================
# رسائل الندج (link nudge)
# ==============================================================================

# الرسالة الرئيسية — تظهر في كل مكان المستخدم يحتاج ربط
def build_link_nudge_message(
    user_name: str = "",
    free_attempts: int = 0,
    is_subscribed: bool = False,
    context: str = "general",  # "general" | "solving" | "first_time"
) -> str:
    """
    يبني رسالة الندج حسب السياق.

    Args:
        user_name: اسم المستخدم
        free_attempts: عدد المحاولات المجانية المتبقية
        is_subscribed: هل عنده اشتراك ساري
        context: متى تُعرض الرسالة
    """
    greeting = f"أهلاً {user_name}! " if user_name else "أهلاً! "

    if context == "first_time":
        body = f"""{greeting}👋

🎉 <b>أهلاً بك في حصاد!</b>

أنا بوتك الذكي لحل الواجبات بالذكاء الاصطناعي 🤖⚡

🔗 <b>قبل ما نبدأ، اربط حسابك بالمنصة:</b>

عشان أقدر أحل واجباتك، أحتاج بيانات الدخول لمنصة مدرستك (dars360.com).

✅ <b>الربط:</b>
• يوزرنيم المنصة + كلمة المرور
• مرة واحدة فقط — ما تحتاج تعيدها
• مشفّرة بشكل آمن في قاعدة البيانات

⏱️ <b>العملية تستغرق 30 ثانية فقط</b>

🎁 <b>عندك {free_attempts} واجبات مجانية</b> بانتظارك بعد الربط!"""
    elif context == "solving":
        body = f"""🔗 <b>اربط حساب المنصة أولاً!</b>

عشان أقدر أحل واجباتك، أحتاج بيانات الدخول لمنصة المدرسة.

✅ <b>ما تحتاج تسويه مرة ثانية:</b>
- يوزرنيم المنصة (اللي تدخل فيه على dars360.com)
- كلمة المرور

⏱️ <b>الربط يستغرق 30 ثانية فقط</b>"""
    else:  # general
        if is_subscribed:
            extra = f"📦 لديك اشتراك ساري — حان وقت الاستفادة منه!"
        elif free_attempts > 0:
            extra = f"🎁 عندك {free_attempts} واجبات مجانية بانتظارك!"
        else:
            extra = "🚀 ابدأ رحلتك مع حصاد!"

        body = f"""🔗 <b>اربط حساب المنصة!</b>

{extra}

عشان أقدر أحل واجباتك، أحتاج بيانات الدخول لمنصة المدرسة.

👇 <b>اضغط الزر بالأسفل:</b>"""

    return body


def build_link_nudge_keyboard(
    include_help: bool = True,
    include_skip: bool = False,
) -> InlineKeyboardMarkup:
    """كيبورد الندج."""
    buttons = [
        [InlineKeyboardButton("🔗 ربط المنصة الآن", callback_data="cmd_login")],
    ]
    if include_help:
        buttons.append([InlineKeyboardButton("💡 علشان إيش؟", callback_data="link_help")])
    if include_skip:
        buttons.append([InlineKeyboardButton("⏭️ لاحقاً", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


# ==============================================================================
# handlers: callback_data = "link_help" | "link_now"
# ==============================================================================

async def cb_link_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شرح ليش الربط مطلوب."""
    q = update.callback_query
    await q.answer()

    text = (
        "💡 <b>علشان إيش نطلب ربط المنصة؟</b>\n\n"

        "🤖 <b>كيف يعمل حصاد؟</b>\n"
        "1. تسجل دخولك في منصتنا\n"
        "2. أنا أدخل منصة المدرسة باسمك (dars360.com)\n"
        "3. أحل واجباتك تلقائياً بالذكاء الاصطناعي\n"
        "4. تحفظ في قاعدة معرفتنا للتعلم منها\n\n"

        "🔒 <b>الأمان:</b>\n"
        "• كلمة المرور مشفّرة (لا أحد يقدر يقراها)\n"
        "• ما نشاركها مع أحد\n"
        "• تقدر تطلب فك القفل في أي وقت\n\n"

        "⏱️ <b>الربط يستغرق 30 ثانية فقط!</b>\n\n"

        "👇 <b>جاهز للربط؟</b>"
    )

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ابدأ الربط", callback_data="cmd_login")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="link_nudge_back")],
        ])
    )


async def cb_link_nudge_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رجوع من شرح الربط إلى الندج الأصلي."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    user = await db_get_user(uid)
    user_name = (user or {}).get("name", "")
    free_attempts = (user or {}).get("free_attempts", 0) or 0
    is_sub = bool((user or {}).get("expiry_ts", 0) > time.time())

    text = build_link_nudge_message(
        user_name=user_name,
        free_attempts=free_attempts,
        is_subscribed=is_sub,
        context="general"
    )

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=build_link_nudge_keyboard(include_help=True, include_skip=True)
    )


# ==============================================================================
# helper: يفحص الربط في أي handler ويعطي الندج إذا ما ربط
# ==============================================================================

async def check_and_nudge(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action_name: str = "هذا الإجراء",
    context_label: str = "general",
) -> bool:
    """
    يفحص هل المستخدم ربط. إذا لا، يعرض الندج ويرجع True.
    إذا ربط، يرجع False (يتابع الإجراء).

    Usage في أي handler:
        if await check_and_nudge(update, context, "حل الواجبات", "solving"):
            return
        # كمّل الإجراء
    """
    uid = update.effective_user.id if update.effective_user else None
    if not uid:
        return False

    if await is_user_linked(uid):
        return False  # مربوط، كمّل الإجراء

    user = await db_get_user(uid)
    user_name = (user or {}).get("name", "")
    free_attempts = (user or {}).get("free_attempts", 0) or 0
    is_sub = bool((user or {}).get("expiry_ts", 0) > time.time())

    text = (
        f"⚠️ <b>عشان {action_name}، اربط المنصة أولاً.</b>\n\n"
        + build_link_nudge_message(
            user_name=user_name,
            free_attempts=free_attempts,
            is_subscribed=is_sub,
            context=context_label,
        )
    )

    # استخدم edit_message_text لو كان callback، وإلا reply_text
    if update.callback_query:
        try:
            await update.callback_query.answer("🔗 اربط المنصة أولاً", show_alert=True)
        except Exception:
            pass
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=build_link_nudge_keyboard(include_help=True)
            )
        except Exception:
            # إذا فشل edit (مثلاً لو الرسالة من البوت)، ابعث رسالة جديدة
            await context.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode="HTML",
                reply_markup=build_link_nudge_keyboard(include_help=True)
            )
    else:
        await update.effective_message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=build_link_nudge_keyboard(include_help=True)
        )

    admin_trace("LINK_NUDGE", f"User {uid} blocked from {action_name} — not linked", uid)
    return True
