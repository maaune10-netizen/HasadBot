"""
admin.py - admin panel, broadcast, renew/revoke/genkeys/users/keys, files,
system reset, account navigation.

This is the largest handler module. It also owns the navigation
callbacks ``back_to_account_callback`` and ``back_to_main_callback`` so
that account views have somewhere to go back to.
"""
from __future__ import annotations

import csv
import io
import shutil
import time
import asyncio

import aiosqlite
from loguru import logger

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    WebAppInfo,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU, ADMIN_PANEL
from hasad_bot.database import (
    _db_pool,
    db_init,
    db_get_user,
    db_set_user,
    db_all_users,
    db_log,
    db_delete_user,
    db_create_keys,
    db_activate_key,
    is_admin,
    is_subscribed,
    is_public_mode,
    set_public_mode,
    update_user_last_active,
    create_user_subscription,
    get_user_remaining_homeworks,
    get_users_count_by_target,
    get_users_by_target,
    get_target_name,
    is_bot_frozen,
    is_teacher,
)
from hasad_bot.datetime_utils import datetime, now, now_timestamp
from hasad_bot.utils import (
    kb_admin,
    kb_main,
    admin_trace,
    now_hijri,
    decrypt_password,
    gregorian_to_hijri,
)
from hasad_bot.logger import log_button_click


# ==============================================================================
# Admin panel entry / system stats / credentials export
# ==============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel entry"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "👑 لوحة الإدارة", "admin")

    if not await is_admin(uid):
        return MAIN_MENU
    await update.message.reply_text(
        f"👑 <b>لوحة تحكم الأدمن</b>\n\n📅 {now_hijri()}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin()
    )
    return ADMIN_PANEL


async def admin_system_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system statistics"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "📊 إحصائيات النظام", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU

    users = await db_all_users()
    total_users = len(users)
    total_subs = sum(1 for u in users if (u.get("expiry_ts") or 0) > now_timestamp())
    total_trials = sum(u.get("free_attempts", 0) for u in users)
    total_refs = sum(u.get("referral_count", 0) for u in users)

    from hasad_bot.ai_engine import stats as ai_stats

    text = (
        "📊 <b>تقرير النظام الشامل</b> 📊\n\n"
        f"👥 إجمالي المستخدمين: <b>{total_users}</b>\n"
        f"💎 المشتركين الفعالين: <b>{total_subs}</b>\n"
        f"🎟️ إجمالي الواجبات: <b>{total_trials}</b>\n"
        f"🔗 إجمالي الإحالات: <b>{total_refs}</b>\n\n"
        f"🤖 <b>إحصائيات الذكاء الاصطناعي:</b>\n"
        f"📚 إجمالي الواجبات: <b>{ai_stats['total_hw']}</b>\n"
        f"💾 ضربات قاعدة البيانات: <b>{ai_stats['db_hits']}</b>\n"
        f"🦙 Groq: <b>{ai_stats['groq']}</b>\n"
        f"✨ Gemini: <b>{ai_stats['gemini']}</b>\n"
        f"❌ الأخطاء: <b>{ai_stats['errors']}</b>\n\n"
        f"🏆 <b>أفضل 5 مسوقين:</b>\n"
    )

    top_refs = sorted(users, key=lambda x: x.get("referral_count", 0), reverse=True)[:5]
    for i, tr in enumerate(top_refs):
        if tr.get('referral_count', 0) > 0:
            text += f"{i+1}. {tr.get('name')} (ID: {tr.get('telegram_id')}) - {tr.get('referral_count')} دعوة\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return ADMIN_PANEL


