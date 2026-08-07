import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import datetime
import os
import sqlite3
import pyzipper
from hasad_bot.config import config
from hasad_bot.utils import now_hijri
from telegram.ext import Application
from telegram import InputFile

async def backup():
    app = Application.builder().token(config.bot_token).build()
    db_path = config.knowledge_db
    channel_id = config.backup_channel_id
    
    # ✅ حساب عدد الصفوف في قاعدة المعرفة
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge")
        row_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"⚠️ فشل حساب عدد الصفوف: {e}")
        row_count = "غير معروف"
    
    # ✅ كلمة المرور من ملف .env
    password = os.environ.get("ZIP_PASSWORD", "Hasad_Default_2024").encode()
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Hasad_DB_Backup_{timestamp}.zip"
    
    # ✅ إنشاء ZIP مشفر بـ AES
    with pyzipper.AESZipFile(
        zip_filename, 
        'w',
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES
    ) as zipf:
        zipf.setpassword(password)
        zipf.write(db_path, os.path.basename(db_path))
    
    with open(zip_filename, 'rb') as doc:
        await app.bot.send_document(
            chat_id=channel_id, 
            document=InputFile(doc, filename=zip_filename),
            caption=(
                f'📦 **قاعدة المعرفة - نسخة احتياطية مشفرة**\n\n'
                f'📊 **عدد الأسئلة:** {row_count}\n'
                f'🔒 **نوع التشفير:** AES-256\n'
                f'📅 **التاريخ:** {now_hijri()}\n'
                f'📁 **حجم الملف:** {os.path.getsize(zip_filename) / 1024:.1f} KB'
            ),
            parse_mode='Markdown'
        )
    
    # ✅ إرسال كلمة المرور في رسالة منفصلة
    await app.bot.send_message(
        chat_id=channel_id,
        text=(
            f'🔑 **كلمة مرور فك الضغط** 🔑\n\n'
            f'⚠️ **احتفظ بهذه الكلمة في مكان آمن**\n'
            f'📌 لا يمكن فك الملف بدونها'
        ),
        parse_mode='HTML'
    )
    
    os.remove(zip_filename)
    print(f'✅ تم إرسال النسخة المشفرة للقناة | {row_count} سؤال | كلمة المرور: {password.decode()}')

asyncio.run(backup())