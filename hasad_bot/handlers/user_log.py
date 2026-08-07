"""
user_log.py - عرض log مفصّل لكل مستخدم (للأدمنز).

يقرأ من ملف logers/admin/admin_accounts_details.log ويصفّي حسب user_id.
الصيغة في الملف: [timestamp] [hijri] [ID: {uid}] [{step}] >> {detail}
"""
from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from hasad_bot.config import config
from hasad_bot.utils import now_hijri
from hasad_bot.database import is_admin, db_get_user, db_all_users


# ==============================================================================
# Parser
# ==============================================================================

# نمط السطر في admin_accounts_details.log:
# [2026-06-15 07:03:43] [29 Dhu al-Hijjah 1447 AH] [ID: 7286004246] [ENGINE_STOP] >> Session paused
LOG_PATTERN = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+"
    r"\[(?P<hijri>[^\]]+)\]\s+"
    r"\[ID:\s*(?P<uid>[^\]]+?)\s*\]\s+"
    r"\[(?P<step>[^\]]+)\]\s+>>\s+"
    r"(?P<detail>.*)$"
)


def _resolve_log_path() -> Optional[Path]:
    """يحسب مسار ملف log"""
    log_path = Path(config.log_dir) / "admin" / "admin_accounts_details.log"
    if log_path.exists():
        return log_path
    return None


def get_user_logs(user_id: int, limit: int = 30, step_filter: Optional[str] = None) -> List[Dict]:
    """
    يقرأ آخر N سطور لمستخدم معيّن من ملف اللوق.

    Args:
        user_id: معرف المستخدم (Telegram ID)
        limit: عدد السطور المطلوب (افتراضي 30)
        step_filter: فلتر اختياري على نوع الحدث (مثل 'LOGIN' أو 'ENGINE_STOP')

    Returns:
        list of dicts: [{ts, hijri, uid, step, detail}, ...] (من الأحدث للأقدم)
    """
    log_path = _resolve_log_path()
    if not log_path:
        logger.warning(f"User log file not found at {log_path}")
        return []

    uid_str = str(user_id)
    matched: deque = deque(maxlen=limit * 5)  # نخزن أكثر من المطلوب للفلترة

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = LOG_PATTERN.match(line.rstrip("\n"))
                if not m:
                    continue
                if m.group("uid").strip() != uid_str:
                    continue
                if step_filter and step_filter.upper() not in m.group("step").upper():
                    continue
                matched.append(m.groupdict())
    except Exception as e:
        logger.error(f"Failed to read user log: {e}")
        return []

    # نرجّع آخر `limit` سطر (المتأخرة)
    return list(matched)[-limit:]


def get_user_log_stats(user_id: int) -> Dict[str, int]:
    """يحسب إحصائيات اللوق لمستخدم (عدد الأحداث حسب النوع)"""
    log_path = _resolve_log_path()
    if not log_path:
        return {}

    uid_str = str(user_id)
    counts: Dict[str, int] = {}
    total = 0

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = LOG_PATTERN.match(line.rstrip("\n"))
                if not m or m.group("uid").strip() != uid_str:
                    continue
                step = m.group("step")
                counts[step] = counts.get(step, 0) + 1
                total += 1
    except Exception as e:
        logger.error(f"Failed to compute user log stats: {e}")
        return {}

    return {"_total": total, **counts}


async def resolve_user_id(query: str) -> Optional[int]:
    """
    يحوّل مدخل المستخدم (id رقمي أو username) إلى Telegram user_id.

    Args:
        query: إما رقم (123456) أو يوزرنيم (@apkD7oomi) أو اسم (apkD7oomi)

    Returns:
        user_id إن وُجد، وإلا None
    """
    query = query.strip().lstrip("@")
    if not query:
        return None

    # رقم مباشر
    if query.isdigit():
        return int(query)

    # بحث باليوزرنيم
    users = await db_all_users()
    q_lower = query.lower()

    for u in users:
        tg = (u.get("tg_username") or "").lower()
        name = (u.get("name") or "").lower()
        if tg == q_lower or tg.lstrip("@") == q_lower or name == q_lower:
            return u.get("telegram_id")

    return None


# ==============================================================================
# Telegram command
# ==============================================================================

def _format_log_entry(entry: Dict[str, str], max_detail_len: int = 200) -> str:
    ts = entry.get("ts", "?")
    step = entry.get("step", "?")
    detail = entry.get("detail", "")
    if len(detail) > max_detail_len:
        detail = detail[:max_detail_len] + "..."
    return f"• <code>{ts}</code> <b>[{step}]</b>\n   {detail}"


