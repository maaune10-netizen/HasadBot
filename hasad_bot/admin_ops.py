# -*- coding: utf-8 -*-
"""
عمليات الإدارة المشتركة - تُستخدم من Telegram (main.py) ومن لوحة التحكم (Web Dashboard)
إرسال الملفات المشفرة، النسخ الاحتياطي لقاعدة البيانات، وتصدير بيانات المنصة
"""

import io
import os
import tempfile
import zipfile
import datetime as dt
import aiosqlite
import msoffcrypto
import pyzipper
from pathlib import Path

from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, admin_trace, decrypt_password
from hasad_bot.database import db_all_users


async def send_encrypted_excel_file(bot, chat_id, workbook, filename: str, caption: str):
    """تشفير Excel وإرساله (يفتح على الجوال)"""
    password = config.backup_password
    
    temp_input = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    temp_input.close()
    workbook.save(temp_input.name)
    
    temp_output = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    temp_output.close()
    
    try:
        with open(temp_input.name, 'rb') as f:
            office_file = msoffcrypto.OfficeFile(f)
            with open(temp_output.name, 'wb') as f_out:
                office_file.encrypt(password, f_out)
        
        with open(temp_output.name, 'rb') as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=filename,
                caption=f"{caption}\n🔐 **كلمة المرور:** `{password}`\n📅 {now_hijri()}\n\n✅ يفتح على Excel مباشرة (جوال + كمبيوتر)",
                parse_mode="Markdown"
            )
    finally:
        if os.path.exists(temp_input.name):
            os.unlink(temp_input.name)
        if os.path.exists(temp_output.name):
            os.unlink(temp_output.name)


async def send_encrypted_zip_file(bot, chat_id, file_path, caption: str):
    """إرسال ZIP مشفر (لقاعدة البيانات واللوجات)"""
    from pathlib import Path
    
    password = config.backup_password
    original_name = file_path.name
    zip_filename = f"{original_name}.zip"
    zip_path = Path(tempfile.gettempdir()) / zip_filename
    
    try:
        with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
            zipf.setpassword(password.encode())
            zipf.write(file_path, original_name)
        
        with open(zip_path, 'rb') as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=zip_filename,
                caption=f"{caption}\n🔐 **كلمة المرور:** `{password}`\n📅 {now_hijri()}\n\n⚠️ ملف ZIP محمي (يفتح على الكمبيوتر)",
                parse_mode="Markdown"
            )
    finally:
        if zip_path.exists():
            zip_path.unlink()


async def send_db_backup(bot, chat_id=None):
    """Send database backup to channel"""
    db_path = config.knowledge_db
    channel_id = chat_id if chat_id is not None else config.backup_channel_id
    
    if not os.path.exists(db_path):
        logger.warning("⚠️ No database to backup")
        print("⚠️ لا توجد قاعدة بيانات للنسخ الاحتياطي")
        return
    
    if not channel_id:
        logger.warning("⚠️ BACKUP_CHANNEL_ID not set")
        print("⚠️ BACKUP_CHANNEL_ID غير معرف في ملف .env")
        return
    
    zip_filename = f"Hasad_DB_Backup_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(db_path, os.path.basename(db_path))
        
        with open(zip_filename, 'rb') as doc:
            await bot.send_document(
                chat_id=channel_id,
                document=doc,
                caption=f"📦 **قاعدة المعرفة**\n📅 {now_hijri()}",
                parse_mode="Markdown"
            )
        
        admin_trace("BACKUP_SUCCESS", "Database backup sent")
        logger.success("✅ Backup sent")
        print(f"✅ تم إرسال النسخة الاحتياطية للقناة: {zip_filename}")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        print(f"❌ خطأ في النسخ الاحتياطي: {e}")
    finally:
        if os.path.exists(zip_filename):
            os.remove(zip_filename)


