#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Exam answer cache: voting + confirmation.
"""
import time
from collections import Counter
from typing import Optional, Tuple

import aiosqlite
from loguru import logger

from hasad_bot.utils import admin_trace
from .pool import db_pool


async def update_exam_vote(exam_id: str, exam_name: str, question_number: int,
                            question_text: str, answer: str, user_id: int) -> Tuple[Optional[str], bool]:
    """
    تحديث أصوات المستخدمين وتأكيد الإجابة إذا وصلنا لـ 3 أصوات متطابقة
    إرجاع: (الإجابة المؤكدة, هل تم التأكيد؟)
    """
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("""
            SELECT * FROM exam_cache
            WHERE exam_id = ? AND question_number = ?
        """, (exam_id, question_number)) as c:
            existing = await c.fetchone()

        if existing and existing['confirmed'] == 1:
            return existing['correct_answer'], True

        if existing:
            votes = existing['votes_for_answer'].split(',') if existing['votes_for_answer'] else []
            votes.append(str(answer))
            votes_for_answer = ','.join(votes)
            total_votes = len(votes)

            vote_counts = Counter(votes)
            most_common = vote_counts.most_common(1)[0]
            most_common_answer = most_common[0]
            most_common_count = most_common[1]

            if most_common_count >= 3:
                await conn.execute("""
                    UPDATE exam_cache
                    SET total_votes = ?,
                        votes_for_answer = ?,
                        correct_answer = ?,
                        confirmed = 1,
                        confirmed_at = ?,
                        updated_at = ?
                    WHERE exam_id = ? AND question_number = ?
                """, (total_votes, votes_for_answer, most_common_answer, time.time(), time.time(), exam_id, question_number))

                admin_trace("EXAM_CONFIRMED", f"✅ Exam {exam_id} Q{question_number} confirmed: {most_common_answer} (votes: {most_common_count}/{total_votes})")
                return most_common_answer, True
            else:
                await conn.execute("""
                    UPDATE exam_cache
                    SET total_votes = ?,
                        votes_for_answer = ?,
                        updated_at = ?
                    WHERE exam_id = ? AND question_number = ?
                """, (total_votes, votes_for_answer, time.time(), exam_id, question_number))

                admin_trace("EXAM_VOTE", f"📊 Exam {exam_id} Q{question_number}: {most_common_answer} ({most_common_count}/{total_votes})")
                return None, False
        else:
            await conn.execute("""
                INSERT INTO exam_cache
                (exam_id, exam_name, question_number, question_text, total_votes, votes_for_answer, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """, (exam_id, exam_name, question_number, question_text, str(answer), time.time(), time.time()))

            admin_trace("EXAM_FIRST_VOTE", f"📝 Exam {exam_id} Q{question_number}: first vote = {answer}")
            return None, False

    except Exception as e:
        logger.error(f"Error updating exam vote: {e}")
        return None, False


async def get_confirmed_exam_answer(exam_id: str, question_number: int) -> Optional[str]:
    """
    قراءة الإجابة المؤكدة من قاعدة البيانات
    """
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("""
            SELECT correct_answer FROM exam_cache
            WHERE exam_id = ? AND question_number = ? AND confirmed = 1
        """, (exam_id, question_number)) as c:
            row = await c.fetchone()
            return row[0] if row else None

    except Exception as e:
        logger.error(f"Error getting confirmed exam answer: {e}")
        return None