async def cmd_user_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /userlog <user_id|username> [N] [STEP]
    أمثلة:
        /userlog 7286004246
        /userlog @apkD7oomi 50
        /userlog 7286004246 20 LOGIN
    """
    uid = update.effective_user.id
    if not await is_admin(uid):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "🔍 <b>استخدام:</b>\n"
            "<code>/userlog &lt;user_id|@username&gt; [عدد] [نوع]</code>\n\n"
            "<b>أمثلة:</b>\n"
            "• <code>/userlog 7286004246</code>\n"
            "• <code>/userlog @apkD7oomi 50</code>\n"
            "• <code>/userlog 7286004246 20 LOGIN</code>\n",
            parse_mode="HTML",
        )
        return

    # Parse args
    target_query = args[0]
    limit = 30
    step_filter = None

    for a in args[1:]:
        if a.isdigit():
            limit = min(max(1, int(a)), 200)
        else:
            step_filter = a

    # Resolve user_id
    target_uid = await resolve_user_id(target_query)
    if target_uid is None:
        await update.message.reply_text(
            f"❌ ما لقيت مستخدم بـ: <code>{target_query}</code>",
            parse_mode="HTML",
        )
        return

    # معلومات المستخدم
    user = await db_get_user(target_uid)
    user_name = (user or {}).get("name", "مستخدم")
    user_tg = (user or {}).get("tg_username", "")

    # الإحصائيات
    stats = get_user_log_stats(target_uid)
    total = stats.pop("_total", 0)
    top_steps = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:6]
    stats_text = "، ".join([f"{k}={v}" for k, v in top_steps]) if top_steps else "—"

    # اللوق
    entries = get_user_logs(target_uid, limit=limit, step_filter=step_filter)

    header = (
        f"📜 <b>سجل المستخدم</b>\n\n"
        f"👤 <b>الاسم:</b> {user_name}\n"
        f"🆔 <b>ID:</b> <code>{target_uid}</code>\n"
        f"📨 <b>يوزرنيم:</b> @{user_tg}\n"
        f"📊 <b>إجمالي الأحداث:</b> {total}\n"
        f"🔝 <b>الأكثر:</b> {stats_text}\n"
        f"🔍 <b>الفلتر:</b> {step_filter or 'الكل'}\n"
        f"📌 <b>المعروض:</b> آخر {len(entries)} حدث\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    if not entries:
        await update.message.reply_text(
            header + "<i>لا توجد أحداث مطابقة.</i>",
            parse_mode="HTML",
        )
        return

    # نقسم الرسائل لو كانت طويلة (Telegram limit ~4096 chars)
    chunks: List[str] = [header]
    for entry in entries:
        line = _format_log_entry(entry) + "\n\n"
        if len(chunks[-1]) + len(line) > 3500:
            chunks.append(line)
        else:
            chunks[-1] += line

    for i, chunk in enumerate(chunks):
        prefix = "" if i == 0 else f"<i>(تابع {i+1}/{len(chunks)})</i>\n\n"
        await update.message.reply_text(prefix + chunk, parse_mode="HTML")


# ==============================================================================
# Public API
# ==============================================================================

async def send_user_log_to(bot, chat_id: int, target_query: str, limit: int = 30, step_filter: Optional[str] = None):
    """
    نسخة برمجية (تُستخدم من الترمنال أو غيره).
    ترسل اللوق كرسائل تيليجرام للـ chat_id المحدد.
    """
    target_uid = await resolve_user_id(target_query)
    if target_uid is None:
        await bot.send_message(chat_id, f"❌ ما لقيت مستخدم بـ: {target_query}")
        return

    user = await db_get_user(target_uid)
    user_name = (user or {}).get("name", "مستخدم")
    user_tg = (user or {}).get("tg_username", "")

    stats = get_user_log_stats(target_uid)
    total = stats.pop("_total", 0)
    top_steps = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:6]
    stats_text = "، ".join([f"{k}={v}" for k, v in top_steps]) if top_steps else "—"

    entries = get_user_logs(target_uid, limit=limit, step_filter=step_filter)

    header = (
        f"📜 <b>سجل المستخدم</b>\n\n"
        f"👤 <b>الاسم:</b> {user_name}\n"
        f"🆔 <b>ID:</b> <code>{target_uid}</code>\n"
        f"📨 <b>يوزرنيم:</b> @{user_tg}\n"
        f"📊 <b>إجمالي الأحداث:</b> {total}\n"
        f"🔝 <b>الأكثر:</b> {stats_text}\n"
        f"🔍 <b>الفلتر:</b> {step_filter or 'الكل'}\n"
        f"📌 <b>المعروض:</b> آخر {len(entries)} حدث\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    if not entries:
        await bot.send_message(chat_id, header + "<i>لا توجد أحداث مطابقة.</i>", parse_mode="HTML")
        return

    chunks: List[str] = [header]
    for entry in entries:
        line = _format_log_entry(entry) + "\n\n"
        if len(chunks[-1]) + len(line) > 3500:
            chunks.append(line)
        else:
            chunks[-1] += line

    for chunk in chunks:
        await bot.send_message(chat_id, chunk, parse_mode="HTML")
