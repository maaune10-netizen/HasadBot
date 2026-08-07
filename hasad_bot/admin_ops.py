# -*- coding: utf-8 -*-
"""
عمليات الإدارة المشتركة - تُستخدم من Telegram (main.py) ومن لوحة التحكم (Web Dashboard)
إرسال الملفات المشفرة، النسخ الاحتياطي لقاعدة البيانات، وتصدير بيانات المنصة
"""

import asyncio
import io
import os
import tempfile
import time
import zipfile
import datetime as dt
from typing import Tuple, Dict, List, Optional
from uuid import uuid4
import aiosqlite
import msoffcrypto
import pyzipper
from pathlib import Path

from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, admin_trace, decrypt_password, gregorian_to_hijri
from hasad_bot.datetime_utils import datetime, now_timestamp
from hasad_bot.database import (
    _db_pool,
    db_all_users,
    db_get_user,
    db_set_user,
    db_delete_user,
    db_log,
    create_user_subscription,
    update_user_free_attempts,
    archive_user_credentials,
    log_admin_action,
    get_users_by_target,
    get_users_count_by_target,
)


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


# ==============================================================================
# عمليات الإدارة المشتركة - تُستخدم من Telegram ومن لوحة التحكم (Web Dashboard)
# كل دالة: تنفيذ التعديلات على قاعدة البيانات + إشعار المستخدم + تسجيل العملية
# ==============================================================================

