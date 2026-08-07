"""
reports.py - per-day homework report views.

Contains:

* ``show_reports_list_callback`` - list days with reports
* ``view_day_report_callback``   - drill into a single day
"""
from __future__ import annotations

import datetime as _dt
import time

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode


async def show_reports_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأيام التي فيها تقارير"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id

    from hasad_bot.database import get_user_reports_days

    reports = await get_user_reports_days(uid)

    if not reports:
        await query.edit_message_text(
            "<b>📭 لا توجد تقارير سابقة</b>\n\nقم بحل واجب أولاً ثم عد إلى هنا.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_account")]
            ])
        )
        return

    message = "<b>📋 التقارير السابقة</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for report in reports:
        date_str = report.get('report_date', '')
        if not date_str:
            continue

        total_hw = report.get('total_homeworks', 0)
        total_q = report.get('total_questions', 0) or 0
        total_correct = report.get('total_correct', 0) or 0
        percentage = (total_correct / total_q * 100) if total_q > 0 else 0

        message += f"""
<b>📅 {date_str}</b>
   عدد الواجبات: {total_hw}
   النتيجة: {total_correct}/{total_q} صحيح
   النسبة: {percentage:.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    message += "\nاضغط على أي يوم لرؤية التفاصيل"

    # ✅ إنشاء الأزرار مع التحقق من وجود قيمة
    buttons = []
    for report in reports[:7]:
        date_str = report.get('report_date', '')
        if date_str:
            buttons.append([
                InlineKeyboardButton(text=date_str, callback_data=f"view_day_report:{date_str}")
            ])

    # ✅ أضف زر الرجوع فقط إذا كان هناك أزرار
    if buttons:
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_account")])
    else:
        buttons = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_account")]]

    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def view_day_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تقرير مفصل ليوم محدد"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    date_str = query.data.split(":")[1]

    if not date_str:
        await query.edit_message_text("<b>❌ لا توجد بيانات لهذا اليوم</b>")
        return

    from hasad_bot.database import get_user_report_by_date
    import datetime

    reports = await get_user_report_by_date(uid, date_str)

    if not reports:
        await query.edit_message_text("<b>❌ لا توجد بيانات لهذا اليوم</b>")
        return

    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%Y-%m-%d')

    total_hw = len(reports)
    total_q = sum(r.get('total_questions', 0) for r in reports)
    total_correct = sum(r.get('correct_answers', 0) or 0 for r in reports)
    total_wrong = sum(r.get('wrong_answers', 0) or 0 for r in reports)
    overall_percentage = (total_correct / total_q * 100) if total_q > 0 else 0

    message = f"<b>📊 تقرير يوم {formatted_date}</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n<b>📚 تفاصيل الواجبات المحلولة في هذا اليوم:</b>\n\n"

    for i, report in enumerate(reports, 1):
        subject = report.get('subject', 'غير معروف')
        time_str = datetime.datetime.fromtimestamp(report.get('end_time', time.time())).strftime('%H:%M')
        total = report.get('total_questions', 0)
        correct = report.get('correct_answers', 0) or 0
        wrong = report.get('wrong_answers', 0) or 0
        percentage = (correct / total * 100) if total > 0 else 0

        message += f"""
<b>{i}. {subject}</b>
   الوقت: {time_str}
   النتيجة: {correct}/{total} صحيح | {wrong} خطأ
   النسبة: {percentage:.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    message += f"""
<b>📊 إجمالي اليوم:</b>

   عدد الواجبات: {total_hw}
   إجمالي الأسئلة: {total_q}
   الإجابات الصحيحة: {total_correct}
   الإجابات الخاطئة: {total_wrong}
   نسبة النجاح: {overall_percentage:.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🤖 أداء حصاد AI:</b>

   تم حل جميع الواجبات تلقائياً

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📅 التاريخ:</b> {formatted_date}
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 العودة للقائمة", callback_data="show_reports_list")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
    ])

    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
