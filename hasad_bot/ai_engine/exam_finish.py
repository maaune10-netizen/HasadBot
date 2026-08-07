from hasad_bot.utils import admin_trace
from hasad_bot.playwright_engine import random_delay
from hasad_bot.ai_engine.ui import UIManager, get_engine_keyboard
from hasad_bot.ai_engine.selectors import QUESTIONS, SUBMIT


async def _handle_exam_finish(page, session, subject: str, exam_questions: int, questions_solved: int, exam_mistakes: int):
    """تسليم الاختبار - دالة مساعدة لإعادة استخدام الكود"""

    finish_btn = page.locator(SUBMIT.FINISH_COMBINED).first

    if await finish_btn.is_visible():
        admin_trace("SHIELD_FINISH", f"✅ تنفيذ عملية الإنهاء المبكر", session.user_id)

        status_msg = (
            f"{session.base_message}\n\n"
            f"📚 <b>{subject}</b>\n"
            f"🏁 <b>جاري تسليم الاختبار...</b>"
        )
        await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
        await random_delay(2000, 4000)

        await finish_btn.click(force=True)

        try:
            await page.wait_for_selector(SUBMIT.CONFIRM_YES, timeout=5000)
            await random_delay(1000, 2000)
            await page.click(SUBMIT.CONFIRM_YES)

            from hasad_bot.database import update_user_stats_comprehensive
            await update_user_stats_comprehensive(session.user_id)
            admin_trace("STATS_UPDATED", f"User stats updated after exam (force finish)", session.user_id)

            admin_trace("EXAM_SUBMITTED", f"Exam {subject} submitted (force finish)", session.user_id)

            session.stats["total_hw"] += 1
            # ✅ ملاحظة: questions و exams يُحدَّثان في add_completed_homework

            from hasad_bot.database import get_user_remaining_homeworks, get_user_free_attempts

            if session.is_subscribed:
                session.remaining = await get_user_remaining_homeworks(session.user_id)
            else:
                session.trials = await get_user_free_attempts(session.user_id)

            if session.is_subscribed:
                if hasattr(session, 'base_template') and session.base_template:
                    session.base_message = session.base_template.format(
                        total_solved=session.total_solved,
                        remaining=session.remaining
                    )
            else:
                if hasattr(session, 'base_template') and session.base_template:
                    session.base_message = session.base_template.format(
                        total_solved=session.total_solved,
                        trials=session.trials
                    )

            admin_trace("SHIELD_COMPLETED", f"✅ الاختبار {subject} تم إنهاؤه بنجاح", session.user_id)

        except Exception as e:
            admin_trace("FORCE_FINISH_ERR", f"خطأ في إنهاء الاختبار: {e}", session.user_id)
            raise


async def get_total_questions_count(page) -> int:
    try:
        try:
            await page.wait_for_selector(QUESTIONS.TOTAL_COUNT, timeout=3000)
            total_element = page.locator(QUESTIONS.TOTAL_COUNT).first
            if await total_element.is_visible():
                total_text = await total_element.text_content()
                if total_text and total_text.strip().isdigit():
                    total = int(total_text.strip())
                    admin_trace("TOTAL_Q", f"من progress: {total} أسئلة")
                    return total
        except:
            pass

        questions = await page.locator(QUESTIONS.CONTAINER).all()
        total = len(questions)
        admin_trace("TOTAL_Q", f"من العد: {total} أسئلة")
        return total

    except Exception as e:
        admin_trace("TOTAL_Q_ERR", str(e))
        try:
            questions = await page.locator(QUESTIONS.CONTAINER).all()
            return len(questions)
        except:
            return 0


async def is_essay_question(question) -> bool:
    """كشف إذا كان السؤال مقالي بدقة"""
    try:
        data_type = await question.get_attribute(QUESTIONS.ESSAY_TYPE_ID)
        if data_type == QUESTIONS.ESSAY_TYPE_VALUE:
            print(f"🔍 [ESSAY CHECK] data-type-id=4 → TRUE")
            return True

        question_text = await question.locator(QUESTIONS.TEXT).text_content() or ""
        if "أكمل" in question_text:
            print(f"🔍 [ESSAY CHECK] نص '{question_text[:30]}' يحتوي على أكمل/Complete → TRUE")
            return True

        input_field = question.locator(QUESTIONS.ESSAY_INPUT)
        input_count = await input_field.count()
        if input_count > 0:
            print(f"🔍 [ESSAY CHECK] وجود {input_count} input field → TRUE")
            return True

        options = await question.locator(f"{QUESTIONS.OPTION}, input[type='radio']").count()
        if options == 0:
            print(f"🔍 [ESSAY CHECK] لا توجد خيارات (options=0) → TRUE")
            return True

        print(f"🔍 [ESSAY CHECK] جميع الفحوصات فشلت → FALSE (options={options})")
        return False

    except Exception as e:
        print(f"❌ [ESSAY CHECK] خطأ: {e}")
        admin_trace("ESSAY_CHECK_ERR", str(e))
        return False