async def admin_extract_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract decrypted credentials to CSV"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🔑 استخراج بيانات المنصة", "admin")

    if uid != config.admin_id:
        await update.message.reply_text(
            "⛔ هذه الميزة متاحة فقط للمالك.",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_PANEL

    users = await db_all_users()
    csv_file = io.StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(['Telegram ID', 'Name', 'Platform Username', 'Decrypted Password', 'Free Attempts', 'Sub Expiry'])

    count = 0
    for u in users:
        user_plat = u.get("dars360_user")
        pass_enc = u.get("dars360_pass")
        if user_plat and pass_enc:
            pass_plain = decrypt_password(pass_enc)
            writer.writerow([
                u['telegram_id'], u.get('name', ''), user_plat,
                pass_plain, u.get('free_attempts', 0), u.get('expiry_hijri', '')
            ])
            count += 1

    if count == 0:
        await update.message.reply_text("📭 لا يوجد حسابات مربوطة.")
        return ADMIN_PANEL

    csv_file.seek(0)
    bio = io.BytesIO(csv_file.read().encode('utf-8'))
    bio.name = f"Credentials_{now().strftime('%Y%m%d')}.csv"
    await update.message.reply_document(
        document=bio,
        caption=f"🚨 <b>تم استخراج بيانات المنصة</b>\nيحتوي الملف على ({count}) حساب.",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_PANEL


# ==============================================================================
# Broadcast
# ==============================================================================

async def admin_broadcast_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب اختيار الفئة المستهدفة للإرسال"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 الكل", callback_data="broadcast_target:all")],
        [InlineKeyboardButton("💎 المشتركين", callback_data="broadcast_target:subscribed")],
        [InlineKeyboardButton("❌ غير المشتركين", callback_data="broadcast_target:not_subscribed")],
        [InlineKeyboardButton("🔗 مرتبط المنصة", callback_data="broadcast_target:linked")],
        [InlineKeyboardButton("🚫 غير مرتبط المنصة", callback_data="broadcast_target:not_linked")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="broadcast_target:cancel")]
    ])

    await update.message.reply_text(
        "📢 اختر الفئة المستهدفة:",
        reply_markup=keyboard
    )
    # لا نغير الحالة، نبقى في MAIN_MENU
    return MAIN_MENU


