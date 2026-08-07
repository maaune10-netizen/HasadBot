from typing import Optional, Tuple, List
import difflib
from loguru import logger
from hasad_bot.utils import (
    admin_trace,
    generate_knowledge_uuid,
    clean_question_text,
    clean_text_universal,
)
from hasad_bot.ai_engine.connection_pool import kb_pool


class KnowledgeBaseManager:

    @staticmethod
    def check_for_answer(subject_name: str, q_text: str, img_src: str, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        """⚠️ DEPRECATED - استخدم check_for_answer_async بدلاً منها"""
        logger.warning(f"⚠️ check_for_answer (sync) called - migrate to async!")
        raise DeprecationWarning("Use check_for_answer_async() instead")

    @staticmethod
    async def check_for_answer_async(subject_name: str, q_text: str, img_src: str, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        """البحث في قاعدة المعرفة — async باستخدام Connection Pool (بدون فتح/إغلاق)"""
        try:
            clean_text = clean_question_text(q_text) if q_text else ""
            img_uuid = generate_knowledge_uuid(clean_text, img_src)

            # 1. البحث بالـ UUID (أسرع)
            res = await kb_pool.fetchone(
                "SELECT answer FROM knowledge WHERE img_uuid = ?",
                (img_uuid,)
            )
            if res:
                admin_trace("DB_HIT", f"UUID: {img_uuid[:20]}...", user_id)
                return res[0], img_uuid

            # 2. البحث بالنص (أبطأ بس أدق)
            if clean_text:
                res = await kb_pool.fetchone(
                    "SELECT answer, img_uuid FROM knowledge WHERE question_text = ? LIMIT 1",
                    (clean_text,)
                )
                if res:
                    admin_trace("DB_HIT", f"Text: {clean_text[:40]}...", user_id)
                    return res[0], res[1]

        except Exception as e:
            admin_trace("DB_ERROR", str(e), user_id)
            logger.error(f"KB search error: {e}")

        return None, None

    @staticmethod
    async def save_answer(subject_name: str, q_text: str, img_src: str, answer: str):
        """حفظ إجابة في قاعدة المعرفة"""
        try:
            clean_text = clean_question_text(q_text) if q_text else ""
            img_uuid = generate_knowledge_uuid(clean_text, img_src)

            await kb_pool.execute(
                """INSERT OR REPLACE INTO knowledge
                   (subject_name, img_uuid, question_text, answer, status)
                   VALUES (?, ?, ?, ?, 'confirmed')""",
                (subject_name, img_uuid, clean_text, answer)
            )
            await kb_pool.commit()
        except Exception as e:
            logger.error(f"KB save error: {e}")

    @staticmethod
    def match_answer_to_option(db_answer: str, opts: List[str], user_id: int) -> Optional[int]:
        """مطابقة الإجابة من قاعدة البيانات مع خيارات السؤال"""
        try:
            db_ans_clean = clean_text_universal(db_answer)

            for i, opt in enumerate(opts):
                if db_ans_clean == clean_text_universal(opt):
                    return i + 1

            for i, opt in enumerate(opts):
                opt_clean = clean_text_universal(opt)
                if len(db_ans_clean) > 3 and len(opt_clean) > 3:
                    if db_ans_clean in opt_clean or opt_clean in db_ans_clean:
                        return i + 1

            best_match_idx, highest_ratio = -1, 0.0
            for i, opt in enumerate(opts):
                opt_clean = clean_text_universal(opt)
                ratio = difflib.SequenceMatcher(None, db_ans_clean, opt_clean).ratio()
                if ratio > highest_ratio and ratio >= 0.80:
                    highest_ratio = ratio
                    best_match_idx = i + 1

            if best_match_idx != -1:
                return best_match_idx

        except Exception as e:
            admin_trace("DB_MATCH_ERROR", str(e), user_id)

        return None
