#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data models for HASAD Bot - نسخة محسنة نهائية مع واجهة متطورة
"""

from dataclasses import dataclass, field
from typing import Set, Optional, Dict, Any
import asyncio
import time
from loguru import logger
from hasad_bot.utils import admin_trace


def get_engine_keyboard(session=None):
    """كيبورد المحرك - 3 أزرار فقط"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    if not session or not session.is_running:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بدء حل الواجبات", callback_data='engine_start')]
        ])
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تقرير مفصل", callback_data='engine_pdf_report')],
        [InlineKeyboardButton("🛑 إيقاف نهائي", callback_data='engine_stop')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='engine_back')]
    ])


@dataclass
class UserSession:
    """User session for AI engine"""
    user_id: int
    loop: asyncio.AbstractEventLoop
    bot: any
    chat_id: int
    message_id: int
    platform_user: str
    platform_pass: str
    is_running: bool = True
    needs_cv_scrape: bool = False
    last_update_time: float = 0
    last_ui_text: str = ""
    solved_uuids: Set[str] = field(default_factory=set)
    stats: Dict[str, Any] = field(default_factory=lambda: {"total_hw": 0, "mistakes": 0, "solved_q": 0})
    hw_start_time: float = 0
    context: Optional[any] = None
    browser_pool: Optional[any] = None
    context_id: Optional[str] = None
    session_stats: Dict[str, Any] = field(default_factory=lambda: {
        'homeworks': 0,
        'questions': 0,
        'correct': 0,
        'wrong': 0,
        'start': time.time(),
        'completed_homeworks': []
    })
    last_progress_update: float = 0
    current_subject: str = ""
    current_question: int = 0
    total_questions: int = 0
    
    # ========== الحقول الجديدة للواجهة الثابتة ==========
    name: str = ""
    rank_title: str = "🥉 طالب جديد"
    plan_name: str = "مجاني"
    expiry_hijri: str = "—"
    base_message: str = ""
    base_template: str = ""
    last_remaining: int = 0
    total_solved: int = 0
    remaining: int = 0
    trials: int = 0
    is_subscribed: bool = False
    max_allowed: int = 0
    
    def update_ui(self, text: str, reply_markup=None):
        """تحديث واجهة المستخدم - نسخة محسنة"""
        if not self.is_running:
            return
        
        if self.last_ui_text == text:
            return
        
        current_time = time.time()
        if current_time - self.last_update_time < 1.0:
            return
        
        self.last_update_time = current_time
        self.last_ui_text = text
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                ), self.loop
            )
            future.result(timeout=5)
            
        except Exception as e:
            error_str = str(e)
            
            if "Message to edit not found" in error_str or "message can't be edited" in error_str:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.send_message(
                            chat_id=self.chat_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        ), self.loop
                    )
                    new_msg = future.result(timeout=5)
                    self.message_id = new_msg.message_id
                    
                except Exception:
                    pass
            
            elif "Message is not modified" not in error_str:
                print(f"UI Update Error: {error_str[:100]}")
    
    def update_progress(self, subject: str, current: int, total: int, eta: str = ""):
        """تحديث شريط التقدم"""
        self.current_subject = subject
        self.current_question = current
        self.total_questions = total
        
        percent = int((current / total) * 100) if total > 0 else 0
        bar_length = 20
        filled = int(round(bar_length * current / total)) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        text = (
            f"<b>📚 الواجب:</b> {subject}\n"
            f"<b>🔢 السؤال:</b> {current}/{total}\n"
            f"<b>📊 التقدم:</b> <code>[{bar}] {percent}%</code>\n"
        )
        if eta:
            text += f"<b>⏱️ الوقت المتبقي:</b> {eta}\n"
        
        self.update_ui(text, get_engine_keyboard(self))
    
    async def _save_homework_to_db(self, subject: str, total_q: int, correct: int, mistakes: int, percentage: float):
        """حفظ الواجب في قاعدة البيانات مع جميع الإحصائيات"""
        try:
            from hasad_bot.database import _db_pool
            import time
            
            conn = await _db_pool.get_connection()
            
            # ✅ تحديد وقت البداية (إما الموجود أو الوقت الحالي)
            start_time = self.hw_start_time if hasattr(self, 'hw_start_time') and self.hw_start_time > 0 else time.time()
            
            # ✅ جلب إحصائيات المصادر من الجلسة (إذا كانت موجودة)
            sources_stats = self.session_stats.get('sources', {})
            db_used = sources_stats.get('db', 0)
            groq_used = sources_stats.get('groq', 0)
            gemini_used = sources_stats.get('gemini', 0)
            random_used = sources_stats.get('random', 0)
            
            await conn.execute("""
                INSERT INTO homework_sessions 
                (user_id, subject, total_questions, solved_questions, correct_answers, wrong_answers, 
                 db_used, groq_used, gemini_used, random_used, status, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)
            """, (
                self.user_id, 
                subject, 
                total_q, 
                total_q,
                correct, 
                mistakes,
                db_used,
                groq_used,
                gemini_used,
                random_used,
                start_time, 
                time.time()
            ))
            await conn.commit()
            
            logger.info(f"📊 تم حفظ تقرير الواجب {subject} | DB:{db_used} Groq:{groq_used} Gemini:{gemini_used} Random:{random_used}")
        except Exception as e:
            logger.error(f"Failed to save homework report: {e}")

    def add_completed_homework(self, subject: str, total_q: int, solved: int, mistakes: int, actual_correct: int = None):
        """إضافة واجب مكتمل إلى السجل وحفظه في قاعدة البيانات

        Args:
            subject: اسم المادة
            total_q: إجمالي الأسئلة
            solved: عدد الأسئلة التي تم إرسال إجابة لها
            mistakes: عدد الإجابات الخاطئة من ودجة الموقع
            actual_correct: العدد الصحيح الفعلي من المنصة (مفضّل).
                إن لم يُمرَّر، نُرجع للسلوك القديم (افتراض كل إجابة صحيحة)
                مع تسجيل تحذير — هذا للتوافق الخلفي فقط.
        """
        if actual_correct is not None:
            # ✅ الإصلاح: نستخدم العدد الصحيح من المنصة (ودجة النتائج)
            correct = max(0, min(actual_correct, total_q))
        else:
            # ⚠️ Fallback قديم: نفترض solved صحيح. يُفضَّل تمرير actual_correct دائماً.
            correct = solved

        # حساب النسبة
        percentage = (correct / total_q * 100) if total_q > 0 else 0
        
        # إضافة إلى قائمة الواجبات في الجلسة
        self.session_stats['completed_homeworks'].append({
            'subject': subject,
            'total_questions': total_q,
            'solved': solved,
            'correct': correct,
            'mistakes': mistakes,
            'percentage': percentage,
            'time': time.time()
        })
        
        # تحديث الإحصائيات الإجمالية للجلسة
        # ✅ ملاحظة: 'correct' يُحدَّث في homework_solver/exam_solver عبر finish code
        #    (يستبدل التقدير المتفائل per-question بقيمة المنصة الفعلية).
        #    هنا نضيف فقط الحقول التي لم تُلمَس: homeworks, questions, wrong.
        self.session_stats['homeworks'] += 1
        self.session_stats['questions'] += total_q
        self.session_stats['wrong'] += mistakes
        
        # تحديث العداد المحلي
        self.total_solved += 1
        if self.is_subscribed:
            self.remaining -= 1
        else:
            self.trials -= 1
        
        # إعادة بناء الرسالة الأساسية
        if self.is_subscribed:
            self.base_message = self.base_template.format(
                total_solved=self.total_solved,
                remaining=self.remaining
            )
        else:
            self.base_message = self.base_template.format(
                total_solved=self.total_solved,
                trials=self.trials
            )
        
        # حفظ في قاعدة البيانات
        asyncio.create_task(self._save_homework_to_db(subject, total_q, correct, mistakes, percentage))
        
        admin_trace("HW_COMPLETED", f"{subject}: {correct}/{total_q} صحيح, {mistakes} خطأ ({percentage:.1f}%)", self.user_id)
        
    async def refresh_stats(self):
        """تحديث الإحصائيات من قاعدة البيانات"""
        from hasad_bot.database import get_user_homeworks_stats
        
        hw_stats = await get_user_homeworks_stats(self.user_id)
        self.total_solved = hw_stats['total_solved']
        self.remaining = hw_stats['remaining']
        
        if self.is_subscribed:
            self.base_message = self.base_template.format(
                total_solved=self.total_solved,
                remaining=self.remaining
            )
        else:
            self.trials = hw_stats['free_attempts']
            self.base_message = self.base_template.format(
                total_solved=self.total_solved,
                trials=self.trials
            )