async def broadcast_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    if not await is_admin(uid):
        await query.edit_message_text("⛔ غير مصرح")
        return

    target = query.data.split(":")[1]
    if target == "cancel":
        await query.edit_message_text("❌ تم الإلغاء.", reply_markup=kb_admin())
        return

    # تخزين الهدف في context
    context.user_data["broadcast_target"] = target
    context.user_data["awaiting_broadcast_text"] = True   # علامة انتظار النص

    count = await get_users_count_by_target(target)
    await query.edit_message_text(
        f"📊 الفئة: {get_target_name(target)}\n👥 العدد: {count}\n\n"
        f"✍️ أرسل الرسالة الآن (نص أو صورة):",
        parse_mode="HTML"
    )
    # نبقى في MAIN_MENU، لكن handle_text سيتعامل مع النص
    # حفظ الهدف في context
    context.user_data["broadcast_target"] = target

    # عرض عدد المستخدمين في هذه الفئة
    count = await get_users_count_by_target(target)

    # تعديل الرسالة الحالية لإظهار التأكيد ثم الانتقال إلى حالة انتظار النص
    await query.edit_message_text(
        f"📊 <b>الفئة المختارة:</b> {get_target_name(target)}\n"
        f"👥 <b>عدد المستخدمين:</b> {count}\n\n"
        f"✍️ <b>أرسل الرسالة التي تريد تعميمها:</b>\n"
        f"(يمكنك إرسال نص أو صورة مع نص)\n"
        f"لإلغاء العملية أرسل /cancel",
        parse_mode="HTML"
    )

    # ✅ العودة إلى الحالة التي تنتظر النص (AWAIT_BROADCAST_MSG)
    from hasad_bot.config import AWAIT_BROADCAST_MSG
    return AWAIT_BROADCAST_MSG


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام الرسالة وإرسالها فوراً مع تأكيد الإرسال"""
    uid = update.effective_user.id

    if not await is_admin(uid):
        return MAIN_MENU

    target = context.user_data.get("broadcast_target")
    if not target:
        await update.message.reply_text("❌ حدث خطأ: لم يتم تحديد الفئة المستهدفة.")
        return ADMIN_PANEL

    # حفظ محتوى الرسالة
    has_photo = bool(update.message.photo)
    has_document = bool(update.message.document)

    if has_photo:
        photo_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        message_preview = f"[صورة] {caption[:100]}" if caption else "[صورة بدون نص]"
    elif has_document:
        doc_id = update.message.document.file_id
        doc_name = update.message.document.file_name
        caption = update.message.caption or ""
        message_preview = f"[ملف: {doc_name}] {caption[:100]}"
    else:
        text = update.message.text
        message_preview = text[:200]

    target_name = get_target_name(target)
    count = await get_users_count_by_target(target)

    # إرسال رسالة "جاري الإرسال"
    status_msg = await update.message.reply_text(f"⏳ <b>جاري الإرسال إلى {count} مستخدم...</b>\n\n📌 الفئة: {target_name}", parse_mode="HTML")

    users = await get_users_by_target(target)
    sent = 0
    failed = 0

    for user_id in users:
        try:
            if has_photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo_id,
                    caption=f"📢 <b>رسالة من الإدارة</b>\n\n{caption}" if caption else "📢 رسالة من الإدارة",
                    parse_mode="HTML"
                )
            elif has_document:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=doc_id,
                    caption=f"📢 <b>رسالة من الإدارة</b>\n\n{caption}" if caption else "📢 رسالة من الإدارة",
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 <b>رسالة من الإدارة</b>\n\n{text}",
                    parse_mode="HTML"
                )
            sent += 1
            await asyncio.sleep(0.05)  # تجنب الـ Flood wait
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send to {user_id}: {e}")

    # تنظيف البيانات
    context.user_data.pop("broadcast_target", None)
    context.user_data.pop("awaiting_broadcast_text", None)

    # ✅ حذف رسالة "جاري الإرسال"
    try:
        await status_msg.delete()
    except:
        pass

    # ✅ إرسال التقرير النهائي
    await update.message.reply_text(
        f"✅ <b>تم الإرسال!</b>\n\n"
        f"📌 الفئة: {target_name}\n"
        f"✅ نجح: {sent}\n"
        f"❌ فشل: {failed}\n"
        f"📅 {now_hijri()}",
        parse_mode="HTML",
        reply_markup=kb_admin()
    )
    return ADMIN_PANEL


# ==============================================================================
# Renew / revoke / genkeys
# ==============================================================================

async def admin_renew_ask(update: Update, context):
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "➕ تجديد اشتراك", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU
    await update.message.reply_text(
        "➕ أرسل <b>Telegram ID</b> للمستخدم:",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_RENEW_USER
    return AWAIT_RENEW_USER


async def admin_renew_got_user(update: Update, context):
    context.user_data["renew_uid"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 أرسل <b>عدد الأيام</b> للتجديد:",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_RENEW_DAYS
    return AWAIT_RENEW_DAYS


async def admin_renew_got_days(update: Update, context):
    """تجديد اشتراك مستخدم - مع إنشاء اشتراك في user_subscriptions"""
    try:
        days = int(update.message.text.strip())
        uid_i = int(context.user_data.get("renew_uid", "0"))
        u = await db_get_user(uid_i)

        if not u:
            await update.message.reply_text("❌ المستخدم غير موجود.")
            return ADMIN_PANEL

        cur_exp = u.get("expiry_ts", 0) or 0
        if cur_exp < now_timestamp():
            cur_exp = now_timestamp()

        new_exp = cur_exp + days * 86400
        exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))
        # تحديث جدول users
        await db_set_user(uid_i, expiry_ts=new_exp, expiry_hijri=exp_h)

        # ✅ ========== إنشاء اشتراك جديد ==========
        if days <= 7:
            plan_id = "weekly"
        elif days <= 30:
            plan_id = "monthly"
        else:
            plan_id = "semester"

        await create_user_subscription(uid_i, plan_id, cur_exp, new_exp)
        # ==========================================

        await update.message.reply_text(
            f"✅ تم تجديد <code>{uid_i}</code> +{days} يوم | الانتهاء: {exp_h}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_admin()
        )

        # إشعار للمستخدم
        try:
            await context.bot.send_message(
                uid_i,
                f"🎉 <b>تم تحديث اشتراكك!</b> +{days} يوم.\nالانتهاء: {exp_h}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")
    return ADMIN_PANEL


async def admin_revoke_ask(update: Update, context):
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🚫 إلغاء الأكسس", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU
    await update.message.reply_text(
        "🚫 أرسل <b>Telegram ID</b> لإلغاء الأكسس:",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_REVOKE_USER
    return AWAIT_REVOKE_USER


async def admin_revoke_done(update: Update, context):
    try:
        uid_i = int(update.message.text.strip())
        await db_set_user(uid_i, expiry_ts=0, expiry_hijri="تم الإلغاء ❌")
        await update.message.reply_text(
            f"✅ تم إلغاء اشتراك <code>{uid_i}</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_admin()
        )
        try:
            await context.bot.send_message(
                uid_i,
                "🚫 <b>تم إلغاء اشتراكك من قبل الإدارة.</b>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")
    return ADMIN_PANEL


async def admin_genkeys_ask(update: Update, context):
    """Ask for key generation parameters"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🔑 توليد أكواد", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU
    await update.message.reply_text(
        "🔑 أرسل بالصيغة: (العدد مسافة الأيام)\nمثال: <code>5 30</code>",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_GENKEY_COUNT
    return AWAIT_GENKEY_COUNT


async def admin_genkeys_done(update: Update, context):
    """Generate keys"""
    try:
        parts = update.message.text.strip().split()
        if len(parts) < 2:
            await update.message.reply_text("⚠️ صيغة غير صحيحة. مثال: 5 30")
            from hasad_bot.config import AWAIT_GENKEY_COUNT
            return AWAIT_GENKEY_COUNT

        count, days = int(parts[0]), int(parts[1])
        keys = await db_create_keys(count, days)
        text = f"✅ <b>تم إصدار {count} كود ({days} يوم):</b>\n\n" + "\n".join(f"<code>{k}</code>" for k in keys)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_admin())

    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")
    return ADMIN_PANEL