async def _get_payment_request_by_id(request_id: int):
    """قراءة سجل طلب دفع بالمعرّف (None إذا لم يوجد)"""
    try:
        conn = await _db_pool.get_connection()
        async with conn.execute(
            "SELECT * FROM payment_requests WHERE id = ?",
            (request_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error reading payment request {request_id}: {e}")
        return None


async def renew_subscription(bot, uid: int, days: int, actor: str = "dashboard") -> Tuple[bool, str]:
    """تجديد اشتراك مستخدم (نفس منطق admin_renew_got_days)"""
    try:
        u = await db_get_user(uid)
        if not u:
            return (False, "❌ المستخدم غير موجود.")

        cur_exp = u.get("expiry_ts", 0) or 0
        if cur_exp < now_timestamp():
            cur_exp = now_timestamp()

        new_exp = cur_exp + days * 86400
        exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))
        # تحديث جدول users
        await db_set_user(uid, expiry_ts=new_exp, expiry_hijri=exp_h)

        # تحديد الخطة حسب عدد الأيام
        if days <= 7:
            plan_id = "weekly"
        elif days <= 30:
            plan_id = "monthly"
        else:
            plan_id = "semester"

        await create_user_subscription(uid, plan_id, cur_exp, new_exp)

        # إشعار للمستخدم
        try:
            await bot.send_message(
                uid,
                f"🎉 <b>تم تحديث اشتراكك!</b> +{days} يوم.\nالانتهاء: {exp_h}",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await log_admin_action(0, actor, "RENEW_SUBSCRIPTION",
                               target_user_id=uid, target_user_name=u.get("name", ""),
                               old_value=str(u.get("expiry_ts", 0) or 0), new_value=str(new_exp),
                               details=f"+{days} days, plan={plan_id}, end={exp_h}")
        admin_trace("RENEW_SUBSCRIPTION", f"User {uid} +{days}d (plan={plan_id}) by {actor}", uid=str(uid))

        return (True, f"✅ تم تجديد <code>{uid}</code> +{days} يوم | الانتهاء: {exp_h}")

    except Exception as e:
        logger.error(f"renew_subscription error: {e}")
        return (False, f"❌ خطأ: {e}")


async def revoke_subscription(bot, uid: int, actor: str = "dashboard") -> Tuple[bool, str]:
    """إلغاء اشتراك مستخدم (نفس منطق admin_revoke_done)"""
    try:
        u = await db_get_user(uid)
        if not u:
            return (False, "❌ المستخدم غير موجود.")

        await db_set_user(uid, expiry_ts=0, expiry_hijri="تم الإلغاء ❌")

        # إشعار للمستخدم
        try:
            await bot.send_message(
                uid,
                "🚫 <b>تم إلغاء اشتراكك من قبل الإدارة.</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await log_admin_action(0, actor, "REVOKE_SUBSCRIPTION",
                               target_user_id=uid, target_user_name=u.get("name", ""),
                               old_value=str(u.get("expiry_ts", 0) or 0), new_value="0",
                               details="Revoked by " + actor)
        admin_trace("REVOKE_SUBSCRIPTION", f"User {uid} revoked by {actor}", uid=str(uid))

        return (True, f"✅ تم إلغاء اشتراك <code>{uid}</code>.")

    except Exception as e:
        logger.error(f"revoke_subscription error: {e}")
        return (False, f"❌ خطأ: {e}")


async def add_homework_credit(bot, uid: int, count: int, kind: str) -> Tuple[bool, str]:
    """إضافة واجبات لمستخدم (kind: free للرصيد المجاني، sub لحد الاشتراك)"""
    try:
        user = await db_get_user(uid)
        if not user:
            return (False, "❌ المستخدم غير موجود.")
        name = user.get("name", uid)

        if kind == "free":
            # إضافة إلى free_attempts
            current = user.get("free_attempts", 0)
            new_value = current + count
            await update_user_free_attempts(uid, new_value)

            await db_log(0, "ADD_HOMEWORKS",
                         detail=f"User {uid} +{count} free (was {current}, now {new_value})")

            # إشعار للمستخدم
            try:
                await bot.send_message(
                    uid,
                    f"🎉 <b>تم إضافة {count} واجبات مجانية إلى رصيدك!</b>\n"
                    f"🎟️ رصيدك الحالي: {new_value} واجب",
                    parse_mode="HTML"
                )
            except Exception:
                pass

            await log_admin_action(0, "admin", "ADD_HOMEWORKS_FREE",
                                   target_user_id=uid, target_user_name=name,
                                   old_value=str(current), new_value=str(new_value),
                                   details=f"+{count} free homeworks")
            admin_trace("ADD_HOMEWORKS", f"User {uid} +{count} free (was {current}, now {new_value})", uid=str(uid))

            return (True, f"✅ <b>تمت الإضافة بنجاح!</b>\n\n"
                          f"👤 المستخدم: {name}\n"
                          f"➕ تم إضافة: {count} واجب (رصيد مجاني)\n"
                          f"🎟️ الرصيد الجديد: {new_value}")

        elif kind == "sub":
            # إضافة إلى max_homeworks في الاشتراك النشط
            conn = await _db_pool.get_connection()
            async with conn.execute("""
                SELECT id, max_homeworks FROM user_subscriptions
                WHERE user_id = ? AND is_active = 1 AND end_date > ?
                ORDER BY end_date DESC LIMIT 1
            """, (uid, time.time())) as cursor:
                sub = await cursor.fetchone()
            if not sub:
                return (False, "❌ لا يوجد اشتراك نشط لهذا المستخدم.")
            sub_id, current_max = sub
            new_max = current_max + count
            await conn.execute(
                "UPDATE user_subscriptions SET max_homeworks = ? WHERE id = ?",
                (new_max, sub_id)
            )
            await conn.commit()

            await db_log(0, "ADD_HOMEWORKS_SUB",
                         detail=f"User {uid} +{count} to subscription (was {current_max}, now {new_max})")

            # إشعار للمستخدم
            try:
                await bot.send_message(
                    uid,
                    f"🎉 <b>تم زيادة حد اشتراكك بمقدار {count} واجب!</b>\n"
                    f"📦 الحد الجديد: {new_max} واجب",
                    parse_mode="HTML"
                )
            except Exception:
                pass

            await log_admin_action(0, "admin", "ADD_HOMEWORKS_SUB",
                                   target_user_id=uid, target_user_name=name,
                                   old_value=str(current_max), new_value=str(new_max),
                                   details=f"+{count} to subscription limit")
            admin_trace("ADD_HOMEWORKS_SUB", f"User {uid} +{count} to subscription (was {current_max}, now {new_max})", uid=str(uid))

            return (True, f"✅ تم إضافة {count} واجبات إلى حد اشتراك المستخدم {name}.\n"
                          f"📦 الحد الجديد: {new_max} واجب")

        else:
            return (False, f"❌ نوع غير معروف: {kind}")

    except Exception as e:
        logger.error(f"add_homework_credit error: {e}")
        return (False, f"❌ خطأ: {e}")


async def approve_payment_request(bot, request_id: int, days: int, actor: str = "dashboard") -> Tuple[bool, str]:
    """تفعيل اشتراك من طلب دفع (نفس منطق set_days_callback / handle_custom_days_input)"""
    try:
        req = await _get_payment_request_by_id(request_id)
        if not req:
            return (False, "❌ طلب الدفع غير موجود.")
        if req.get("status") != "pending":
            return (False, f"❌ الطلب رقم {request_id} تمت معالجته مسبقاً (الحالة: {req.get('status')}).")

        uid = req["user_id"]
        u = await db_get_user(uid)
        if not u:
            return (False, f"❌ المستخدم {uid} غير موجود")

        # حساب تواريخ الاشتراك
        cur_exp = u.get("expiry_ts", 0) or 0
        if cur_exp < now_timestamp():
            cur_exp = now_timestamp()

        new_exp = cur_exp + days * 86400
        exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))
        # تحديث جدول users
        await db_set_user(uid, expiry_ts=new_exp, expiry_hijri=exp_h)

        # تحديد الخطة حسب عدد الأيام
        if days <= 7:
            plan_id = "weekly"
            max_homeworks = 25
        elif days <= 30:
            plan_id = "monthly"
            max_homeworks = 100
        else:
            plan_id = "semester"
            max_homeworks = 200

        await create_user_subscription(uid, plan_id, cur_exp, new_exp)

        # تحديث طلب الدفع
        try:
            conn = await _db_pool.get_connection()
            await conn.execute("""
                UPDATE payment_requests
                SET status = 'approved', processed_at = ?, processed_by = ?
                WHERE id = ? AND status = 'pending'
            """, (time.time(), actor, request_id))
            await conn.commit()
        except Exception:
            pass

        # إشعار للمستخدم
        try:
            await bot.send_message(
                uid,
                f"🎉 <b>تم تفعيل اشتراكك!</b> 🎉\n\n"
                f"📦 <b>الخطة:</b> {plan_id}\n"
                f"📚 <b>الواجبات:</b> {max_homeworks} واجب\n"
                f"📅 <b>المدة:</b> +{days} يوم\n"
                f"📆 <b>الانتهاء:</b> {exp_h}\n\n"
                f"🚀 استمتع بحل الواجبات!",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await log_admin_action(0, actor, "APPROVE_PAYMENT_REQUEST",
                               target_user_id=uid, target_user_name=req.get("user_name", ""),
                               old_value="pending", new_value="approved",
                               details=f"Request #{request_id}, +{days} days, plan={plan_id}")
        admin_trace("APPROVE_PAYMENT_REQUEST", f"Request #{request_id} approved for user {uid} (+{days}d, plan={plan_id}) by {actor}", uid=str(uid))

        return (True, f"✅ <b>تم التفعيل بنجاح!</b>\n\n"
                      f"👤 المستخدم: <code>{uid}</code>\n"
                      f"📅 المدة: {days} يوم\n"
                      f"📦 الخطة: {plan_id} ({max_homeworks} واجب)\n"
                      f"📆 الانتهاء: {exp_h}")

    except Exception as e:
        logger.error(f"approve_payment_request error: {e}")
        return (False, f"❌ خطأ: {e}")


async def reject_payment_request(bot, request_id: int, reason: str, actor: str = "dashboard") -> Tuple[bool, str]:
    """رفض طلب دفع (نفس منطق reject_reason_callback / handle_custom_reject)"""
    try:
        req = await _get_payment_request_by_id(request_id)
        if not req:
            return (False, "❌ طلب الدفع غير موجود.")
        if req.get("status") != "pending":
            return (False, f"❌ الطلب رقم {request_id} تمت معالجته مسبقاً (الحالة: {req.get('status')}).")

        uid = req["user_id"]

        # تحديث طلب الدفع
        try:
            conn = await _db_pool.get_connection()
            await conn.execute("""
                UPDATE payment_requests
                SET status = 'rejected', processed_at = ?, processed_by = ?
                WHERE id = ? AND status = 'pending'
            """, (time.time(), actor, request_id))
            await conn.commit()
        except Exception:
            pass

        # إشعار للمستخدم
        try:
            await bot.send_message(
                uid,
                f"❌ <b>تم رفض طلب الاشتراك</b>\n\n"
                f"📌 <b>السبب:</b> {reason}\n\n"
                f"💡 للاستفسار، تواصل مع الدعم الفني.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await log_admin_action(0, actor, "REJECT_PAYMENT_REQUEST",
                               target_user_id=uid, target_user_name=req.get("user_name", ""),
                               old_value="pending", new_value="rejected",
                               details=f"Request #{request_id}, reason: {reason}")
        admin_trace("REJECT_PAYMENT_REQUEST", f"Request #{request_id} rejected for user {uid} by {actor}", uid=str(uid))

        return (True, f"✅ <b>تم رفض الطلب!</b>\n\n"
                      f"👤 المستخدم: <code>{uid}</code>\n"
                      f"📌 السبب: {reason}")

    except Exception as e:
        logger.error(f"reject_payment_request error: {e}")
        return (False, f"❌ خطأ: {e}")


async def unlock_user(bot, uid: int, actor: str = "dashboard") -> Tuple[bool, str]:
    """فك قفل مستخدم مع أرشفة بيانات المنصة إن وجدت (نفس منطق cb_unlock)"""
    try:
        u = await db_get_user(uid)
        if not u:
            return (False, "❌ المستخدم غير موجود.")

        # أرشفة بيانات المنصة قبل فك القفل (إن وجدت)
        try:
            await archive_user_credentials(uid, 0, actor, "فك القفل بواسطة الإدارة")
        except Exception:
            pass

        await db_set_user(uid, locked_to=None, lock_request=0, dars360_user=None, dars360_pass=None)

        # إشعار للمستخدم
        try:
            await bot.send_message(
                uid,
                "🔓 <b>تم فك قفل حسابك.</b> يمكنك إضافة حساب جديد الآن.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await log_admin_action(0, actor, "UNLOCK_USER",
                               target_user_id=uid, target_user_name=u.get("name", ""),
                               details="Unlocked by " + actor)
        admin_trace("UNLOCK_USER", f"User {uid} unlocked by {actor}", uid=str(uid))

        return (True, f"✅ تم فك قفل <code>{uid}</code>.")

    except Exception as e:
        logger.error(f"unlock_user error: {e}")
        return (False, f"❌ خطأ: {e}")


async def delete_user(bot, uid: int, actor: str = "dashboard") -> Tuple[bool, str]:
    """حذف مستخدم مع جميع سجلاته (نفس منطق cb_delete)"""
    try:
        u = await db_get_user(uid)
        if not u:
            return (False, "❌ المستخدم غير موجود.")

        await db_delete_user(uid)

        await log_admin_action(0, actor, "DELETE_USER",
                               target_user_id=uid, target_user_name=u.get("name", ""),
                               details="Deleted by " + actor)
        admin_trace("DELETE_USER", f"User {uid} deleted by {actor}", uid=str(uid))

        return (True, f"🗑️ تم حذف <code>{uid}</code>.")

    except Exception as e:
        logger.error(f"delete_user error: {e}")
        return (False, f"❌ خطأ: {e}")


# ==============================================================================
# الإرسال الجماعي (Broadcast) والإعلانات — منطق مشترك مع لوحة التحكم
# ==============================================================================

# مخزن وظائف الإرسال الحية (broadcast + announcements)
SEND_JOBS: Dict[str, dict] = {}


def get_send_job(job_id: str) -> Optional[dict]:
    """قراءة نسخة آمنة من بيانات وظيفة إرسال (نسخة وليس مرجع)."""
    job = SEND_JOBS.get(job_id)
    if job is None:
        return None
    return {k: (list(v) if isinstance(v, list) else v) for k, v in job.items()}


def _new_job_id() -> str:
    """معرّف فريد لوظيفة إرسال."""
    return uuid4().hex


async def send_broadcast(bot, target: str, text: str, actor: str = "dashboard", progress_cb=None) -> dict:
    """إرسال رسالة جماعية نصية لفئة مستخدمين (نفس منطق admin_broadcast_send).

    target: all | subscribed | not_subscribed | linked | not_linked
    Returns: {"sent": n, "failed": n, "skipped": n, "errors": [...]}
    """
    valid_targets = ("all", "subscribed", "not_subscribed", "linked", "not_linked")
    if target not in valid_targets:
        return {"sent": 0, "failed": 0, "skipped": 0, "errors": [f"فئة غير معروفة: {target}"]}

    users = await get_users_by_target(target)
    total = len(users)
    sent = 0
    failed = 0
    skipped = 0
    errors: List[str] = []
    message = f"📢 <b>رسالة من الإدارة</b>\n\n{text}"

    admin_trace("BROADCAST_SEND", f"target={target} total={total} by {actor}", actor)

    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=message, parse_mode="HTML")
            sent += 1
        except Exception as e:
            err_msg = str(e)
            low = err_msg.lower()
            if any(k in low for k in ("blocked", "deactivated", "chat not found", "bot was kicked")):
                skipped += 1
            else:
                failed += 1
                errors.append(f"UID {user_id}: {err_msg[:80]}")
                logger.error(f"Failed to send to {user_id}: {e}")

        await asyncio.sleep(0.05)  # تجنب الـ Flood wait

        if progress_cb:
            progress_cb({
                "done": sent + failed + skipped,
                "total": total,
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
            })

    await log_admin_action(0, actor, "BROADCAST_SENT",
                           details=f"target={target} total={total} sent={sent} failed={failed} skipped={skipped}")
    admin_trace("BROADCAST_DONE", f"target={target} total={total} sent={sent} failed={failed} skipped={skipped}", actor)

    return {"sent": sent, "failed": failed, "skipped": skipped, "errors": errors}


