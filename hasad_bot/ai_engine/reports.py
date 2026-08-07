import time
from hasad_bot.utils import admin_trace
from hasad_bot.ai_engine.ui import UIManager, get_engine_keyboard


async def send_homework_report(session, subject: str, total_questions: int, solved_questions: int, mistakes: int = 0):
    try:
        if total_questions > 0:
            percentage = (solved_questions / total_questions) * 100
        else:
            percentage = 0

        if percentage >= 90:
            evaluation = "🌟 ممتاز! 🔥"
            emoji = "🏆"
        elif percentage >= 75:
            evaluation = "✅ جيد جداً"
            emoji = "⭐"
        elif percentage >= 60:
            evaluation = "📝 مقبول"
            emoji = "📚"
        else:
            evaluation = "⚠️ يحتاج تحسين"
            emoji = "💪"

        report = (
            f"📊 **تقرير الواجب** 📊\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📚 **المادة:** {subject}\n"
            f"🔢 **إجمالي الأسئلة:** {total_questions}\n"
            f"✅ **تم الحل:** {solved_questions}\n"
            f"📈 **النسبة:** {percentage:.1f}%\n"
            f"❌ **الأخطاء:** {mistakes}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"**التقييم:** {emoji} {evaluation}\n"
            f"⚡ **الوقت:** {time.strftime('%H:%M:%S')}\n"
        )

        await UIManager.safe_update(session, report, get_engine_keyboard(session))
        admin_trace("HW_REPORT", f"{subject}: {solved_questions}/{total_questions} ({percentage:.1f}%)", session.user_id)

    except Exception as e:
        admin_trace("REPORT_ERR", str(e), session.user_id)


async def send_detailed_report(session):
    """إرسال تقرير مفصل - مع عرض كل الواجبات"""
    try:
        homeworks_list = session.session_stats.get('completed_homeworks', [])
        total_hw = len(homeworks_list)

        # ✅ إحصائيات هذه الجلسة فقط (بدون التراكمي من جلسات سابقة)
        _init = session.session_stats.get('_initial_snapshot', {})
        total_questions = session.session_stats.get('questions', 0) - _init.get('questions', 0)
        total_correct = session.session_stats.get('correct', 0) - _init.get('correct', 0)
        total_wrong = session.session_stats.get('wrong', 0) - _init.get('wrong', 0)

        sources_stats = session.session_stats.get('sources', {})

        total_db = sources_stats.get('db', 0)
        total_groq = sources_stats.get('groq', 0)
        total_qwen = sources_stats.get('qwen', 0)
        total_ensemble = sources_stats.get('ensemble', 0)
        total_gemini = sources_stats.get('gemini', 0)
        total_random = sources_stats.get('random', 0)

        total_hasad_ai_solutions = (
            total_db +
            total_groq +
            total_qwen +
            total_ensemble +
            total_gemini +
            total_random
        )

        if total_questions > 0:
            percentage = (total_correct / total_questions) * 100
        else:
            percentage = 0

        elapsed = int(time.time() - session.session_stats.get('start', time.time()))
        minutes = elapsed // 60
        seconds = elapsed % 60

        # ✅ الفجوة بين الإجمالي و "حل بواسطة حصاد" — للإيضاح
        not_by_hasad = max(0, total_questions - total_hasad_ai_solutions)

        report = f"""
📊 <b>تقرير حصاد - حل الواجبات</b> 📊

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 <b>معلومات المستخدم:</b>
• الاسم: {session.name}
• الرتبة: {session.rank_title}
• المعرف: <code>{session.user_id}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💎 <b>معلومات الاشتراك:</b>
• الخطة: {session.plan_name}
• تم حل: {session.total_solved} واجب
• المتبقي: {session.remaining if session.is_subscribed else session.trials} واجب
• ينتهي: {session.expiry_hijri}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>ملخص الجلسة:</b>
• ✅ عدد الواجبات: {total_hw}
• ✅ إجمالي الأسئلة: {total_questions}
• ✅ الإجابات الصحيحة: {total_correct}
• ❌ الإجابات الخاطئة: {total_wrong}
• 📈 نسبة النجاح: {percentage:.1f}%
• ⏱️ وقت الجلسة: {minutes} دقيقة {seconds} ثانية

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 <b>تفاصيل الواجبات:</b>
"""

        if homeworks_list:
            for i, hw in enumerate(homeworks_list, 1):
                hw_correct = hw.get('correct', hw.get('solved', 0) - hw.get('mistakes', 0))
                hw_mistakes = hw.get('mistakes', 0)
                hw_total = hw.get('total_questions', 0)
                hw_percentage = hw.get('percentage', 0)

                report += f"""
{i}. <b>{hw['subject']}</b>
   • الأسئلة: {hw_total}
   • الصحيح: {hw_correct}
   • الخاطئ: {hw_mistakes}
   • النسبة: {hw_percentage:.1f}%
"""
        else:
            report += "\n⚠️ لا توجد واجبات مكتملة في هذه الجلسة\n"

        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

        await session.bot.send_message(
            chat_id=session.chat_id,
            text=report,
            parse_mode="HTML"
        )

        admin_trace("DETAILED_REPORT", f"Report sent to user {session.user_id} with {total_hw} homeworks", session.user_id)

    except Exception as e:
        error_msg = f"❌ <b>فشل إنشاء التقرير</b>\n\n{str(e)[:200]}"
        await session.update_ui(error_msg, get_engine_keyboard(session))
        admin_trace("REPORT_ERR", str(e), session.user_id)
