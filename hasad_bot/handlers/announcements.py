"""
announcements.py - إعلانات متكررة ومستهدفة (Marketing Automation).

يستبدل النظام البسيط رسائل "broadcast" العشوائية بنظام:
- قوالب جاهزة لكل حالة (free, expiring, low, re-engagement, share_earn, welcome)
- جدولة يومية عبر job_queue
- فلترة المستخدمين حسب حالتهم
- حماية من spam (حد أقصى رسالة واحدة لكل مستخدم/نوع/يوم)
- نصوص قابلة للتعديل من الأدمن (تعديل في قاعدة البيانات)
- أوامر /announce للأدمن للاختبار اليدوي

التخزين:
- announcement_templates: قوالب الإعلانات في قاعدة البيانات
- announcement_log: سجل الإرسال (لتجنب الإعادة)
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger
from telegram import Bot

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, admin_trace
from hasad_bot.database import (
    _db_pool,
    db_all_users,
    is_admin,
)


# ==============================================================================
# إعدادات عامة
# ==============================================================================

# حد الإرسال في الثانية (Telegram rate limit ~30 msg/s)
MAX_MESSAGES_PER_SECOND = 25
DELAY_BETWEEN_BATCHES = 1.0 / MAX_MESSAGES_PER_SECOND

# حماية spam: لا نرسل نفس النوع للمستخدم نفسه خلال 24 ساعة
SPAM_PROTECTION_HOURS = 24

# التوقيت اليومي للإعلانات التلقائية (السعودية GMT+3)
DEFAULT_SCHEDULE_TIME = "10:00"


# ==============================================================================
# أنواع الإعلانات والفلاتر
# ==============================================================================

class AnnouncementType(str, Enum):
    FREE_USER_PROMO = "free_user_promo"
    SUB_EXPIRING_5D = "sub_expiring_5d"
    SUB_EXPIRING_1D = "sub_expiring_1d"
    LOW_ATTEMPTS = "low_attempts"
    RE_ENGAGEMENT = "re_engagement"
    WELCOME = "welcome"
    SHARE_AND_EARN_PROMO = "share_and_earn_promo"
    LINK_REMINDER = "link_reminder"


# القوالب الافتراضية — تُحفظ في DB عند أول تشغيل
DEFAULT_TEMPLATES: Dict[str, Dict] = {
    "free_user_promo": {
        "name_ar": "🎁 ترويج الواجبات المجانية",
        "filter": "is_free_user_with_attempts",
        "schedule_time": "10:00",
        "message": """🎁 <b>عندك {free_attempts} واجبات مجانية!</b>

🚀 <b>كيف تبدأ؟</b>
• اضغط على 🤖 <b>حل الواجبات</b>
• اربط حسابك بالمنصة (مرة واحدة فقط)
• خل البوت يشتغل وانت مرتاح

💎 <b>تبغى أكثر؟</b>
عندنا باقات اشتراك تبدأ من {monthly_price} ريال شهرياً.

🎁 أو شارك واربح: كل صديق = +{referral_bonus} واجبات مجانية!
""",
    },

    "sub_expiring_5d": {
        "name_ar": "⏰ تنبيه: 5 أيام على انتهاء الاشتراك",
        "filter": "subscriber_with_5d_or_less",
        "schedule_time": "18:00",
        "message": """⏰ <b>اشتراكك ينتهي بعد {days_left} يوم!</b>

📦 <b>المتبقي:</b> {remaining} واجب من {total}
📅 <b>الانتهاء:</b> {expiry_hijri}

💡 <b>نصيحة:</b> استخدم المتبقي قبل ما يضيع!
🔄 <b>للتجديد:</b> اضغط ⭐ المتجر في القائمة الرئيسية.
""",
    },

    "sub_expiring_1d": {
        "name_ar": "🚨 آخر يوم في الاشتراك",
        "filter": "subscriber_with_1d_or_less",
        "schedule_time": "19:00",
        "message": """🚨 <b>آخر يوم في اشتراكك!</b>

📦 <b>المتبقي:</b> {remaining} واجب
📅 <b>ينتهي اليوم.</b>

⏰ استخدم المتبقي قبل ما يضيع!
🔄 اضغط ⭐ <b>المتجر</b> للتجديد.
""",
    },

    "low_attempts": {
        "name_ar": "📉 رصيدك على وشك النفاد",
        "filter": "subscriber_with_<=20pct",
        "schedule_time": "09:00",
        "message": """📊 <b>رصيدك على وشك النفاد!</b>