def _update_job_progress(job_id: str, p: dict):
    """تحديث عدادات الوظيفة أثناء الإرسال."""
    job = SEND_JOBS.get(job_id)
    if not job:
        return
    job["sent"] = p.get("sent", 0)
    job["failed"] = p.get("failed", 0)
    job["skipped"] = p.get("skipped", 0)
    job["total"] = p.get("total", job["total"])


async def start_broadcast(bot, target: str, text: str, actor: str = "dashboard") -> str:
    """إنشاء وظيفة إرسال جماعي وتشغيلها في الخلفية. يرجع job_id."""
    job_id = _new_job_id()
    total = await get_users_count_by_target(target)
    SEND_JOBS[job_id] = {
        "job_id": job_id,
        "kind": "broadcast",
        "label": target,
        "status": "queued",
        "total": total,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
        "started_at": time.time(),
        "finished_at": None,
    }
    asyncio.create_task(_run_broadcast_job(job_id, bot, target, text, actor))
    return job_id


async def _run_broadcast_job(job_id: str, bot, target: str, text: str, actor: str):
    """تنفيذ وظيفة الإرسال الجماعي وتحديث الحالة."""
    job = SEND_JOBS[job_id]
    job["status"] = "running"
    try:
        result = await send_broadcast(
            bot, target, text, actor=actor,
            progress_cb=lambda p: _update_job_progress(job_id, p),
        )
        job["sent"] = result["sent"]
        job["failed"] = result["failed"]
        job["skipped"] = result["skipped"]
        job["errors"] = result["errors"]
    except Exception as e:
        job["errors"].append(str(e)[:200])
        logger.error(f"broadcast job {job_id} error: {e}")
    finally:
        job["status"] = "done"
        job["finished_at"] = time.time()