async def admin_toggle_mode(update: Update, context):
    """Toggle public/private mode"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🔓 وضع عام/خاص", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU
    cur = await is_public_mode()
    await set_public_mode(not cur)
    mode = "🌍 عام" if not cur else "🔐 خاص"
    await update.message.reply_text(f"✅ تم تغيير وضع البوت إلى: {mode}", reply_markup=kb_admin())
    return ADMIN_PANEL


# ==============================================================================
# Users list / user detail / unlock / delete
# ==============================================================================

async def admin_list_users(update: Update, context):
    """List all users - مع إضافة علامة ربط المنصة"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "👥 قائمة المستخدمين", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU

    users = await db_all_users()
    now_ts = now_timestamp()
    text = f"👥 <b>المستخدمين</b> ({now_hijri()})\n\n"
    kbd = []

    for u in users:
        uid_i = u["telegram_id"]
        if uid_i == 0:
            continue

        # حالة الاشتراك
        sub = "✅" if (u.get("expiry_ts") or 0) > now_ts else "❌"

        # حالة الأدمن
        adm_b = "👑" if u.get("is_admin", 0) >= 1 else ""

        # ✅ حالة ربط المنصة: 🔗 إذا وجد dars360_user، وإلا ⚪
        linked = "🔗" if u.get("dars360_user") else "⚪"

        # بناء النص
        text += f"{sub}{adm_b}{linked} <b>{u.get('name', '—')}</b> <code>{uid_i}</code>\n"

        # زر المستخدم
        kbd.append([InlineKeyboardButton(
            f"{sub}{adm_b}{linked} {u.get('name', '—')} ({uid_i})",
            callback_data=f"ud:{uid_i}"
        )])

    text += f"\n📊 الإجمالي: {len(users)}"

    if len(kbd) > 90:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kbd) if kbd else None
        )
    return ADMIN_PANEL


async def admin_add_homework_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية إضافة واجبات لمستخدم"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    await update.message.reply_text(
        "➕ <b>إضافة واجبات لمستخدم</b>\n\n"
        "أرسل <b>Telegram ID</b> للمستخدم:",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_ADD_HW_ID
    return AWAIT_ADD_HW_ID


