#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Homework sessions: start, update, list.
"""
import time
from typing import List, Dict

import aiosqlite
from loguru import logger

from .pool import db_pool


async def start_homework_session(user_id: int, subject: str, homework_id: str = "",
                                  total_questions: int = 0) -> int:
    """بدء جلسة حل واجب"""
    try:
        conn = await db_pool.get_connection()

        logger.info(f"📊 [DB_SESSION_START] بدء جلسة قاعدة بيانات للمستخدم {user_id} | المادة: {subject} | عدد الأسئلة: {total_questions}")

        await conn.execute("""
            INSERT INTO homework_sessions
            (user_id, subject, homework_id, total_questions, start_time, status)
            VALUES (?, ?, ?, ?, ?, 'started')
        """, (user_id, subject, homework_id, total_questions, time.time()))
        await conn.commit()

        cursor = await conn.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        session_id = row[0] if row else 0

        logger.info(f"✅ [DB_SESSION_START] تم بدء جلسة قاعدة البيانات للمستخدم {user_id} | session_id: {session_id}")
        return session_id

    except Exception as e:
        logger.error(f"❌ [DB_SESSION_START] فشل بدء جلسة قاعدة البيانات للمستخدم {user_id}: {e}")
        return 0


async def update_homework_session(session_id: int,
                                   solved: int = None,
                                   correct: int = None,
                                   wrong: int = None,
                                   db_used: int = None,
                                   groq_used: int = None,
                                   gemini_used: int = None,
                                   random_used: int = None,
                                   status: str = None):
    """تحديث جلسة حل واجب"""
    try:
        conn = await db_pool.get_connection()

        updates = []
        values = []

        if solved is not None:
            updates.append("solved_questions = ?")
            values.append(solved)
        if correct is not None:
            updates.append("correct_answers = ?")
            values.append(correct)
        if wrong is not None:
            updates.append("wrong_answers = ?")
            values.append(wrong)
        if db_used is not None:
            updates.append("db_used = db_used + ?")
            values.append(db_used)
        if groq_used is not None:
            updates.append("groq_used = groq_used + ?")
            values.append(groq_used)
        if gemini_used is not None:
            updates.append("gemini_used = gemini_used + ?")
            values.append(gemini_used)
        if random_used is not None:
            updates.append("random_used = random_used + ?")
            values.append(random_used)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
            if status in ['completed', 'stopped']:
                updates.append("end_time = ?")
                values.append(time.time())

        if updates:
            values.append(session_id)
            await conn.execute(f"""
                UPDATE homework_sessions SET {', '.join(updates)} WHERE id = ?
            """, values)
            await conn.commit()
            logger.info(f"✅ Homework session {session_id} updated")

    except Exception as e:
        logger.error(f"Error updating homework session: {e}")


async def get_user_homework_sessions(user_id: int, limit: int = 10) -> List[Dict]:
    """جلب جلسات حل الواجبات لمستخدم معين"""
    try:
        conn = await db_pool.get_connection()
        conn.row_factory = aiosqlite.Row

        sessions = []
        async with conn.execute("""
            SELECT * FROM homework_sessions
            WHERE user_id = ?
            ORDER BY start_time DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            async for row in cursor:
                sessions.append(dict(row))

        return sessions
    except Exception as e:
        logger.error(f"Error getting user homework sessions: {e}")
        return []