async def start_announcement_send(bot, atype: str, actor: str = "dashboard") -> str:
    """إنشاء وظيفة إرسال إعلان وتشغيلها في الخلفية. يرجع job_id."""
    job_id = _new_job_id()
    SEND_JOBS[job_id] = {
        "job_id": job_id,
        "kind": "announcement",
        "label": atype,
        "status": "queued",
        "total": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
        "started_at": time.time(),
        "finished_at": None,
    }
    asyncio.create_task(_run_announcement_job(job_id, bot, atype, actor))
    return job_id


async def _run_announcement_job(job_id: str, bot, atype: str, actor: str):
    """تنفيذ وظيفة إرسال الإعلان وتحديث الحالة + تسجيل العملية بعد الاكتمال."""
    from hasad_bot.handlers.announcements import send_announcement

    job = SEND_JOBS[job_id]
    job["status"] = "running"
    try:

        def _cb(p: dict):
            job["sent"] = p.get("sent", 0)
            job["skipped"] = p.get("skipped", 0)
            job["total"] = p.get("total", job["total"])
            job["errors"] = p.get("errors", 0)  # عدد مؤقت أثناء التقدم، يُستبدل بالقائمة عند الاكتمال

        sent, skipped, errors = await send_announcement(bot, atype, manual=True, progress_cb=_cb)
        job["sent"] = sent
        job["skipped"] = skipped
        job["errors"] = errors
        await log_admin_action(0, actor, "ANNOUNCEMENT_SENT",
                               details=f"type={atype} sent={sent} skipped={skipped} errors={len(errors)}")
        admin_trace("ANNOUNCEMENT_SENT", f"type={atype} sent={sent} skipped={skipped} errors={len(errors)} by {actor}", actor)
    except Exception as e:
        job["errors"].append(str(e)[:200])
        logger.error(f"announcement job {job_id} error: {e}")
    finally:
        job["status"] = "done"
        job["finished_at"] = time.time()