async def admin_add_hw_got_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام ID المستخدم"""
    try:
        target_uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ ID غير صالح. أرسل رقماً صحيحاً.")
        from hasad_bot.config import AWAIT_ADD_HW_ID
        return AWAIT_ADD_HW_ID

    user = await db_get_user(target_uid)
    if not user:
        await update.message.reply_text(f"❌ المستخدم `{target_uid}` غير موجود.", parse_mode=ParseMode.HTML)
        from hasad_bot.config import AWAIT_ADD_HW_ID
        return AWAIT_ADD_HW_ID

    context.user_data["add_hw_target_uid"] = target_uid
    await update.message.reply_text(
        f"✅ المستخدم: {user.get('name', target_uid)}\n"
        f"🎟️ رصيده الحالي: {user.get('free_attempts', 0)} واجب مجاني\n\n"
        f"✍️ أرسل <b>عدد الواجبات</b> التي تريد إضافتها (رقم):",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_ADD_HW_COUNT
    return AWAIT_ADD_HW_COUNT


async def admin_add_hw_got_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام عدد الواجبات، ثم إذا كان مشتركاً يعرض خيارين، وإلا يضيف مباشرة"""
    try:
        count = int(update.message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح أكبر من صفر.")
        from hasad_bot.config import AWAIT_ADD_HW_COUNT
        return AWAIT_ADD_HW_COUNT

    target_uid = context.user_data.get("add_hw_target_uid")
    user = await db_get_user(target_uid)
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return MAIN_MENU

    context.user_data["add_hw_count"] = count
    is_subscribed = await is_subscribed(target_uid)

    if not is_subscribed:
        # ✅ غير مشترك → أضف مباشرة إلى free_attempts
        current = user.get("free_attempts", 0)
        new_value = current + count

        conn = await _db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET free_attempts = ? WHERE telegram_id = ?",
            (new_value, target_uid)
        )
        await conn.commit()

        await db_log(update.effective_user.id, "ADD_HOMEWORKS",
                     detail=f"User {target_uid} +{count} free (was {current}, now {new_value})")

        await update.message.reply_text(
            f"✅ <b>تمت الإضافة بنجاح!</b>\n\n"
            f"👤 المستخدم: {user.get('name', target_uid)}\n"
            f"➕ تم إضافة: {count} واجب (رصيد مجاني)\n"
            f"🎟️ الرصيد الجديد: {new_value}",
            parse_mode=ParseMode.HTML
        )
        # إشعار للمستخدم
        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 <b>تم إضافة {count} واجبات مجانية إلى رصيدك!</b>\n"
                f"🎟️ رصيدك الحالي: {new_value} واجب",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        return MAIN_MENU

    else:
        # ✅ مشترك → اعرض خيارين للأدمن
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎁 إضافة إلى الرصيد المجاني", callback_data="add_hw_free"),
                InlineKeyboardButton("📈 إضافة إلى حد الاشتراك", callback_data="add_hw_sub")
            ]
        ])
        await update.message.reply_text(
            f"👤 المستخدم: {user.get('name', target_uid)} (مشترك)\n"
            f"🎟️ رصيده المجاني الحالي: {user.get('free_attempts', 0)}\n"
            f"📦 حد الاشتراك الحالي: سيتم جلبه من جدول الاشتراكات\n"
            f"➕ عدد الواجبات المراد إضافتها: {count}\n\n"
            f"❓ إلى أين تريد إضافة هذه الواجبات؟",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        from hasad_bot.config import AWAIT_ADD_HW_CHOICE
        return AWAIT_ADD_HW_CHOICE


async def admin_add_hw_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار إضافة الواجبات للمشترك (مجاني أو اشتراك)"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not await is_admin(uid):
        await query.edit_message_text("⛔ غير مصرح")
        return

    choice = query.data  # add_hw_free أو add_hw_sub
    target_uid = context.user_data.get("add_hw_target_uid")
    count = context.user_data.get("add_hw_count")

    if not target_uid or not count:
        await query.edit_message_text("❌ حدث خطأ في البيانات. أعد المحاولة.")
        return

    user = await db_get_user(target_uid)
    if not user:
        await query.edit_message_text("❌ المستخدم غير موجود.")
        return

    if choice == "add_hw_free":
        # إضافة إلى free_attempts
        current = user.get("free_attempts", 0)
        new_value = current + count
        conn = await _db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET free_attempts = ? WHERE telegram_id = ?",
            (new_value, target_uid)
        )
        await conn.commit()
        await db_log(uid, "ADD_HOMEWORKS_FREE",
                     detail=f"User {target_uid} +{count} free (was {current}, now {new_value})")
        await query.edit_message_text(
            f"✅ تم إضافة {count} واجبات إلى الرصيد المجاني للمستخدم {user.get('name', target_uid)}.\n"
            f"🎟️ الرصيد الجديد: {new_value}",
            parse_mode=ParseMode.HTML
        )
        # إشعار للمستخدم
        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 <b>تم إضافة {count} واجبات مجانية إلى رصيدك!</b>\n"
                f"🎟️ رصيدك الحالي: {new_value} واجب",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

    else:  # add_hw_sub
        # إضافة إلى max_homeworks في الاشتراك النشط
        conn = await _db_pool.get_connection()
        # جلب الاشتراك النشط
        async with conn.execute("""
            SELECT id, max_homeworks FROM user_subscriptions
            WHERE user_id = ? AND is_active = 1 AND end_date > ?
            ORDER BY end_date DESC LIMIT 1
        """, (target_uid, time.time())) as cursor:
            sub = await cursor.fetchone()
        if not sub:
            await query.edit_message_text("❌ لا يوجد اشتراك نشط لهذا المستخدم.")
            return
        sub_id, current_max = sub
        new_max = current_max + count
        await conn.execute(
            "UPDATE user_subscriptions SET max_homeworks = ? WHERE id = ?",
            (new_max, sub_id)
        )
        await conn.commit()
        await db_log(uid, "ADD_HOMEWORKS_SUB",
                     detail=f"User {target_uid} +{count} to subscription (was {current_max}, now {new_max})")
        await query.edit_message_text(
            f"✅ تم إضافة {count} واجبات إلى حد اشتراك المستخدم {user.get('name', target_uid)}.\n"
            f"📦 الحد الجديد: {new_max} واجب",
            parse_mode=ParseMode.HTML
        )
        # إشعار للمستخدم
        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 <b>تم زيادة حد اشتراكك بمقدار {count} واجب!</b>\n"
                f"📦 الحد الجديد: {new_max} واجب",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

    # تنظيف البيانات
    context.user_data.pop("add_hw_target_uid", None)
    context.user_data.pop("add_hw_count", None)