✅ <b>المتبقي:</b> {remaining} واجب من {total} في اشتراكك.

💎 <b>جدد الآن عشان ما تنقطع:</b>
• باقة ترم كامل: {semester_hw} واجب
• باقة شهرية: {monthly_hw} واجب

اضغط ⭐ <b>المتجر</b> للتجديد.
""",
    },

    "re_engagement": {
        "name_ar": "💤 تفاعل راكد",
        "filter": "inactive_7d",
        "schedule_time": "11:00",
        "message": """👋 <b>أهلاً {name}!</b>

💤 لاحظنا إنك ما استخدمت حصاد من {days_inactive} يوم. 

🎁 <b>عندك واجبات جديدة بانتظارك!</b>
اضغط على 🤖 <b>حل الواجبات</b> وكمّل.

💎 <b>اشتراكك ساري حتى {expiry_hijri}</b> — لا تضيّع المتبقي!
""",
    },

    "welcome": {
        "name_ar": "🎉 ترحيب بالمستخدم الجديد",
        "filter": "new_user_only",
        "schedule_time": "manual",
        "message": """🎉 <b>أهلاً بك في حصاد!</b>

أنا بوتك الذكي لحل الواجبات بالذكاء الاصطناعي 🤖⚡

🎁 <b>عندك {free_attempts} واجبات مجانية للتجربة!</b>

🚀 <b>كيف تبدأ؟</b>
1️⃣ اضغط على 🤖 <b>حل الواجبات</b>
2️⃣ اربط حسابك بالمنصة (مرة واحدة)
3️⃣ خلني أشتغل وأنت مرتاح

💎 <b>اشترك لاحقاً</b> لباقات أكبر ومميزات إضافية.

📣 <b>شارك واربح:</b> +{referral_bonus} واجبات لكل صديق!
""",
    },

    "share_and_earn_promo": {
        "name_ar": "🎁 شارك واربح - ترويج",
        "filter": "no_attempts_no_sub",
        "schedule_time": "14:00",
        "message": """👋 <b>أهلاً {name}!</b>

📭 خلصت محاولاتك المجانية ولا عندك اشتراك حالياً؟

🎁 <b>لا تفوّت الفرصة!</b>
اضغط على 🎁 <b>شارك واربح</b> في القائمة الرئيسية، انسخ رابطك الخاص، وشاركه مع أصدقائك.

🎯 <b>كل صديق يسجّل عن طريقك =</b>
• +{referral_bonus} واجبات مجانية هدية لك

💎 أو اشترك في الباقات بأسعار رمزية:
• ترم كامل: {semester_hw} واجب ({semester_price} ريال)
• شهري: {monthly_hw} واجب ({monthly_price} ريال)

اضغط 🎁 <b>شارك واربح</b> أو ⭐ <b>المتجر</b> في القائمة الرئيسية 👇
""",
    },

    "link_reminder": {
        "name_ar": "🔗 تذكير بربط المنصة",
        "filter": "not_linked_with_attempts",
        "schedule_time": "12:00",
        "message": """🔗 <b>أهلاً {name}!</b>

📊 لاحظنا إنك ما زلت ما ربطت حسابك بالمنصة، لكن عندك {free_attempts} واجبات مجانية بانتظارك!

🤖 <b>كيف تستفيد؟</b>
1️⃣ اضغط على <b>🔗 ربط المنصة</b> في القائمة الرئيسية
2️⃣ أدخل يوزرنيم + كلمة مرور المنصة (dars360.com)
3️⃣ خلني أحل واجباتك تلقائياً ⚡

⏱️ <b>الربط يستغرق 30 ثانية فقط — مرة واحدة</b>

🔒 بياناتك مشفّرة وآمنة في قاعدة البيانات.

