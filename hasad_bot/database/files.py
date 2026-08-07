#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram file/image download + local path storage.
"""
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

from hasad_bot.config import config
from .pool import db_pool


IMAGES_DIR = Path(config.knowledge_dir) / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

FILES_DIR = Path(config.knowledge_dir) / "support_files"
FILES_DIR.mkdir(parents=True, exist_ok=True)


async def download_and_save_image(bot, file_id: str, chat_id: int, message_id: int, user_id: int) -> str:
    """تحميل صورة من تليجرام وحفظها محلياً"""
    try:
        file = await bot.get_file(file_id)

        timestamp = int(time.time())
        filename = f"user_{user_id}_chat_{chat_id}_msg_{message_id}_{timestamp}.jpg"
        file_path = IMAGES_DIR / filename

        await file.download_to_drive(file_path)

        logger.info(f"📸 Image saved locally: {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        return ""


async def save_image_reference(image_path: str, file_id: str, user_id: int, chat_id: int, message_id: int):
    """حفظ مرجع الصورة في قاعدة البيانات"""
    try:
        conn = await db_pool.get_connection()

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stored_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                local_path TEXT,
                user_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                created_at REAL
            )
        """)

        await conn.execute("""
            INSERT INTO stored_images (file_id, local_path, user_id, chat_id, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (file_id, image_path, user_id, chat_id, message_id, time.time()))

        await conn.commit()
        logger.info(f"📸 Image reference saved: {image_path}")

    except Exception as e:
        logger.error(f"Error saving image reference: {e}")


async def download_and_save_file(bot, file_id: str, file_type: str, file_name: str, chat_id: int, message_id: int, user_id: int) -> str:
    """تحميل ملف من تليجرام وحفظه محلياً"""
    try:
        file = await bot.get_file(file_id)

        timestamp = int(time.time())
        unique_name = f"{file_type}_{user_id}_{chat_id}_{message_id}_{timestamp}_{file_name}"

        dangerous_chars = '<>:"/\\|?*'
        for char in dangerous_chars:
            unique_name = unique_name.replace(char, '_')

        file_path = FILES_DIR / unique_name
        await file.download_to_drive(file_path)

        logger.info(f"📁 File saved locally: {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return ""


async def save_file_reference(file_path: str, file_id: str, file_type: str, file_name: str, user_id: int, chat_id: int, message_id: int):
    """حفظ مرجع الملف في قاعدة البيانات"""
    try:
        conn = await db_pool.get_connection()

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stored_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                file_type TEXT,
                file_name TEXT,
                local_path TEXT,
                user_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                created_at REAL
            )
        """)

        await conn.execute("""
            INSERT INTO stored_files (file_id, file_type, file_name, local_path, user_id, chat_id, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (file_id, file_type, file_name, file_path, user_id, chat_id, message_id, time.time()))

        await conn.commit()
        logger.info(f"📁 File reference saved: {file_path}")

    except Exception as e:
        logger.error(f"Error saving file reference: {e}")


async def get_image_path(file_id: str) -> Optional[str]:
    """الحصول على المسار المحلي للصورة من معرفها"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute(
            "SELECT local_path FROM stored_images WHERE file_id = ?", (file_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["local_path"]:
                path = Path(row["local_path"])
                if path.exists():
                    return str(path)
        return None

    except Exception as e:
        logger.error(f"Error getting image path: {e}")
        return None