async def admin_add_hw_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الضغط على نعم/لا لإضافة الواجبات"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not await is_admin(uid):
        await query.edit_message_text("⛔ غير مصرح")
        return

    choice = query.data
    target_uid = context.user_data.get("add_hw_target_uid")
    count = context.user_data.get("add_hw_count")

    if choice == "add_hw_confirm_no":
        await query.edit_message_text("❌ تم إلغاء إضافة الواجبات.")
        # تنظيف البيانات
        context.user_data.pop("add_hw_target_uid", None)
        context.user_data.pop("add_hw_count", None)
        return

    # تنفيذ الإضافة
    user = await db_get_user(target_uid)
    if not user:
        await query.edit_message_text("❌ المستخدم غير موجود.")
        return

    current = user.get("free_attempts", 0)
    new_value = current + count

    # تحديث قاعدة البيانات
    conn = await _db_pool.get_connection()
    await conn.execute(
        "UPDATE users SET free_attempts = ? WHERE telegram_id = ?",
        (new_value, target_uid)
    )
    await conn.commit()

    # تسجيل العملية
    await db_log(uid, "ADD_HOMEWORKS", detail=f"User {target_uid} +{count} (was {current}, now {new_value})")

    await query.edit_message_text(
        f"✅ <b>تمت الإضافة بنجاح!</b>\n\n"
        f"👤 المستخدم: {user.get('name', target_uid)}\n"
        f"➕ تم إضافة: {count} واجب\n"
        f"🎟️ الرصيد الجديد: {new_value}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin()
    )

    # إرسال إشعار للمستخدم (اختياري)
    try:
        await context.bot.send_message(
            target_uid,
            f"🎉 <b>تم إضافة {count} واجبات مجانية إلى رصيدك!</b>\n"
            f"🎟️ رصيدك الحالي: {new_value} واجب",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

    # تنظيف البيانات
    context.user_data.pop("add_hw_target_uid", None)
    context.user_data.pop("add_hw_count", None)


async def admin_add_admin_ask(update: Update, context):
    """Ask for new admin ID"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "👤 إضافة أدمن", "admin")

    if update.effective_user.id != config.admin_id:
        await update.message.reply_text("⛔ هذه الصلاحية للمالك فقط.")
        return ADMIN_PANEL
    await update.message.reply_text(
        "👤 أرسل <b>Telegram ID</b> للترقية:",
        parse_mode=ParseMode.HTML
    )
    from hasad_bot.config import AWAIT_ADD_ADMIN
    return AWAIT_ADD_ADMIN


async def admin_add_admin_done(update: Update, context):
    """Add new admin - مع إنشاء اشتراك عادي"""
    try:
        new_uid = int(update.message.text.strip())

        # ✅ تحديث صلاحيات المستخدم
        await db_set_user(new_uid, is_admin=1, joined_hijri=now_hijri())

        # ✅ ========== إنشاء اشتراك عادي للأدمن الجديد ==========
        from hasad_bot.database import create_user_subscription

        u = await db_get_user(new_uid)
        cur_exp = (u or {}).get("expiry_ts", 0) or 0

        if cur_exp < time.time():
            cur_exp = time.time()

        # 30 يوماً للأدمن الجديد
        end_date = cur_exp + (30 * 86400)

        conn = await _db_pool.get_connection()
        await conn.execute("""
            UPDATE user_subscriptions SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (new_uid,))

        await conn.execute("""
            INSERT INTO user_subscriptions
            (user_id, plan_id, start_date, end_date, max_homeworks, homeworks_used, is_active)
            VALUES (?, 'monthly', ?, ?, 100, 0, 1)
        """, (new_uid, cur_exp, end_date))
        await conn.commit()
        # ================================================================

        await update.message.reply_text(
            f"✅ تم ترقية <code>{new_uid}</code> إلى أدمن مع اشتراك شهري.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_admin()
        )

        try:
            await context.bot.send_message(
                new_uid,
                "👑 <b>تم تعيينك كأدمن في النظام!</b>\n\n"
                "📦 تم تفعيل اشتراك شهري لك (100 واجب).\n"
                "📅 يمكنك تجديد اشتراكك من لوحة التحكم.",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")
    return ADMIN_PANEL


async def admin_files(update: Update, context):
    """Send database files"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "📥 إدارة الملفات", "admin")

    if not await is_admin(update.effective_user.id):
        return MAIN_MENU

    for f in [config.db_file, config.audit_log]:
        if f.exists():
            try:
                await update.message.reply_document(
                    document=InputFile(str(f), filename=f.name),
                    caption=f"📁 {f.name} | {now_hijri()}"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ تعذر استخراج {f.name}: {e}")
    return ADMIN_PANEL


async def admin_full_reset(update: Update, context):
    """Full system reset"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "☢️ ريستارت شامل", "admin")

    if update.effective_user.id != config.admin_id:
        await update.message.reply_text("⛔ هذه العملية للمالك فقط.")
        return ADMIN_PANEL

    backup = config.data_dir / f"backup_{int(now_timestamp())}.db"
    if config.db_file.exists():
        import shutil
        shutil.copy2(config.db_file, backup)

    import aiosqlite
    async with aiosqlite.connect(config.db_file) as db:
        await db.execute("DELETE FROM users")
        await db.execute("DELETE FROM license_keys")
        await db.execute("DELETE FROM logs")
        await db.execute("DELETE FROM settings")
        await db.commit()

    await update.message.reply_text(
        f"☢️ <b>تمت إعادة تعيين النظام.</b>\n"
        f"💾 نسخة احتياطية: {backup.name}\n"
        f"📅 {now_hijri()}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin()
    )
    return ADMIN_PANEL


# ==============================================================================
# Callback handlers - user detail / unlock / delete
# ==============================================================================

async def cb_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user details"""
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id):
        return

    uid_i = int(q.data.split(":")[1])
    u = await db_get_user(uid_i)

    if not u:
        await q.edit_message_text("❌ المستخدم غير موجود.")
        return

    sub = "✅" if (u.get("expiry_ts") or 0) > now_timestamp() else "❌"

    await q.edit_message_text(
        f"👤 <b>تفاصيل المستخدم</b>\n\n"
        f"📛 الاسم: {u.get('name', '—')}\n"
        f"🆔 ID: <code>{uid_i}</code>\n"
        f"🎓 منصة: <code>{u.get('dars360_user', '—')}</code>\n"
        f"💎 الاشتراك: {sub}\n"
        f"📆 الانتهاء: {u.get('expiry_hijri', '—')}\n"
        f"👑 الرتبة: {'أدمن' if u.get('is_admin', 0) >= 1 else 'عادي'}\n"
        f"🎟️ محاولات: {u.get('free_attempts', 0)}\n"
        f"📅 {now_hijri()}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 مراسلة", callback_data=f"reply_support:{uid_i}"),
                InlineKeyboardButton("📜 السجل", callback_data=f"view_history:{uid_i}")
            ],
            [
                InlineKeyboardButton("🔓 فك القفل", callback_data=f"ulk:{uid_i}"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"del:{uid_i}")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ])
    )


async def cb_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unlock user account"""
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id):
        return

    uid_i = int(q.data.split(":")[1])
    await db_set_user(uid_i, locked_to=None, lock_request=0, dars360_user=None, dars360_pass=None)
    await q.edit_message_text(f"✅ تم فك قفل <code>{uid_i}</code>.", parse_mode=ParseMode.HTML)

    try:
        await context.bot.send_message(
            uid_i,
            "🔓 <b>تم فك قفل حسابك.</b> يمكنك إضافة حساب جديد الآن.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass


async def cb_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete user"""
    q = update.callback_query
    await q.answer()
    if q.from_user.id != config.admin_id:
        return

    uid_i = int(q.data.split(":")[1])
    await db_delete_user(uid_i)
    await q.edit_message_text(f"🗑️ تم حذف <code>{uid_i}</code>.", parse_mode=ParseMode.HTML)


# ==============================================================================
# Web App shortcuts + navigation
# ==============================================================================

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح صفحة إعدادات الدفع"""

    uid = update.effective_user.id

    # تأكد أن المستخدم هو الأدمن الرئيسي
    if uid != config.admin_id:
        await update.message.reply_text("⛔ غير مصرح")
        return

    webapp_url = "https://hasad1.netlify.app/admin_settings.html"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⚙️ إعدادات الدفع",
            web_app=WebAppInfo(url=webapp_url)
        )
    ]])

    await update.message.reply_text(
        "⚙️ **إعدادات الدفع**\n\n"
        "اضغط على الزر لفتح صفحة إعدادات الدفع:\n"
        "• تعديل بيانات التحويل البنكي\n"
        "• تعديل أسعار النجوم\n"
        "• حفظ الإعدادات",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def admin_panel_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح لوحة تحكم الأدمن عبر Web App"""

    uid = update.effective_user.id

    # تأكد أن المستخدم أدمن
    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return

    webapp_url = "https://hasad1.netlify.app/admin.html"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "👑 لوحة التحكم",
            web_app=WebAppInfo(url=webapp_url)
        )
    ]])

    await update.message.reply_text(
        "👑 **لوحة تحكم الأدمن**\n\n"
        "اضغط على الزر لفتح لوحة التحكم وعرض:\n"
        "• إحصائيات المبيعات\n"
        "• طلبات الدفع\n"
        "• النشاطات الأخيرة",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def back_to_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة إلى صفحة حسابي"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    u = await db_get_user(uid) or {}
    sub = await is_subscribed(uid)

    total_solved = u.get('total_hw_solved', 0)
    rank_title = u.get('rank_title', '🥉 طالب جديد')
    platform_user = u.get('dars360_user', '')

    from hasad_bot.database import get_user_remaining_homeworks
    remaining_hw = await get_user_remaining_homeworks(uid)

    if platform_user:
        platform_display = f"<code>{platform_user}</code>"
    else:
        platform_display = "🔗 اضغط لربط المنصة"

    if sub:
        attempts_text = f"🎟️ <b>رصيدك المتبقي: {remaining_hw} واجب</b>"
    else:
        attempts_text = f"🎟️ <b>الواجبات المجانية: {u.get('free_attempts', 0)}</b>"

    text = f"""
<b>👤 معلومات حسابك</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📛 الاسم:</b> {u.get('name', '—')}
<b>🏅 الرتبة:</b> {rank_title} ( {total_solved} واجب )
<b>🆔 ID:</b> <code>{uid}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎓 منصة درس:</b> {platform_display}
<b>💎 الاشتراك:</b> {'نشط' if sub else 'منتهي'}
<b>📆 ينتهي:</b> {u.get('expiry_hijri', '—')}
{attempts_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📅 التاريخ:</b> {now_hijri()}
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 التقارير السابقة", callback_data="show_reports_list")]
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة إلى القائمة الرئيسية"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    adm = await is_admin(uid)

    await query.edit_message_text(
        "<b>🏠 الرئيسية</b>\n\nاختر من القائمة ما يناسبك",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(uid, admin=adm)
    )
