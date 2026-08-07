import asyncio
import time
import random
from loguru import logger
from hasad_bot.utils import admin_trace
from hasad_bot.config import config
from hasad_bot.database import (
    _db_pool,
    db_get_user,
    db_update_rank,
    deduct_homework_attempt,
)
from hasad_bot.playwright_engine import (
    _browser_pool,
    scroll_element_to_center as scroll_to_center,
    login,
    extract_homeworks,
    get_all_questions,
    scrape_answer_key,
    random_delay,
)
from hasad_bot.ai_engine.state import stats, active_sessions
from hasad_bot.ai_engine.ui import UIManager, get_engine_keyboard
from hasad_bot.ai_engine.logging import AnswerSource, log_question_solved, log_error_event
from hasad_bot.ai_engine.metrics import increment_correct_answer, increment_total_questions
from hasad_bot.ai_engine.knowledge import KnowledgeBaseManager
from hasad_bot.ai_engine.ai_manager import AIManager
from hasad_bot.ai_engine.exam_finish import get_total_questions_count, is_essay_question
from hasad_bot.ai_engine.selectors import URLS, HOMEWORK, QUESTIONS, NAVIGATION, SUBMIT, RESULTS, SCROLL


async def solve_homework_logic_async(session):
    """المحرك الرئيسي - واجهة مستخدم احترافية"""

    admin_trace("SYS_START", f"Starting engine for UID {session.user_id}", session.user_id)
    session.solved_uuids.clear()

    from hasad_bot.database import get_user_total_stats

    previous_stats = await get_user_total_stats(session.user_id)

    if not hasattr(session, 'session_stats') or session.session_stats.get('homeworks', 0) == 0:
        session.session_stats = {
            'homeworks': previous_stats.get('total_homeworks', 0),
            'questions': previous_stats.get('total_questions', 0),
            'correct': previous_stats.get('total_correct', 0),
            'wrong': previous_stats.get('total_wrong', 0),
            'start': time.time(),
            'sources': {},
            'completed_homeworks': getattr(session, 'completed_homeworks', [])
        }
        # ✅ Snapshot للقيم الابتدائية — لعرض "هذه الجلسة فقط" في التقارير
        session.session_stats['_initial_snapshot'] = {
            'homeworks': session.session_stats['homeworks'],
            'questions': session.session_stats['questions'],
            'correct': session.session_stats['correct'],
            'wrong': session.session_stats['wrong'],
        }
        admin_trace("STATE", f"Loaded previous stats: {session.session_stats['homeworks']} homeworks", session.user_id)

    page = None
    context = None
    first_check = True

    try:
        await UIManager.safe_update(session, session.base_message, get_engine_keyboard(session))
        await asyncio.sleep(2)

        status_msg = f"{session.base_message}\n\n🔄 <b>جاري تجهيز المحرك المتطور...</b>\n⚙️ يتم تحضير بيئة التشغيل"
        await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
        await asyncio.sleep(3)

        admin_trace("BROWSER", "Getting browser context", session.user_id)
        context = await _browser_pool.get_context(session.user_id)
        session.context = context
        session.browser_pool = _browser_pool
        page = await context.new_page()

        status_msg = f"{session.base_message}\n\n🔐 <b>جاري تسجيل الدخول...</b>"
        await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
        await asyncio.sleep(1)

        admin_trace("LOGIN", "Attempting login", session.user_id)
        login_success = await login(page, session.platform_user, session.platform_pass, session.user_id)

        user_data = await db_get_user(session.user_id)
        school_id = user_data.get('platform_id', 'alamjad1')

        if not login_success:
            await UIManager.safe_update(session, f"{session.base_message}\n\n❌ <b>فشل تسجيل الدخول!</b>")
            await page.close()
            return

        from hasad_bot.database import update_user_stats_comprehensive
        await update_user_stats_comprehensive(session.user_id)

        homework_count = 0
        start_time = time.time()

        while session.is_running:
            if not session.is_running:
                break

            # ✅ حماية: إذا المستخدم المشترك استنفذ واجباته، أوقف الجلسة برسالة مفصّلة
            if session.is_subscribed and session.remaining <= 0:
                no_credit_msg = (
                    f"👋 مرحباً {session.name}!\n"
                    f"🌟 مستواك: {session.rank_title}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>اشتراكك الحالي</b>\n\n"
                    f"📦 الباقة: <b>{session.plan_name}</b>\n"
                    f"✅ تم حلها: <b>{session.total_solved}</b> واجب (الحد الأقصى)\n"
                    f"🎟️ الواجبات المتبقية: <b>0</b>\n"
                    f"📅 ينتهي الاشتراك: <b>{session.expiry_hijri}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"⚠️ <b>لقد استنفذت جميع واجبات هذا الشهر</b>\n\n"
                    f"💡 <b>لكن لا تقلق! لديك خياران لاستئناف الحل:</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎁 <b>الخيار الأول: شارك واربح</b>\n"
                    f"• أرسل رابط البوت لأصدقائك\n"
                    f"• كل صديق يسجل عن طريقك يمنحك <b>{config.referral_bonus} واجبات مجانية</b>\n"
                    f"• كلما زاد عدد أصدقائك، زاد رصيدك\n\n"
                    f"اضغط على زر <b>🎁 شارك واربح</b> في القائمة الرئيسية.\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💎 <b>الخيار الثاني: رقّي اشتراكك</b>\n"
                    f"• انتقل إلى باقة <b>ترم كامل</b> (200 واجب)\n"
                    f"• ستتمكن من حل المزيد دون توقف\n\n"
                    f"اضغط على زر <b>⭐ المتجر</b> للاطلاع على الباقات.\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🚀 اختر ما يناسبك واستمر في التفوق!"
                )
                await UIManager.safe_update(session, no_credit_msg, get_engine_keyboard(session))
                admin_trace("STOP", f"User {session.user_id} has 0 homeworks remaining — stopping solver", session.user_id)
                break

            if first_check:
                status_msg = f"{session.base_message}\n\n🔍 <b>جاري فحص الواجبات...</b>"
                await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
                user_data = await db_get_user(session.user_id)
                base_url = user_data.get('platform_url', URLS.DEFAULT_BASE)

                await page.goto(f"{base_url}{URLS.HOMEWORK_LIST}")
                await page.wait_for_load_state("domcontentloaded")
                await random_delay(1000, 2000)

                # 🚀 استخراج سريع مرة واحدة
                homeworks = await extract_homeworks(page, fast_mode=True)
                session.cached_homeworks = homeworks
                session.hw_index = 0
                actual_hw_count = len(homeworks)

                if actual_hw_count == 0:
                    elapsed = int(time.time() - start_time)
                    minutes = elapsed // 60
                    seconds = elapsed % 60
                    # ✅ إحصائيات هذه الجلسة فقط (نطرح snapshot أول الجلسة)
                    _init = session.session_stats.get('_initial_snapshot', {})
                    total_questions = session.session_stats.get('questions', 0) - _init.get('questions', 0)
                    total_correct = session.session_stats.get('correct', 0) - _init.get('correct', 0)
                    total_wrong = session.session_stats.get('wrong', 0) - _init.get('wrong', 0)

                    if total_questions > 0:
                        percentage = (total_correct / total_questions) * 100
                    else:
                        percentage = 0

                    summary = (
                        f"{session.base_message}\n\n"
                        f"🎉 <b>مبروك! تم الانتهاء من جميع الواجبات!</b> 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"<b>📊 ملخص الجلسة:</b>\n\n"
                        f"✅ <b>عدد الواجبات:</b> {session.session_stats.get('homeworks', 0)}\n"
                        f"✅ <b>إجمالي الأسئلة:</b> {total_questions}\n"
                        f"✅ <b>الإجابات الصحيحة:</b> {total_correct}\n"
                        f"❌ <b>الإجابات الخاطئة:</b> {total_wrong}\n"
                        f"📈 <b>نسبة النجاح:</b> {percentage:.1f}%\n"
                        f"⏱️ <b>وقت الجلسة:</b> {minutes} دقيقة {seconds} ثانية\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"اضغط على <b>📊 تقرير مفصل</b> للحصول على التقرير"
                    )
                    await UIManager.safe_update(session, summary, get_engine_keyboard(session))
                    break

                status_msg = (
                    f"{session.base_message}\n\n"
                    f"📊 <b>تم العثور على {actual_hw_count} واجب</b>\n"
                    f"🚀 جاري بدء حل الواجبات..."
                )
                await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
                await asyncio.sleep(2)

                first_check = False
                session.hw_verification_counter = 0
            else:
                # بعد كل واجب: نتنقل للصفحة الرئيسية ونجيب الزر الأول فقط (بدون extract)
                await page.goto(f"{base_url}{URLS.HOMEWORK_LIST}")
                await page.wait_for_load_state("domcontentloaded")
                await random_delay(500, 1000)

                # ✅ كل 10 واجبات — نعيد extract للتأكد
                session.hw_verification_counter = getattr(session, 'hw_verification_counter', 0) + 1
                if session.hw_verification_counter >= 10:
                    session.cached_homeworks = await extract_homeworks(page, fast_mode=True)
                    session.hw_index = 0
                    session.hw_verification_counter = 0
                    admin_trace("CACHE_VERIFY", f"Re-extracted: {len(session.cached_homeworks)} homeworks remaining")

                actual_hw_count = max(0, len(session.cached_homeworks) - session.hw_index)

                if actual_hw_count == 0:
                    elapsed = int(time.time() - start_time)
                    minutes = elapsed // 60
                    seconds = elapsed % 60
                    # ✅ إحصائيات هذه الجلسة فقط (نطرح snapshot أول الجلسة)
                    _init = session.session_stats.get('_initial_snapshot', {})
                    total_questions = session.session_stats.get('questions', 0) - _init.get('questions', 0)
                    total_correct = session.session_stats.get('correct', 0) - _init.get('correct', 0)
                    total_wrong = session.session_stats.get('wrong', 0) - _init.get('wrong', 0)

                    if total_questions > 0:
                        percentage = (total_correct / total_questions) * 100
                    else:
                        percentage = 0

                    summary = (
                        f"{session.base_message}\n\n"
                        f"🎉 <b>مبروك! تم الانتهاء من جميع الواجبات!</b> 🎉\n\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"<b>📊 ملخص الجلسة:</b>\n\n"
                        f"✅ <b>عدد الواجبات:</b> {session.session_stats.get('homeworks', 0)}\n"
                        f"✅ <b>إجمالي الأسئلة:</b> {total_questions}\n"
                        f"✅ <b>الإجابات الصحيحة:</b> {total_correct}\n"
                        f"❌ <b>الإجابات الخاطئة:</b> {total_wrong}\n"
                        f"📈 <b>نسبة النجاح:</b> {percentage:.1f}%\n"
                        f"⏱️ <b>وقت الجلسة:</b> {minutes} دقيقة {seconds} ثانية\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"اضغط على <b>📊 تقرير مفصل</b> للحصول على التقرير"
                    )
                    await UIManager.safe_update(session, summary, get_engine_keyboard(session))
                    break

            # 🚀 نستخدم الـ ID من الكاش للتنقل المباشر للواجب (بدل الضغط على زر)
            hw = session.cached_homeworks[session.hw_index]
            subject = hw['subject']
            homework_count += 1

            homework_questions = 0
            questions_solved = 0
            homework_mistakes = 0

            status_msg = (
                f"{session.base_message}\n\n"
                f"📚 <b>الواجب الحالي:</b> {subject}\n"
                f"🔄 <b>الواجبات المتبقية:</b> {actual_hw_count}\n"
                f"⏳ جاري فتح الواجب..."
            )
            await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
            admin_trace("HW_START", f"Starting homework: {subject}", session.user_id)
            logger.info(f"🚀 [HW_START] بدء حل واجب {subject} للمستخدم {session.user_id} | الأسئلة: {homework_questions}")

            session.hw_start_time = time.time()

            await random_delay(500, 1000)

            if not session.is_running:
                break

            # 🚀 ضغط زر ابدأ الحل لأول بطاقة في الصفحة (أسرع من extract بالـ ID)
            first_card = page.locator(HOMEWORK.CARD).first
            btn = first_card.locator(HOMEWORK.CARD_START_BTN_COMBINED).first
            await btn.click(force=True)

            if not session.is_running:
                break

            await page.wait_for_selector(QUESTIONS.CONTAINER_ANY, timeout=45000)

            try:
                total_questions_in_homework = await get_total_questions_count(page)
                admin_trace("HW_TOTAL", f"إجمالي أسئلة الواجب: {total_questions_in_homework}", session.user_id)
                homework_questions = total_questions_in_homework
            except Exception as e:
                admin_trace("HW_TOTAL_ERR", str(e), session.user_id)
                questions = await get_all_questions(page)
                homework_questions = len(questions)

            admin_trace("HW_INFO", f"الواجب: {subject} | إجمالي الأسئلة: {homework_questions}", session.user_id)

            update_counter = 0
            last_ui_update = time.time()
            offset = 0
            used_ai_for_this_hw = False

            while session.is_running:
                if not session.is_running:
                    break

                questions = await get_all_questions(page)
                total_q = len(questions)

                for idx, q in enumerate(questions):
                    if not session.is_running:
                        break

                    checked = await q.locator(QUESTIONS.OPTION_CHECKED).count()
                    if checked > 0:
                        continue

                    elapsed = time.time() - session.hw_start_time
                    if idx > 0:
                        avg_time_per_q = elapsed / idx
                        remaining_q = total_q - idx
                        eta_seconds = int(avg_time_per_q * remaining_q)
                        mins, secs = divmod(eta_seconds, 60)
                        eta_str = f"{mins}m {secs}s"
                    else:
                        eta_str = "جاري الحساب..."

                    current_question_number = offset + idx + 1
                    bar_length = 20
                    filled_len = int(round(bar_length * current_question_number / float(homework_questions)))
                    bar = '█' * filled_len + '░' * (bar_length - filled_len)
                    percent = int((current_question_number) / homework_questions * 100)
                    progress_bar = f"[{bar}] {percent}%"

                    update_counter += 1
                    current_time = time.time()

                    if update_counter >= 5 or current_time - last_ui_update >= 5:
                        update_counter = 0
                        last_ui_update = current_time

                        progress_message = (
                            f"{session.base_message}\n\n"
                            f"📚 <b>الواجب:</b> {subject}\n"
                            f"🔢 <b>السؤال:</b> {current_question_number}/{homework_questions}\n"
                            f"📊 <b>التقدم:</b> <code>{progress_bar}</code>\n"
                            f"⏱️ <b>الوقت المتبقي:</b> {eta_str}"
                        )

                        await UIManager.safe_update(session, progress_message, get_engine_keyboard(session))

                    await scroll_to_center(page, q)

                    if not session.is_running:
                        break

                    q_text = await q.locator(QUESTIONS.TEXT).inner_text()
                    q_text = q_text.strip()
                    opts = await q.locator(QUESTIONS.OPTION_TEXT).all_text_contents()

                    is_essay = await is_essay_question(q)
                    print(f"🔍 [DEBUG] is_essay = {is_essay}")

                    if is_essay:
                        print(f"✅ [DEBUG] دخلنا في if is_essay للسؤال {idx+1}")
                        admin_trace("ESSAY_DETECTED", f"Q{idx+1} is essay type", session.user_id)

                        try:
                            await q.click()
                            await random_delay(500, 800)
                            print(f"✅ [DEBUG] تم النقر على السؤال")
                        except:
                            pass

                        input_field = q.locator(QUESTIONS.ESSAY_INPUT).first

                        try:
                            await input_field.scroll_into_view_if_needed()
                            await random_delay(200, 400)
                        except:
                            pass

                        try:
                            await input_field.focus()
                            await random_delay(200, 400)
                            print(f"✅ [DEBUG] تم التركيز على الحقل - ظهر الإطار الأزرق")
                        except:
                            pass

                        try:
                            await input_field.click()
                            await random_delay(100, 200)
                            await input_field.click()
                            await random_delay(200, 400)
                            print(f"✅ [DEBUG] تم النقر المزدوج - ظهر المؤشر")
                        except:
                            pass

                        try:
                            essay_answer = await AIManager.get_gemini_answer_essay(q_text, session.user_id)

                            if essay_answer:
                                print(f"✅ [DEBUG] حصلنا على إجابة من Gemini: {essay_answer[:50]}")
                                source = AnswerSource.GEMINI

                                # ✅ عدّ المقالي ضمن "حل بواسطة حصاد" في التقرير
                                stats["gemini"] += 1
                                if 'sources' not in session.session_stats:
                                    session.session_stats['sources'] = {}
                                session.session_stats['sources'][AnswerSource.GEMINI.value] = (
                                    session.session_stats['sources'].get(AnswerSource.GEMINI.value, 0) + 1
                                )

                                await input_field.fill("")
                                await random_delay(100, 200)

                                await input_field.fill(essay_answer)
                                await random_delay(800, 1500)

                                questions_solved += 1
                                used_ai_for_this_hw = True
                                admin_trace("ESSAY_SOLVED", f"Q{idx+1} solved by Gemini", session.user_id)

                                try:
                                    conn = await _db_pool.get_connection()
                                    await conn.execute("""
                                        INSERT INTO solved_questions (user_id, question_text, answer, source, solved_at)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (session.user_id, q_text[:500], essay_answer, 'gemini', time.time()))
                                    await conn.commit()
                                except Exception as e:
                                    admin_trace("ESSAY_SAVE_ERR", str(e), session.user_id)

                                print(f"✅ [DEBUG] سنستخدم continue لتجنب MCQ")
                                continue
                            else:
                                print(f"❌ [DEBUG] Gemini فشل في الحل")
                                admin_trace("ESSAY_FAILED", f"Q{idx+1} could not be solved", session.user_id)
                                continue
                        except Exception as e:
                            print(f"❌ [DEBUG] خطأ في الكتابة: {e}")
                            admin_trace("ESSAY_WRITE_ERR", str(e), session.user_id)
                            continue

                    answer = None
                    source = None
                    img_src = None

                    try:
                        img_el = q.locator(QUESTIONS.IMAGE).first
                        if await img_el.is_visible():
                            img_src = await img_el.get_attribute("src")
                    except:
                        pass

                    db_answer, db_uuid = await KnowledgeBaseManager.check_for_answer_async(subject, q_text, img_src, session.user_id)
                    if db_answer:
                        answer = KnowledgeBaseManager.match_answer_to_option(db_answer, opts, session.user_id)
                        if answer:
                            source = AnswerSource.DATABASE
                            session.solved_uuids.add(db_uuid)
                            stats["db_hits"] += 1
                            if 'sources' not in session.session_stats:
                                session.session_stats['sources'] = {}
                            session.session_stats['sources'][AnswerSource.DATABASE.value] = session.session_stats['sources'].get(AnswerSource.DATABASE.value, 0) + 1
                            admin_trace("DB_SOLVED", f"Q{idx+1} solved from DB", session.user_id)

                    if not answer and q_text and len(q_text) > 5:
                        answer = await AIManager.get_groq_answer(q_text, opts, session.user_id)
                        if answer:
                            source = AnswerSource.GROQ
                            stats["groq"] += 1
                            session.session_stats['sources'][AnswerSource.GROQ.value] = session.session_stats['sources'].get(AnswerSource.GROQ.value, 0) + 1
                            admin_trace("GROQ_SOLVED", f"Q{idx+1} solved by Groq", session.user_id)
                            used_ai_for_this_hw = True

                    if not answer and img_src and config.gemini_keys:
                        from pathlib import Path
                        import re

                        screenshots_dir = config.knowledge_dir / "question_screenshots"
                        screenshots_dir.mkdir(parents=True, exist_ok=True)

                        if 'FileStorage/' in img_src:
                            img_name = img_src.split('FileStorage/')[-1]
                        else:
                            img_name = img_src.split('/')[-1] if '/' in img_src else img_src

                        safe_name = re.sub(r'[<>:"/\\|?*]', '_', img_name)
                        img_path = screenshots_dir / safe_name

                        try:
                            await q.screenshot(path=img_path)
                            admin_trace("SCREENSHOT", f"✅ صورة السؤال محفوظة: {img_path}", session.user_id)

                            answer = await AIManager.get_gemini_answer(str(img_path), session.user_id)
                            if answer:
                                source = AnswerSource.GEMINI
                                stats["gemini"] += 1
                                session.session_stats['sources'][AnswerSource.GEMINI.value] = session.session_stats['sources'].get(AnswerSource.GEMINI.value, 0) + 1
                                admin_trace("GEMINI_SOLVED", f"Q{idx+1} solved by Gemini", session.user_id)
                                used_ai_for_this_hw = True
                        except Exception as e:
                            admin_trace("SCREENSHOT_ERR", f"فشل حفظ الصورة: {e}", session.user_id)

                    if not answer and len(opts) > 0:
                        answer = random.randint(1, len(opts))
                        source = AnswerSource.RANDOM
                        stats["random"] = stats.get("random", 0) + 1
                        session.session_stats['sources'][AnswerSource.RANDOM.value] = session.session_stats['sources'].get(AnswerSource.RANDOM.value, 0) + 1
                        admin_trace("RANDOM", f"Random answer for Q{idx+1}: {answer}", session.user_id)

                    if answer and 1 <= answer <= len(opts):
                        try:
                            if source == AnswerSource.DATABASE:
                                session.session_stats['db_used'] = session.session_stats.get('db_used', 0) + 1
                            elif source == AnswerSource.GROQ:
                                session.session_stats['groq_used'] = session.session_stats.get('groq_used', 0) + 1
                            elif source == AnswerSource.GEMINI:
                                session.session_stats['gemini_used'] = session.session_stats.get('gemini_used', 0) + 1
                            elif source == AnswerSource.RANDOM:
                                session.session_stats['random_used'] = session.session_stats.get('random_used', 0) + 1

                            if not session.is_running:
                                break

                            await random_delay(800, 1500)
                            await q.locator(".q-option").nth(answer - 1).click(force=True)

                            if not session.is_running:
                                break

                            session.stats["solved_q"] += 1
                            questions_solved += 1

                            source_str = str(source) if not isinstance(source, AnswerSource) else source.value
                            increment_correct_answer(source_str)
                            increment_total_questions()

                            await log_question_solved(session.user_id, subject, source, q_text)

                            try:
                                conn = await _db_pool.get_connection()
                                await conn.execute("""
                                    INSERT INTO solved_questions (user_id, question_text, answer, source, solved_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (session.user_id, q_text[:500], str(answer), source.value, time.time()))
                                await conn.commit()
                            except Exception as e:
                                admin_trace("SOLVED_SAVE_ERR", str(e), session.user_id)

                            await page.evaluate(SCROLL.HALF_DOWN)
                            await random_delay(400, 800)
                        except Exception as e:
                            if "closed" in str(e).lower():
                                break
                            admin_trace("CLICK_ERR", str(e), session.user_id)

                offset += total_q

                if not session.is_running:
                    break

                next_btn = page.locator(NAVIGATION.NEXT_PAGE).first
                if await next_btn.is_visible() and await next_btn.is_enabled():
                    await random_delay(500, 1000)
                    await next_btn.click(force=True)
                    await page.wait_for_load_state("domcontentloaded")
                else:
                    status_msg = (
                        f"{session.base_message}\n\n"
                        f"📚 <b>{subject}</b>\n"
                        f"🏁 <b>جاري تسليم الواجب...</b>"
                    )
                    await UIManager.safe_update(session, status_msg, get_engine_keyboard(session))
                    await random_delay(1000, 2000)

                    js_keywords = SUBMIT.JS_FINISH_KEYWORDS
                    js_btn_id = SUBMIT.JS_SAVE_BTN_ID
                    js_finish_check = " || ".join(
                        [f"b.id === '{js_btn_id}'"] +
                        [f"b.innerText.includes('{kw}')" for kw in js_keywords]
                    )
                    await page.evaluate(f"""() => {{
                        const btns = Array.from(document.querySelectorAll('button, input[type="button"]'));
                        const finishBtn = btns.find(b => {js_finish_check});
                        if (finishBtn) finishBtn.click();
                    }}""")

                    try:
                        await page.wait_for_selector(SUBMIT.CONFIRM_YES, timeout=5000)
                        await random_delay(1000, 2000)
                        await page.click(SUBMIT.CONFIRM_YES)

                        from hasad_bot.database import update_user_stats_comprehensive
                        await update_user_stats_comprehensive(session.user_id)
                        admin_trace("STATS_UPDATED", f"User stats updated after homework", session.user_id)

                        if used_ai_for_this_hw:
                            admin_trace("LEARNING", f"AI used, scraping answers for {subject}", session.user_id)

                            await page.wait_for_load_state("networkidle")
                            await random_delay(2000, 3000)

                            await page.evaluate(SCROLL.TO_BOTTOM)
                            await random_delay(1000, 2000)

                            answers = await scrape_answer_key(page, subject, session)

                            if answers:
                                for ans in answers:
                                    admin_trace("LEARNING", f"Answer: {ans['ans'][:50]} | Status: {ans['log_type']}", session.user_id)
                                admin_trace("LEARNING", f"✅ Scraped {len(answers)} answers for {subject}", session.user_id)
                            else:
                                admin_trace("LEARNING", f"⚠️ No answers found for {subject}", session.user_id)

                        session.stats["total_hw"] += 1
                        # ✅ ملاحظة: questions و homeworks يُحدَّثان في add_completed_homework
                        #    لتجنّب الازدواج. هنا فقط نسجّل المحاولة.
                        await deduct_homework_attempt(session.user_id)

                        from hasad_bot.database import get_user_remaining_homeworks, get_user_free_attempts

                        if session.is_subscribed:
                            session.remaining = await get_user_remaining_homeworks(session.user_id)
                            admin_trace("STATE", f"Remaining homeworks: {session.remaining}", session.user_id)
                        else:
                            session.trials = await get_user_free_attempts(session.user_id)
                            admin_trace("STATE", f"Remaining free attempts: {session.trials}", session.user_id)

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

                        # ✅ قراءة النتيجة الفعلية من ودجة الموقع (بدلاً من افتراض solved = correct)
                        homework_correct = None
                        try:
                            await page.wait_for_selector(RESULTS.WIDGET, timeout=10000)
                            await random_delay(1000, 2000)

                            # استخراج كل أرقام الودجة دفعة واحدة عبر JavaScript (أقوى من selectors)
                            widget_data = await page.evaluate("""() => {
                                const digits = Array.from(document.querySelectorAll('.widget-digit'));
                                const result = {};
                                digits.forEach((d, i) => {
                                    // نحاول ربط كل رقم بنص الـ label الذي قبله
                                    let label = '';
                                    const prev = d.previousElementSibling;
                                    if (prev && prev.tagName === 'SPAN') label = prev.innerText.trim();
                                    const parent = d.parentElement;
                                    if (!label && parent) {
                                        const lbl = parent.querySelector('span.text-muted');
                                        if (lbl) label = lbl.innerText.trim();
                                    }
                                    result[`digit_${i}`] = { value: d.innerText.trim(), label: label };
                                });
                                return result;
                            }""")

                            # البحث عن رقم الصحيح/الخاطئ حسب الـ label
                            for key, data in (widget_data or {}).items():
                                label = (data.get('label') or '').strip()
                                value = (data.get('value') or '').strip()
                                if not value.isdigit():
                                    continue
                                if 'الصحيحة' in label or 'صحيحة' in label:
                                    if homework_correct is None:
                                        homework_correct = int(value)
                                elif 'الخاطئة' in label or 'خاطئة' in label:
                                    mistakes = int(value)
                                    session.stats["mistakes"] += mistakes
                                    homework_mistakes = mistakes
                                    session.session_stats['wrong'] = session.session_stats.get('wrong', 0) + mistakes

                            # Fallback: لو ما لقينا الـ labels، نحاول selectors الأصلية
                            if homework_correct is None:
                                correct_element = page.locator(RESULTS.CORRECT_COUNT).first
                                if await correct_element.count() > 0:
                                    try:
                                        correct_text = await correct_element.inner_text()
                                        if correct_text and correct_text.strip().isdigit():
                                            homework_correct = int(correct_text.strip())
                                    except Exception:
                                        pass

                            if homework_mistakes == 0:
                                wrong_element = page.locator(RESULTS.WRONG_COUNT).first
                                if await wrong_element.count() > 0:
                                    try:
                                        wrong_text = await wrong_element.inner_text()
                                        if wrong_text and wrong_text.strip().isdigit():
                                            mistakes = int(wrong_text.strip())
                                            session.stats["mistakes"] += mistakes
                                            homework_mistakes = mistakes
                                            session.session_stats['wrong'] = session.session_stats.get('wrong', 0) + mistakes
                                    except Exception:
                                        pass
                        except Exception as e:
                            admin_trace("RESULTS_WIDGET_ERR", f"Failed to read results widget: {e}", session.user_id)

                        # إذا المنصة ما أعطتنا العدد الصحيح، نستخدم الفارق (solved - wrong)
                        if homework_correct is None:
                            homework_correct = max(0, questions_solved - homework_mistakes)
                            admin_trace(
                                "RESULTS_CORRECT_FALLBACK",
                                f"Widget unavailable; estimated correct = solved({questions_solved}) - wrong({homework_mistakes}) = {homework_correct}",
                                session.user_id
                            )

                        # تحديث عداد الصحيح في الجلسة بالقيمة الفعلية من المنصة
                        # (المصدر الوحيد — per-question لم يعد يحدّث session_stats['correct'])
                        session.session_stats['correct'] = session.session_stats.get('correct', 0) + homework_correct

                        logger.info(f"🏁 [HW_END] انتهاء حل واجب {subject} للمستخدم {session.user_id} | النتيجة: {homework_correct}/{homework_questions} صحيح | خاطئة: {homework_mistakes}")
                        admin_trace("HW_END", f"{subject}: {homework_correct}/{homework_questions} صحيح (من المنصة) | خاطئة: {homework_mistakes}", session.user_id)

                        if homework_questions > 0:
                            percentage = (homework_correct / homework_questions) * 100
                        else:
                            percentage = 0

                        from hasad_bot.database import get_user_homeworks_stats

                        hw_stats = await get_user_homeworks_stats(session.user_id)
                        session.total_solved = hw_stats['total_solved']
                        session.remaining = hw_stats['remaining']

                        if session.is_subscribed:
                            if hasattr(session, 'base_template') and session.base_template:
                                session.base_message = session.base_template.format(
                                    total_solved=session.total_solved,
                                    remaining=session.remaining
                                )
                        else:
                            session.trials = hw_stats['free_attempts']
                            if hasattr(session, 'base_template') and session.base_template:
                                session.base_message = session.base_template.format(
                                    total_solved=session.total_solved,
                                    trials=session.trials
                                )

                        elapsed_time = time.time() - session.hw_start_time
                        minutes = int(elapsed_time // 60)
                        seconds = int(elapsed_time % 60)

                        # 🚀 تحديث المؤشر للواجب التالي (بدون extract)
                        session.hw_index += 1
                        remaining_count = max(0, len(session.cached_homeworks) - session.hw_index)

                        next_subject = ""
                        if remaining_count > 0 and session.hw_index < len(session.cached_homeworks):
                            next_subject = session.cached_homeworks[session.hw_index]['subject']

                        if remaining_count > 0:
                            result_message = (
                                f"{session.base_message}\n\n"
                                f"✅ <b>تم الانتهاء من الواجب</b> ({subject})\n"
                                f"📊 <b>النتيجة:</b> {homework_correct}/{homework_questions} صحيح ({percentage:.1f}%)\n"
                                f"🎯 <b>وقت الإنجاز:</b> {minutes} دقيقة {seconds} ثانية\n\n"
                                f"🔄 <b>جاري الانتقال للواجب التالي: {next_subject}</b>\n"
                                f"📊 <b>يتبقى {remaining_count} واجب{'ات' if remaining_count > 2 else ''} في المنصة</b>"
                            )
                        else:
                            result_message = (
                                f"{session.base_message}\n\n"
                                f"✅ <b>تم الانتهاء من الواجب</b> ({subject})\n"
                                f"📊 <b>النتيجة:</b> {homework_correct}/{homework_questions} صحيح ({percentage:.1f}%)\n"
                                f"🎯 <b>وقت الإنجاز:</b> {minutes} دقيقة {seconds} ثانية\n\n"
                                f"🎉 <b>مبروك! هذا آخر واجب في المنصة</b>"
                            )

                        await UIManager.safe_update(session, result_message, get_engine_keyboard(session))
                        await asyncio.sleep(3)

                        if hasattr(session, 'add_completed_homework'):
                            print(f"🔥 استدعاء add_completed_homework: {subject}, {homework_questions}, {questions_solved}, {homework_mistakes}, correct={homework_correct}")

                            session.add_completed_homework(subject, homework_questions, questions_solved, homework_mistakes, actual_correct=homework_correct)
                        else:
                            print(f"❌ add_completed_homework غير موجود في الجلسة!")

                        user = await db_get_user(session.user_id)
                        if user:
                            await db_update_rank(session.user_id, user.get('total_hw_solved', 0))

                        break

                    except Exception as e:
                        admin_trace("SUBMIT_ERR", str(e), session.user_id)
                        break

        await page.close()

    except Exception as e:
        from hasad_bot.utils import friendly_error_message

        error_msg = str(e).split('\n')[0]
        friendly_msg = friendly_error_message(e)

        admin_trace("CRITICAL_ERR", error_msg, session.user_id)
        await log_error_event(session.user_id, error_msg, "CRITICAL")

        await UIManager.safe_update(
            session,
            f"{session.base_message}\n\n"
            f"⚠️ **{friendly_msg}**\n\n"
            f"يمكنك بدء جلسة جديدة بالضغط على 🤖 حل الواجبات",
            get_engine_keyboard(None)
        )

    finally:
        session.is_running = False

        if hasattr(session, 'context') and session.context:
            try:
                for page in session.context.pages:
                    if not page.is_closed():
                        await page.close()
            except:
                pass

        if session.user_id in active_sessions:
            del active_sessions[session.user_id]

        admin_trace("SESSION_END", f"Session cleaned for user {session.user_id}", session.user_id)