async def send_cv_export(bot, chat_id=None):
    """Export CV data to Excel - مع تنسيقات كيو كيو"""
    print("✅ بدء تصدير بيانات CV...")
    
    channel_id = chat_id if chat_id is not None else config.backup_channel_id
    
    if not channel_id:
        print("❌ BACKUP_CHANNEL_ID غير معرف في ملف .env")
        return
    
    if not config.harvest_db.exists():
        print(f"❌ ملف قاعدة البيانات غير موجود: {config.harvest_db}")
        return
    
    try:
        async with aiosqlite.connect(config.harvest_db) as db:
            # إنشاء الجدول إذا لم يكن موجوداً
            await db.execute('''
                CREATE TABLE IF NOT EXISTS student_cvs_v2 (
                    platform_user TEXT PRIMARY KEY,
                    telegram_id INTEGER,
                    local_name TEXT,
                    latin_name TEXT,
                    identity_no TEXT,
                    phone TEXT,
                    nationality TEXT,
                    stage TEXT,
                    grade TEXT,
                    student_class TEXT,
                    profile_pic TEXT,
                    scraped_at REAL
                )
            ''')
            
            # عد السجلات
            async with db.execute("SELECT COUNT(*) FROM student_cvs_v2") as cursor:
                count = await cursor.fetchone()
                total_records = count[0] if count else 0
                print(f"📊 عدد السجلات: {total_records}")
            
            if total_records == 0:
                print("❌ لا توجد بيانات في الجدول")
                return
            
            # إنشاء ملف Excel بالتنسيقات
            from openpyxl import Workbook
            from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
            
            wb = Workbook()
            ws = wb.active
            ws.title = "سجلات الطلاب (حصاد)"
            ws.sheet_view.rightToLeft = True
            
            # تنسيقات كيو كيو
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            green_fill  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
            alt_row_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            
            bold_white_font = Font(name='Tahoma', size=11, bold=True, color="FFFFFF")
            normal_font = Font(name='Tahoma', size=10)
            center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin_border = Border(
                left=Side(style='thin'), right=Side(style='thin'),
                top=Side(style='thin'), bottom=Side(style='thin')
            )
            
            headers = [
                'Telegram ID', 'Platform User', 'الاسم بالعربية', 'الاسم باللاتينية',
                'رقم الهوية', 'الجوال', 'الجنسية', 'المرحلة', 'الصف', 'الفصل', 'تاريخ السحب'
            ]
            ws.append(headers)
            
            # تنسيق الهيدر
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = bold_white_font
                cell.alignment = center_align
                cell.border = thin_border
            
            rows_added = 0
            async with db.execute("SELECT * FROM student_cvs_v2") as cursor:
                async for row in cursor:
                    scrape_date = dt.datetime.fromtimestamp(row[11]).strftime('%Y-%m-%d %H:%M') if len(row) > 11 else ""
                    row_data = [
                        row[1], row[0], row[2], row[3], row[4],
                        row[5], row[6], row[7], row[8], row[9], scrape_date
                    ]
                    ws.append(row_data)
                    rows_added += 1
                    
                    # تنسيق الصفوف مثل كيو كيو
                    current_row = ws[ws.max_row]
                    for col_idx, cell in enumerate(current_row):
                        cell.font = normal_font
                        cell.alignment = center_align
                        cell.border = thin_border
                        
                        # تلوين الصفوف الفردية والزوجية
                        if rows_added % 2 == 0:
                            cell.fill = alt_row_fill
                        
                        # تلوين خاص لبعض الأعمدة
                        if col_idx == 1:  # Platform User
                            cell.fill = yellow_fill
                            cell.font = Font(name='Tahoma', size=10, bold=True, color="C00000")
                        elif col_idx == 10:  # تاريخ السحب
                            cell.fill = green_fill
            
            # ضبط عرض الأعمدة
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                ws.column_dimensions[column].width = min((max_length + 4), 40)
            
            # حفظ الملف
            excel_stream = io.BytesIO()
            wb.save(excel_stream)
            excel_stream.seek(0)
            excel_stream.name = f"CV_Export_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            
            print(f"📁 تم إنشاء الملف: {excel_stream.name}")
            print(f"📤 جاري الإرسال للقناة...")
            
            # إرسال للقناة
            caption = f"🚨 <b>تم استخراج سجلات الطلاب</b> 🕵️\nعدد السجلات: <b>{rows_added}</b>\n📅 {now_hijri()}"
            
            await bot.send_document(
                chat_id=channel_id,
                document=excel_stream,
                caption=caption,
                parse_mode="HTML"
            )
            
            print(f"✅ تم إرسال ملف الإكسل الملون للقناة! ({rows_added} سجل)")
            
    except Exception as e:
        logger.error(f"CV export error: {e}")
        print(f"❌ خطأ في تصدير الملف: {e}")
        import traceback
        traceback.print_exc()


