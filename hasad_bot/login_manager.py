#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Login Manager for HASAD Bot - النسخة البطيئة V6 (متعددة المنصات)
مسؤول عن تسجيل الدخول إلى منصة درس 360 (جميع المدارس) واستخراج بيانات الطالب
يدعم: alamjad1, alamjad2, riyadahschool, bloom, althuraya, alkhloud, fl, albushra, alshima, atyab, qyem-q
"""

import asyncio
import random
from typing import Tuple, Optional, Dict, Any, List
from pathlib import Path

from loguru import logger

from hasad_bot.config import config
from hasad_bot.database import db_set_user, db_save_cv
from hasad_bot.playwright_engine import _browser_pool
from hasad_bot.utils import admin_trace, encrypt_password, now_hijri, log_error_with_code
from hasad_bot.ai_engine.selectors import URLS, LOGIN, PROFILE


# ==============================================================================
# قائمة المدارس (المنصات) - من المركزية
# ==============================================================================

# تم نقل SCHOOLS إلى URLS.SCHOOLS في hasad_bot.ai_engine.selectors


# ==============================================================================
# ثوابت الموقع - محسنة (أبطأ)
# ==============================================================================

# سيتم تحديد LOGIN_URL و PROFILE_URL ديناميكياً بناءً على المدرسة المختارة

TIMEOUTS = {
    "login_page": 60000,      # 60 ثانية
    "navigation": 45000,       # 45 ثانية
    "element": 20000,          # 20 ثانية
    "profile": 45000,          # 45 ثانية
    "profile_element": 20000,  # 20 ثانية
    "post_submit_network": 30000,  # 30 ثانية — انتظار الشبكة بعد النقر
}

# ✅ تأخيرات بشرية (أبطأ وأكثر طبيعية)
DELAY_RANGES = {
    "click": (800, 2000),      # 0.8-2 ثانية
    "type": (200, 600),        # 0.2-0.6 ثانية
    "between": (1000, 2500),   # 1-2.5 ثانية
    "post_login": (2000, 4000),# 2-4 ثانية
    "pre_submit": (1500, 3000),# 1.5-3 ثانية
}

# ✅ محاولات إعادة عند فشل النقر (البطء في الشبكة) — 3 محاولات كافية
MAX_LOGIN_RETRIES = 3


# ==============================================================================
# دوال مساعدة
# ==============================================================================

async def random_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
    """تأخير عشوائي (بطيء) لمحاكاة البشر"""
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


async def human_type(page, selector: str, text: str):
    """كتابة نص مثل البشر (حرف حرف مع تأخير)"""
    await page.locator(selector).click()
    await random_delay(300, 800)
    
    for char in text:
        await page.locator(selector).press(char)
        await random_delay(50, 150)


def get_schools_list() -> List[Dict[str, str]]:
    """الحصول على قائمة المدارس بشكل عشوائي"""
    schools_list = [
        {"id": school_id, "name": info["name"], "url": info["base"]}
        for school_id, info in URLS.SCHOOLS.items()
    ]
    # ✅ خلط القائمة بشكل عشوائي
    random.shuffle(schools_list)
    return schools_list

def get_school_info(school_id: str) -> Optional[Dict]:
    """الحصول على معلومات المدرسة حسب المعرف"""
    info = URLS.SCHOOLS.get(school_id)
    if info:
        return {
            "name": info["name"],
            "base_url": info["base"],
            "login_url": info["login"],
            "profile_url": info["profile"]
        }
    return None


async def check_login_success(page, base_url: str) -> Tuple[bool, str]:
    """
    التحقق من نجاح تسجيل الدخول باستخدام معايير متعددة
    إرجاع: (نجاح, سبب النجاح أو الفشل)
    """
    try:
        current_url = page.url
        
        # ✅ 1. التحقق من الرابط
        for success_url in URLS.SUCCESS_URLS:
            if success_url in current_url:
                admin_trace("LOGIN_CHECK", f"✅ نجاح: الرابط يحتوي على {success_url}")
                return True, f"تم التوجيه إلى {success_url}"
        
        # ✅ 2. التحقق من النصوص في الصفحة
        page_content = await page.content()
        for success_text in LOGIN.SUCCESS_TEXTS:
            if success_text in page_content:
                admin_trace("LOGIN_CHECK", f"✅ نجاح: تم العثور على نص '{success_text}'")
                return True, f"تم العثور على نص '{success_text}'"
        
        # ✅ 3. التحقق من العناصر في الصفحة
        for selector in LOGIN.SUCCESS_SELECTORS:
            element_exists = await page.locator(selector).count() > 0
            if element_exists:
                admin_trace("LOGIN_CHECK", f"✅ نجاح: تم العثور على عنصر '{selector}'")
                return True, f"تم العثور على عنصر '{selector}'"
        
        # ❌ لم نجد أي معيار نجاح
        admin_trace("LOGIN_CHECK", f"❌ فشل: لم يتم العثور على أي معيار نجاح. URL: {current_url[:100]}")
        return False, "لم يتم العثور على معايير النجاح في الصفحة"
        
    except Exception as e:
        admin_trace("LOGIN_CHECK_ERR", f"خطأ في التحقق: {e}")
        return False, f"خطأ في التحقق: {str(e)[:50]}"


# ==============================================================================
# دوال التحقق من نوع الحساب
# ==============================================================================

def is_teacher_account(username: str) -> Tuple[bool, str]:
    """التحقق من نوع الحساب (طالب/أستاذ)"""
    if not username:
        return True, "اسم المستخدم فارغ (أستاذ محتمل)"
    
    is_student = username.isdigit() and len(username) in [10, 11, 9]

    
    if is_student:
        return False, f"طالب (رقم هوية {len(username)} أرقام)"
    
    if username.isdigit():
        reason = f"عدد الأرقام {len(username)} (غير 10) - أستاذ"
    elif '@' in username:
        reason = "يحتوي على إيميل (@) - أستاذ"
    elif any(c.isalpha() for c in username):
        reason = "يحتوي على حروف - أستاذ"
    else:
        reason = "غير مطابق لرقم هوية 10 أرقام - أستاذ"
    
    return True, reason


# ==============================================================================
# دوال تسجيل الدخول - نسخة بطيئة (محاكاة بشرية) مع دعم متعدد المنصات
# ==============================================================================

async def perform_login(page, username: str, password: str, login_url: str) -> Tuple[bool, str]:
    """
    تسجيل الدخول ببطء (محاكاة سلوك بشري)
    يدعم أي رابط تسجيل دخول، مع صبر على الشبكات البطيئة
    """

    for attempt in range(MAX_LOGIN_RETRIES):
        try:
            admin_trace("LOGIN_ATTEMPT", f"محاولة {attempt + 1}/{MAX_LOGIN_RETRIES} لـ {username} | URL: {login_url}")

            # ✅ انتظر تحميل الصفحة
            await page.goto(login_url, timeout=TIMEOUTS["login_page"])
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # بعض الصفحات لا تصل networkidle، نكمل
            await random_delay(1000, 2000)

            # ✅ انتظر ظهور الحقول
            await page.wait_for_selector(LOGIN.USERNAME, state="visible", timeout=TIMEOUTS["element"])
            await random_delay(500, 1000)

            # ✅ كتابة اسم المستخدم
            await page.locator(LOGIN.USERNAME).click()
            await random_delay(300, 800)
            await page.locator(LOGIN.USERNAME).fill(str(username))

            # ✅ تأخير بين الحقول
            await random_delay(*DELAY_RANGES["between"])

            # ✅ كتابة كلمة المرور
            await page.locator(LOGIN.PASSWORD).click()
            await random_delay(300, 800)
            await page.locator(LOGIN.PASSWORD).fill(str(password))

            # ✅ تأخير قبل النقر
            await random_delay(*DELAY_RANGES["pre_submit"])

            # ✅ النقر على زر تسجيل الدخول
            await page.locator(LOGIN.SUBMIT).click()

            # ============================================================
            # ⏳ هنا كان المشكلة: البوت ما كان يستنى الصفحة تتحمّل بعد النقر
            # ============================================================
            # نعطي وقت كافي + ننتظر اكتمال الشبكة قبل فحص النتيجة
            await random_delay(3000, 5000)

            # ✅ انتظر اكتمال تحميل الشبكة بعد النقر (حتى 30 ثانية للشبكات البطيئة)
            try:
                await page.wait_for_load_state("networkidle", timeout=TIMEOUTS["post_submit_network"])
                admin_trace("LOGIN_LOAD_OK", "✅ networkidle reached after submit", page_url=page.url)
            except Exception as load_err:
                # networkidle لم يتحقق — هذا متوقع مع شبكة بطيئة جداً
                admin_trace("LOGIN_LOAD_SLOW", f"⚠️ networkidle لم يتحقق: {str(load_err)[:80]} | URL: {page.url}")
                # نعطيه وقت إضافي قبل الحكم
                await random_delay(3000, 5000)

            # ✅ تحقق من رسالة الخطأ (بعد ما استقرت الصفحة)
            error_element = await page.locator(LOGIN.ERROR_VISIBLE).count()
            if error_element > 0:
                error_text = await page.locator(LOGIN.ERROR_MSG).text_content()
                admin_trace("LOGIN_ERROR", f"رسالة خطأ: {error_text}")
                if attempt == MAX_LOGIN_RETRIES - 1:
                    return False, f"❌ {error_text}"
                await random_delay(2000, 4000)
                continue

            # ✅ تحقق من نجاح الدخول (باستخدام المعايير الجديدة)
            base_url = login_url.replace(URLS.LOGIN_PAGE, "").replace("?returnUrl=%2F", "")
            success, reason = await check_login_success(page, base_url)

            if success:
                admin_trace("LOGIN_SUCCESS", f"تم الدخول بنجاح: {reason}")
                await random_delay(1000, 2000)
                return True, f"✅ تم تسجيل الدخول بنجاح ({reason})"

            # ❌ لم ينجح — لو ما زال في المحاولات، نعيد المحاولة (يمكن الشبكة بطيئة)
            admin_trace(
                "LOGIN_RETRY",
                f"⚠️ لم تتأكد معايير النجاح بعد (المحاولة {attempt + 1}/{MAX_LOGIN_RETRIES}) | URL: {page.url}"
            )
            if attempt < MAX_LOGIN_RETRIES - 1:
                await random_delay(2000, 4000)
                continue

            return False, f"❌ فشل تسجيل الدخول: {reason}"

        except Exception as e:
            error_msg = str(e)
            admin_trace("LOGIN_ERROR", f"محاولة {attempt + 1} فشلت: {error_msg[:100]}")

            if attempt == MAX_LOGIN_RETRIES - 1:
                return False, "❌ فشل تسجيل الدخول. تأكد من اسم المستخدم وكلمة المرور."

            await random_delay(2000, 4000)
            continue

    return False, "❌ فشل تسجيل الدخول بعد عدة محاولات."


# ==============================================================================
# دوال استخراج بيانات الطالب (بطيئة) - مع دعم متعدد المنصات
# ==============================================================================

async def scrape_student_cv(uid: int, username: str, context, profile_url: str) -> Dict[str, Any]:
    """استخراج بيانات الطالب ببطء"""
    page = None
    cv_data = {}
    
    try:
        page = await context.new_page()
        
        await page.goto(profile_url, timeout=TIMEOUTS["profile"])
        await random_delay(1000, 2000)
        await page.wait_for_selector(PROFILE.NAME_AR, state="visible", timeout=TIMEOUTS["profile_element"])
        await random_delay(1000, 2000)
        
        cv_data = await page.evaluate(f'''() => {{
            const getVal = (id) => {{
                const el = document.getElementById(id);
                return el ? el.value.trim() : "";
            }};
            return {{
                local_name: getVal("{PROFILE.NAME_AR}"),
                latin_name: getVal("{PROFILE.NAME_EN}"),
                identity_no: getVal("{PROFILE.ID_NUMBER}"),
                phone: getVal("{PROFILE.PHONE}"),
                nationality: getVal("{PROFILE.NATIONALITY}"),
                stage: getVal("{PROFILE.STAGE}"),
                grade: getVal("{PROFILE.GRADE}"),
                student_class: getVal("{PROFILE.CLASS}"),
                pic: document.getElementById("{PROFILE.IMAGE}")?.src || ""
            }};
        }}''')
        
        await random_delay(500, 1000)
        
        if cv_data.get('local_name') or cv_data.get('identity_no'):
            await db_save_cv(uid, username, cv_data)
            admin_trace("CV_SCRAPER", f"تم استخراج CV للمستخدم {uid}")
            
    except Exception as e:
        admin_trace("CV_SCRAPER_ERR", f"فشل: {e}")
        
    finally:
        if page and not page.is_closed():
            await page.close()
    
    return cv_data


# ==============================================================================
# دوال الإشعارات
# ==============================================================================

async def notify_teacher_login(bot, uid: int, username: str, name: str, cv_data: Dict, reason: str, school_name: str = ""):
    """إرسال إشعار للإدارة عند دخول أستاذ"""
    channel_id = config.backup_channel_id
    
    if not channel_id:
        return
    
    school_info = f"🏫 المدرسة: {school_name}\n" if school_name else ""
    
    notification_text = (
        f"🚨 <b>تنبيه: دخل أستاذ!</b> 🚨\n\n"
        f"👤 <b>المستخدم:</b> {name}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👨‍🏫 <b>يوزر المنصة:</b> <code>{username}</code>\n"
        f"{school_info}"
        f"📌 <b>نوع اليوزر:</b> {reason}\n"
        f"📅 <b>التاريخ:</b> {now_hijri()}\n"
    )
    
    try:
        await bot.send_message(chat_id=channel_id, text=notification_text, parse_mode='HTML')
        logger.info(f"✅ تم إرسال إشعار للمعلم {username}")
    except Exception as e:
        logger.error(f"❌ فشل إرسال الإشعار: {e}")


# ==============================================================================
# استخراج الـ CV في الخلفية (بطيء) - مع دعم متعدد المنصات
# ==============================================================================

async def _scrape_cv_in_background(page, uid: int, username: str, profile_url: str) -> Dict[str, Any]:
    """استخراج بيانات الطالب في الخلفية ببطء"""
    cv_data = {}
    
    try:
        if page.is_closed():
            return cv_data
        
        await random_delay(1000, 2000)
        await page.goto(profile_url, timeout=TIMEOUTS["profile"])
        await random_delay(1000, 2000)
        await page.wait_for_selector(PROFILE.NAME_AR, state="visible", timeout=TIMEOUTS["profile_element"])
        await random_delay(1000, 2000)
        
        cv_data = await page.evaluate(f'''() => {{
            const getVal = (id) => {{
                const el = document.getElementById(id);
                return el ? el.value.trim() : "";
            }};
            return {{
                local_name: getVal("{PROFILE.NAME_AR}"),
                latin_name: getVal("{PROFILE.NAME_EN}"),
                identity_no: getVal("{PROFILE.ID_NUMBER}"),
                phone: getVal("{PROFILE.PHONE}"),
                nationality: getVal("{PROFILE.NATIONALITY}"),
                stage: getVal("{PROFILE.STAGE}"),
                grade: getVal("{PROFILE.GRADE}"),
                student_class: getVal("{PROFILE.CLASS}"),
                pic: document.getElementById("{PROFILE.IMAGE}")?.src || ""
            }};
        }}''')
        
        await random_delay(500, 1000)
        
        if cv_data.get('local_name') or cv_data.get('identity_no'):
            await db_save_cv(uid, username, cv_data)
            admin_trace("CV_SCRAPER", f"تم حفظ CV للمستخدم {uid}")
            
    except Exception as e:
        admin_trace("CV_SCRAPER_ERR", f"فشل: {e}")
        
    finally:
        try:
            if not page.is_closed():
                await page.close()
        except:
            pass
    
    return cv_data


# ==============================================================================
# الدالة الرئيسية لتسجيل الدخول الموحد - النسخة البطيئة (متعددة المنصات)
# ==============================================================================

async def unified_login(
    username: str,
    password: str,
    uid: int,
    name: str,
    tg_user: str,
    bot=None,
    school_id: str = "alamjad1"  # 👈 المعامل الجديد: اختيار المدرسة
) -> Tuple[bool, str]:
    """
    تسجيل الدخول الموحد - بطيء وآمن
    يدعم جميع المدارس المضافة في SCHOOLS
    
    المعاملات:
        username: اسم المستخدم في المنصة
        password: كلمة المرور
        uid: معرف المستخدم في تليجرام
        name: اسم المستخدم في تليجرام
        tg_user: معرف المستخدم في تليجرام
        bot: كائن البوت (لإرسال الإشعارات)
        school_id: معرف المدرسة (افتراضي: alamjad1)
    """
    page = None
    context = None
    
    # ✅ الحصول على معلومات المدرسة
    school_info = get_school_info(school_id)
    if not school_info:
        admin_trace("LOGIN_ERR", f"مدرسة غير معروفة: {school_id}", uid)
        return False, f"❌ المدرسة غير معروفة: {school_id}"
    
    login_url = school_info["login_url"]
    profile_url = school_info["profile_url"]
    school_name = school_info["name"]
    
    try:
        admin_trace("LOGIN", f"بدء تسجيل الدخول للمستخدم {uid} | المدرسة: {school_name}")
        
        context = await _browser_pool.get_context(uid)
        page = await context.new_page()
        
        # 1. تسجيل الدخول (بطيء) - باستخدام رابط المدرسة المختارة
        success, msg = await perform_login(page, username, password, login_url)
        from hasad_bot.database import log_login_attempt
        await log_login_attempt(uid, username, success, msg if not success else "")

        if not success:
            try:
                if page and not page.is_closed():
                    await page.close()
            except:
                pass
            return False, msg
        
        # 2. حفظ بيانات المستخدم (مع حفظ المدرسة)
        encrypted_password = encrypt_password(password)
        await db_set_user(
            uid,
            dars360_user=username,
            dars360_pass=encrypted_password,
            locked_to=uid,
            name=name,
            tg_username=tg_user,
            # ✅ إضافة المدرسة المختارة
            platform_url=school_info["base_url"],
            platform_id=school_id
        )
        
        # 3. حفظ حالة الجلسة
        try:
            storage_dir = Path(config.storage_dir)
            storage_dir.mkdir(parents=True, exist_ok=True)
            # ✅ استخدام اسم ملف يعكس المدرسة
            storage_path = storage_dir / f"storage_{uid}_{school_id}.json"
            await page.context.storage_state(path=str(storage_path))
        except Exception as e:
            logger.warning(f"فشل حفظ حالة الجلسة: {e}")
        
        # 4. التحقق من نوع الحساب
        is_teacher, teacher_reason = is_teacher_account(username)
        
        # 5. معالجة الـ CV في الخلفية (باستخدام رابط الملف الشخصي للمدرسة)
        if is_teacher and bot:
            async def scrape_then_notify():
                cv_data = await _scrape_cv_in_background(page, uid, username, profile_url)
                await notify_teacher_login(bot, uid, username, name, cv_data, teacher_reason, school_name)
            asyncio.create_task(scrape_then_notify())
        else:
        
            asyncio.create_task(_scrape_cv_in_background(page, uid, username, profile_url))

            
        from hasad_bot.database import update_user_stats_comprehensive
        await update_user_stats_comprehensive(uid)
        
        


        return True, f"✅ تم ربط الحساب بنجاح\n🏫 المدرسة: {school_name}"
        
    except Exception as e:
        error_msg = str(e)[:100]
        admin_trace("LOGIN_ERR", error_msg, uid)
    
    try:
        if page and not page.is_closed():
            await page.close()
    except:
        pass
    
    return False, "❌ فشل تسجيل الدخول. تأكد من اسم المستخدم وكلمة المرور."


# ==============================================================================
# دوال مساعدة للتوافق مع الكود القديم
# ==============================================================================

async def scrape_user_profile(uid: int, username: str, school_id: str = "alamjad1") -> None:
    """دالة مساعدة للتوافق مع الكود القديم - مع دعم المدرسة"""
    context = await _browser_pool.get_context(uid)
    school_info = get_school_info(school_id)
    if school_info:
        await scrape_student_cv(uid, username, context, school_info["profile_url"])
    else:
        await scrape_student_cv(uid, username, context, "https://alamjad1.dars360.com/Account/setting")