🎁 <b>لا تضيّع {free_attempts} واجباتك!</b>
""",
    },
}


# ==============================================================================
# دوال مساعدة للفلترة
# ==============================================================================

async def _user_has_active_sub(user: dict) -> bool:
    """هل المستخدم عنده اشتراك ساري؟"""
    expiry = user.get("expiry_ts") or 0
    return expiry > time.time()


async def _user_days_left(user: dict) -> int:
    """كم يوم متبقي في الاشتراك؟"""
    expiry = user.get("expiry_ts") or 0
    delta = expiry - time.time()
    return max(0, int(delta // 86400))


async def _user_total_attempts(user: dict) -> int:
    """إجمالي محاولات الاشتراك (200/50/etc)."""
    return user.get("max_homeworks", 200) or 200


async def _user_remaining_attempts(user: dict) -> int:
    """المحاولات المتبقية من الاشتراك."""
    return user.get("remaining", 0) or 0


async def _user_free_attempts(user: dict) -> int:
    """المحاولات المجانية المتبقية."""
    return user.get("free_attempts", 0) or 0


async def _user_last_active(user: dict) -> float:
    """آخر وقت نشط (timestamp)."""
    return user.get("last_active") or 0


def _format_number(value) -> str:
    """تنسيق الأرقام العربية مع فواصل الآلاف."""
    if value is None:
        return "0"
    return f"{int(value):,}".replace(",", "،")


# ==============================================================================
# DB Schema + seeding
# ==============================================================================

async def ensure_announcement_tables():
    """إنشاء جداول الإعلانات والسجل."""
    try:
        conn = await _db_pool.get_connection()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS announcement_templates (
                type TEXT PRIMARY KEY,
                name_ar TEXT NOT NULL,
                template_text TEXT NOT NULL,
                target_filter TEXT NOT NULL,
                schedule_time TEXT DEFAULT '10:00',
                enabled INTEGER DEFAULT 1,
                created_at REAL,
                updated_at REAL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS announcement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                announcement_type TEXT NOT NULL,
                sent_at REAL NOT NULL
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcement_log_user_type
            ON announcement_log(user_id, announcement_type, sent_at)
        """)
        await conn.commit()

        # Seeding القوالب الافتراضية (INSERT OR IGNORE لا يمسّ القوالب الموجودة)
        for atype, tpl in DEFAULT_TEMPLATES.items():
            await conn.execute("""
                INSERT OR IGNORE INTO announcement_templates
                (type, name_ar, template_text, target_filter, schedule_time, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, COALESCE((SELECT created_at FROM announcement_templates WHERE type = ?), ?), ?)
            """, (
                atype, tpl["name_ar"], tpl["message"],
                tpl["filter"], tpl["schedule_time"],
                atype, time.time(), time.time()
            ))
        await conn.commit()
        logger.success("✅ Announcement tables ensured + templates synced")
    except Exception as e:
        logger.error(f"Error creating announcement tables: {e}")


# ==============================================================================
# قراءة وكتابة القوالب
# ==============================================================================