async def extract_credentials(bot, chat_id=None):
    """استخراج بيانات المنصة - ملف Excel ملون ومدلع"""
    print("🔑 بدء استخراج بيانات المنصة...")
    
    channel_id = chat_id if chat_id is not None else config.backup_channel_id
    
    if not channel_id:
        print("❌ BACKUP_CHANNEL_ID غير معرف في ملف .env")
        return
    
    try:
        users = await db_all_users()
        
        # فلترة المستخدمين اللي عندهم حسابات منصة
        filtered_users = []
        for u in users:
            if u.get('dars360_user') and u.get('dars360_pass'):
                pass_plain = decrypt_password(u['dars360_pass'])
                filtered_users.append({
                    'telegram_id': u['telegram_id'],
                    'name': u.get('name', ''),
                    'platform_user': u['dars360_user'],
                    'password': pass_plain,
                    'expiry': u.get('expiry_hijri', ''),
                    'free_attempts': u.get('free_attempts', 0)
                })
        
        if not filtered_users:
            print("📭 لا توجد بيانات منصة مخزنة.")
            return
        
        print(f"📊 عدد الحسابات: {len(filtered_users)}")
        
        # إنشاء ملف Excel بالتنسيقات
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        import io
        import datetime
        
        wb = Workbook()
        ws = wb.active
        ws.title = "بيانات المنصة"
        ws.sheet_view.rightToLeft = True
        
        # تنسيقات كيو كيو
        header_fill = PatternFill(start_color="8B0000", end_color="8B0000", fill_type="solid")  # أحمر غامق
        vip_fill = PatternFill(start_color="C6E0B4", end_color="C6E0B4", fill_type="solid")  # أخضر فاتح للـ VIP
        normal_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        alt_row_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        
        bold_white_font = Font(name='Tahoma', size=11, bold=True, color="FFFFFF")
        normal_font = Font(name='Tahoma', size=10)
        bold_red_font = Font(name='Tahoma', size=10, bold=True, color="8B0000")
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        
        headers = [
            'Telegram ID', 'الاسم', 'يوزر المنصة', 'كلمة المرور (مفكوكة)',
            'الصلاحية', 'واجبات مجانية', 'VIP'
        ]
        ws.append(headers)
        
        # تنسيق الهيدر
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = bold_white_font
            cell.alignment = center_align
            cell.border = thin_border
        
        # إضافة البيانات
        for idx, u in enumerate(filtered_users):
            # التحقق إذا كان المستخدم VIP (مشترك)
            is_vip = u['expiry'] and u['expiry'] not in ['', 'تم الإلغاء ❌']
            
            row_data = [
                u['telegram_id'],
                u['name'],
                u['platform_user'],
                u['password'],
                u['expiry'],
                u['free_attempts'],
                '✅' if is_vip else '❌'
            ]
            ws.append(row_data)
            
            # تنسيق الصف
            current_row = ws[ws.max_row]
            for col_idx, cell in enumerate(current_row):
                cell.font = normal_font
                cell.alignment = center_align
                cell.border = thin_border
                
                # تلوين الصفوف الفردية والزوجية
                if idx % 2 == 0:
                    cell.fill = alt_row_fill
                
                # تلوين خاص للأعمدة
                if col_idx == 2:  # يوزر المنصة
                    cell.font = bold_red_font
                elif col_idx == 3:  # كلمة المرور
                    cell.font = Font(name='Courier New', size=10, bold=True)
                
                # تلوين صفوف VIP بالكامل
                if is_vip:
                    cell.fill = vip_fill
        
        # ضبط عرض الأعمدة
        column_widths = [15, 25, 20, 25, 20, 15, 8]
        for i, width in enumerate(column_widths):
            ws.column_dimensions[chr(65 + i)].width = width
        
        # حفظ الملف
        excel_stream = io.BytesIO()
        wb.save(excel_stream)
        excel_stream.seek(0)
        excel_stream.name = f"Platform_Credentials_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        
        print(f"📁 تم إنشاء الملف: {excel_stream.name}")
        print(f"📤 جاري الإرسال للقناة...")
        
        # إرسال للقناة
        caption = f"🔑 <b>استخراج بيانات المنصة</b>\n"
        caption += f"عدد الحسابات: <b>{len(filtered_users)}</b>\n"
        caption += f"✅ VIP: <b>{sum(1 for u in filtered_users if u['expiry'] and u['expiry'] not in ['', 'تم الإلغاء ❌'])}</b>\n"
        caption += f"📅 {now_hijri()}"
        
        await bot.send_document(
            chat_id=channel_id,
            document=excel_stream,
            caption=caption,
            parse_mode="HTML"
        )
        
        print(f"✅ تم إرسال ملف البيانات للقناة! ({len(filtered_users)} حساب)")
        
        # كمان نعرض في التيرمينال ملخص
        print(f"\n🔑 ملخص الحسابات المستخرجة:")
        print(f"   إجمالي: {len(filtered_users)}")
        print(f"   VIP: {sum(1 for u in filtered_users if u['expiry'] and u['expiry'] not in ['', 'تم الإلغاء ❌'])}")
        print(f"   عادي: {sum(1 for u in filtered_users if not u['expiry'] or u['expiry'] in ['', 'تم الإلغاء ❌'])}")
        
    except Exception as e:
        logger.error(f"Extract error: {e}")
        print(f"❌ خطأ في الاستخراج: {e}")
        import traceback
        traceback.print_exc()


# اسم قديم محتفظ به للتوافق مع الاستدعاءات القائمة (terminal/CLI)
extract_credentials_terminal = extract_credentials


async def send_encrypted_file(bot, chat_id: int, file_path: Path, caption: str, password: str = None, custom_name: str = None):
    """
    إرسال ملف مشفر ومحمي بكلمة مرور
    """
    import tempfile
    import os
    import pyzipper
    
    if password is None:
        password = config.backup_password
    
    # ✅ تحديد اسم الملف النهائي
    if custom_name:
        zip_filename = custom_name
    else:
        # استخراج اسم الملف الأصلي بدون مسار
        original_name = file_path.stem
        zip_filename = f"{original_name}.zip"
    
    # إنشاء ملف ZIP مؤقت باسم منظم
    temp_dir = tempfile.gettempdir()
    zip_path = Path(temp_dir) / zip_filename
    
    try:
        # إنشاء ZIP مشفر بكلمة مرور
        with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zipf:
            zipf.setpassword(password.encode())
            zipf.write(file_path, os.path.basename(file_path))
        
        # إرسال الملف
        with open(zip_path, 'rb') as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=zip_filename,  # ✅ اسم واضح ومنظم
                caption=f"🔒 **{caption}**\n🔐 **محمي بكلمة مرور**\n📅 {now_hijri()}\n\n📌 **كلمة المرور:** `{password}`",
                parse_mode="Markdown"
            )
            
    finally:
        # حذف الملف المؤقت
        if zip_path.exists():
            zip_path.unlink()