async def get_template(atype: str) -> Optional[Dict]:
    """قراءة قالب من DB."""
    conn = await _db_pool.get_connection()
    cursor = await conn.execute(
        "SELECT type, name_ar, template_text, target_filter, schedule_time, enabled "
        "FROM announcement_templates WHERE type = ?", (atype,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "type": row[0], "name_ar": row[1], "template_text": row[2],
        "target_filter": row[3], "schedule_time": row[4], "enabled": row[5]
    }


async def get_all_templates() -> List[Dict]:
    """قراءة كل القوالب."""
    conn = await _db_pool.get_connection()
    cursor = await conn.execute(
        "SELECT type, name_ar, template_text, target_filter, schedule_time, enabled "
        "FROM announcement_templates ORDER BY type"
    )
    rows = await cursor.fetchall()
    return [{
        "type": r[0], "name_ar": r[1], "template_text": r[2],
        "target_filter": r[3], "schedule_time": r[4], "enabled": r[5]
    } for r in rows]


async def set_template_enabled(atype: str, enabled: bool) -> bool:
    """تفعيل/تعطيل قالب."""
    conn = await _db_pool.get_connection()
    await conn.execute(
        "UPDATE announcement_templates SET enabled = ?, updated_at = ? WHERE type = ?",
        (1 if enabled else 0, time.time(), atype)
    )
    await conn.commit()
    return True


async def update_template_text(atype: str, new_text: str) -> bool:
    """تعديل نص القالب من الأدمن."""
    conn = await _db_pool.get_connection()
    await conn.execute(
        "UPDATE announcement_templates SET template_text = ?, updated_at = ? WHERE type = ?",
        (new_text, time.time(), atype)
    )
    await conn.commit()
    return True


# ==============================================================================
# فلترة المستخدمين حسب نوع الإعلان
# ==============================================================================

async def get_target_users(atype: str) -> List[Dict]:
    """يرجع قائمة المستخدمين المطابقين للفلتر."""
    tpl = await get_template(atype)
    if not tpl or not tpl["enabled"]:
        return []

    flt = tpl["target_filter"]
    all_users = await db_all_users()
    matched = []

    for u in all_users:
        uid = u.get("telegram_id")
        if not uid:
            continue
        # تخطي المستخدمين اللي استلموا نفس الإعلان في آخر 24 ساعة
        if await _was_sent_recently(uid, atype):
            continue

        if flt == "is_free_user_with_attempts":
            if not await _user_has_active_sub(u) and await _user_free_attempts(u) > 0:
                matched.append(u)
        elif flt == "subscriber_with_5d_or_less":
            if await _user_has_active_sub(u):
                days_left = await _user_days_left(u)
                if 0 < days_left <= 5:
                    matched.append(u)
        elif flt == "subscriber_with_1d_or_less":
            if await _user_has_active_sub(u):
                days_left = await _user_days_left(u)
                if days_left <= 1:
                    matched.append(u)
        elif flt == "subscriber_with_<=20pct":
            if await _user_has_active_sub(u):
                total = await _user_total_attempts(u)
                remaining = await _user_remaining_attempts(u)
                if total > 0 and (remaining / total) <= 0.20 and remaining > 0:
                    matched.append(u)
        elif flt == "inactive_7d":
            last_active = await _user_last_active(u)
            if last_active > 0 and (time.time() - last_active) > 7 * 86400:
                if await _user_has_active_sub(u):
                    matched.append(u)
        elif flt == "no_attempts_no_sub":
            if not await _user_has_active_sub(u) and await _user_free_attempts(u) <= 0:
                matched.append(u)
        elif flt == "not_linked_with_attempts":
            # ✅ الفلتر الأهم: عنده رصيد لكن ما ربط
            free = await _user_free_attempts(u)
            has_sub = await _user_has_active_sub(u)
            is_linked = bool((u.get("dars360_user") or "").strip() and (u.get("dars360_pass") or "").strip())
            if not is_linked and (free > 0 or has_sub):
                matched.append(u)
        elif flt == "new_user_only":
            # manual send only
            pass

    return matched


# ==============================================================================
# سجل الإرسال (spam protection)
# ==============================================================================

async def _was_sent_recently(user_id: int, atype: str) -> bool:
    """هل استلم المستخدم هذا النوع في آخر 24 ساعة؟"""
    conn = await _db_pool.get_connection()
    cutoff = time.time() - SPAM_PROTECTION_HOURS * 3600
    cursor = await conn.execute(
        "SELECT 1 FROM announcement_log WHERE user_id = ? AND announcement_type = ? AND sent_at > ? LIMIT 1",
        (user_id, atype, cutoff)
    )
    row = await cursor.fetchone()
    return row is not None


async def _log_sent(user_id: int, atype: str):
    """تسجيل إرسال."""
    conn = await _db_pool.get_connection()
    await conn.execute(
        "INSERT INTO announcement_log (user_id, announcement_type, sent_at) VALUES (?, ?, ?)",
        (user_id, atype, time.time())
    )
    await conn.commit()


# ==============================================================================
# الإرسال الفعلي
# ==============================================================================

async def send_announcement(bot: Bot, atype: str, manual: bool = False, progress_cb=None) -> Tuple[int, int, List[str]]:
    """
    يرسل إعلان لمستخدمين مطابقين.
    Returns: (sent_count, skipped_count, errors)
    """
    tpl = await get_template(atype)
    if not tpl:
        return 0, 0, [f"نوع غير معروف: {atype}"]

    if not tpl["enabled"] and not manual:
        return 0, 0, [f"النوع {atype} مُعطّل"]

    targets = await get_target_users(atype)
    if not targets:
        return 0, 0, []

    sent = 0
    skipped = 0
    errors: List[str] = []
    message = tpl["template_text"]

    admin_trace("ANNOUNCE_SEND", f"Sending {atype} to {len(targets)} users (manual={manual})", "SYSTEM")

    # الإرسال بمعدل محدود
    processed = 0
    for i, user in enumerate(targets):
        processed += 1
        uid = user.get("telegram_id")
        if not uid:
            # إبلاغ المتصل بالتقدم (لوحة التحكم)
            if progress_cb:
                progress_cb({"done": processed, "total": len(targets), "sent": sent, "skipped": skipped, "errors": len(errors)})
            continue

        # تخطي لو استلم حديثاً (إلا لو manual)
        if not manual and await _was_sent_recently(uid, atype):
            skipped += 1
            # إبلاغ المتصل بالتقدم (لوحة التحكم)
            if progress_cb:
                progress_cb({"done": processed, "total": len(targets), "sent": sent, "skipped": skipped, "errors": len(errors)})
            continue

        try:
            # تنسيق الرسالة بمعلومات المستخدم
            rendered = await _format_message_for_user(message, user)
            await bot.send_message(chat_id=uid, text=rendered, parse_mode="HTML")
            await _log_sent(uid, atype)
            sent += 1
        except Exception as e:
            err_msg = str(e)
            if "blocked" in err_msg.lower() or "deactivated" in err_msg.lower():
                # المستخدم حظر البوت — نتجاهله بصمت
                pass
            else:
                errors.append(f"UID {uid}: {err_msg[:80]}")
                admin_trace("ANNOUNCE_ERR", f"{atype} → {uid}: {err_msg[:80]}", "SYSTEM")

        # rate limiting
        if (i + 1) % MAX_MESSAGES_PER_SECOND == 0:
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        # إبلاغ المتصل بالتقدم (لوحة التحكم)
        if progress_cb:
            progress_cb({"done": processed, "total": len(targets), "sent": sent, "skipped": skipped, "errors": len(errors)})

    admin_trace("ANNOUNCE_DONE", f"{atype}: sent={sent}, skipped={skipped}, errors={len(errors)}", "SYSTEM")
    return sent, skipped, errors


async def _format_message_for_user(template: str, user: dict) -> str:
    """تعبئة placeholders بمعلومات المستخدم (كل الأرقام ديناميكية)."""
    # خطط الأسعار من الـ config/DB
    monthly_hw = 100
    monthly_price = 25
    semester_hw = 200
    semester_price = 60
    try:
        from hasad_bot.database.payment_settings import get_payment_config
        plans = (await get_payment_config()).get("plans", {}) or {}
        monthly = plans.get("monthly") or {}
        semester = plans.get("semester") or {}
        monthly_hw = monthly.get("max_homeworks", monthly_hw)
        monthly_price = monthly.get("price", monthly_price)
        semester_hw = semester.get("max_homeworks", semester_hw)
        semester_price = semester.get("price", semester_price)
    except Exception:
        pass

    return template.format(
        name=user.get("name") or "أهلاً",
        free_attempts=_format_number(await _user_free_attempts(user)),
        remaining=_format_number(await _user_remaining_attempts(user)),
        total=_format_number(await _user_total_attempts(user)),
        days_left=await _user_days_left(user),
        days_inactive=max(1, int((time.time() - (user.get("last_active") or 0)) // 86400)) if user.get("last_active") else 7,
        expiry_hijri=user.get("expiry_hijri") or "—",
        referral_bonus=config.referral_bonus,
        monthly_hw=monthly_hw,
        monthly_price=monthly_price,
        semester_hw=semester_hw,
        semester_price=semester_price,
    )


async def preview_announcement(atype: str) -> dict:
    """معاينة قالب إعلان قبل الإرسال (للوحة التحكم).

    Returns: {"type", "name_ar", "count", "sample_rendered", "sample_user_name"}
    """
    tpl = await get_template(atype)
    if not tpl:
        return {"error": f"نوع غير معروف: {atype}"}

    targets = await get_target_users(atype)
    sample_rendered = ""
    sample_user_name = ""
    if targets:
        sample_user_name = targets[0].get("name") or "أهلاً"
        sample_rendered = await _format_message_for_user(tpl["template_text"], targets[0])

    return {
        "type": atype,
        "name_ar": tpl.get("name_ar", atype),
        "count": len(targets),
        "sample_rendered": sample_rendered,
        "sample_user_name": sample_user_name,
    }


# ==============================================================================
# أوامر الأدمن
# ==============================================================================

async def _is_admin(uid: int) -> bool:
    return await is_admin(uid)


async def cmd_announce(update, context):
    """
    /announce [list|<type>|on <type>|off <type>|set <type>]
    """
    uid = update.effective_user.id
    if not await _is_admin(uid):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "📢 <b>أوامر الإعلانات:</b>\n\n"
            "<code>/announce list</code> — عرض الأنواع\n"
            "<code>/announce &lt;type&gt;</code> — إرسال فوري\n"
            "<code>/announce on &lt;type&gt;</code> — تفعيل\n"
            "<code>/announce off &lt;type&gt;</code> — تعطيل\n"
            "<code>/announce set &lt;type&gt;</code> — تعديل النص (Reply بذكر جديد)\n",
            parse_mode="HTML",
        )
        return

    cmd = args[0].lower()

    if cmd == "list":
        templates = await get_all_templates()
        lines = ["📢 <b>الأنواع المتاحة:</b>\n"]
        for t in templates:
            status = "✅" if t["enabled"] else "⏸️"
            lines.append(
                f"{status} <code>{t['type']}</code>\n"
                f"   📝 {t['name_ar']}\n"
                f"   🕐 {t['schedule_time']} | 🎯 {t['target_filter']}\n"
            )
        lines.append(f"\n💡 <b>الإحصائيات:</b>")
        lines.append(f"   • الإجمالي: {len(templates)} نوع")
        lines.append(f"   • المُفعّل: {sum(1 for t in templates if t['enabled'])}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if cmd == "on" and len(args) > 1:
        atype = args[1]
        if not await get_template(atype):
            await update.message.reply_text(f"❌ نوع غير موجود: <code>{atype}</code>", parse_mode="HTML")
            return
        await set_template_enabled(atype, True)
        await update.message.reply_text(f"✅ تم تفعيل <code>{atype}</code>", parse_mode="HTML")
        admin_trace("ANNOUNCE_TOGGLE", f"Enabled {atype}", uid)
        return

    if cmd == "off" and len(args) > 1:
        atype = args[1]
        if not await get_template(atype):
            await update.message.reply_text(f"❌ نوع غير موجود: <code>{atype}</code>", parse_mode="HTML")
            return
        await set_template_enabled(atype, False)
        await update.message.reply_text(f"⏸️ تم تعطيل <code>{atype}</code>", parse_mode="HTML")
        admin_trace("ANNOUNCE_TOGGLE", f"Disabled {atype}", uid)
        return

    if cmd == "set" and len(args) > 1:
        atype = args[1]
        tpl = await get_template(atype)
        if not tpl:
            await update.message.reply_text(f"❌ نوع غير موجود: <code>{atype}</code>", parse_mode="HTML")
            return
        # لازم يكون فيه Reply على رسالة فيها النص الجديد
        if not update.message.reply_to_message:
            await update.message.reply_text(
                f"📝 <b>تعديل نص:</b> {tpl['name_ar']}\n\n"
                f"رد على هذه الرسالة بالنص الجديد (يدعم placeholders: {{{{name}}}}, {{{{free_attempts}}}}, etc.)",
                parse_mode="HTML",
            )
            return
        new_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
        if not new_text:
            await update.message.reply_text("❌ النص المُرَدّ به فارغ", parse_mode="HTML")
            return
        await update_template_text(atype, new_text)
        await update.message.reply_text(
            f"✅ <b>تم تحديث النص لـ:</b> {tpl['name_ar']}\n\n"
            f"<i>المعاينة:</i>\n{new_text[:500]}",
            parse_mode="HTML",
        )
        admin_trace("ANNOUNCE_UPDATE", f"Updated text for {atype}", uid)
        return

    # بدون subcommand — نفترض أنه نوع للإرسال الفوري
    atype = args[0]
    tpl = await get_template(atype)
    if not tpl:
        await update.message.reply_text(
            f"❌ نوع غير موجود: <code>{atype}</code>\n\n"
            f"💡 <code>/announce list</code> لعرض الأنواع",
            parse_mode="HTML",
        )
        return

    wait_msg = await update.message.reply_text(
        f"📤 جاري إرسال <b>{tpl['name_ar']}</b>... قد يستغرق دقيقة.",
        parse_mode="HTML",
    )

    sent, skipped, errors = await send_announcement(context.bot, atype, manual=True)

    result = (
        f"✅ <b>تم!</b>\n\n"
        f"📤 مُرسلة: {sent}\n"
        f"⏭️ مُتجاوزة: {skipped}\n"
        f"❌ أخطاء: {len(errors)}"
    )
    if errors[:3]:
        result += "\n\n<b>أول 3 أخطاء:</b>\n" + "\n".join(f"• {e}" for e in errors[:3])

    try:
        await wait_msg.edit_text(result, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(result, parse_mode="HTML")
