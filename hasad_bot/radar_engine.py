#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Radar Engine module for HASAD Bot - الميزة الحصرية للمشتركين
يقوم بفحص الواجبات الجديدة يومياً وإرسال إشعارات للطلاب
"""
from hasad_bot import datetime_utils
import asyncio
import time
import random
from hasad_bot.datetime_utils import datetime, now, timedelta
from typing import Optional, Dict, List

from loguru import logger
from playwright.async_api import async_playwright

from hasad_bot.config import config
from hasad_bot.database import db_get_vip_users, db_add_radar_notification, db_was_notified, db_get_user
from hasad_bot.utils import admin_trace, decrypt_password
from hasad_bot.playwright_engine import _browser_pool


class RadarEngine:
    """محرك الرادار الذكي - يفحص الواجبات الجديدة للمشتركين"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.is_running = False
        self.radar_task: Optional[asyncio.Task] = None
    
    async def start(self, bot):
        """بدء تشغيل الرادار"""
        from hasad_bot.config import config as app_config
        if not app_config.radar_enabled:
            logger.warning("⏸ Radar start() ignored (RADAR_ENABLED=false)")
            return

        async with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self.radar_task = asyncio.create_task(self._radar_loop(bot))
            logger.info("🚀 Radar engine started")
    
    async def stop(self):
        """إيقاف الرادار"""
        async with self._lock:
            self.is_running = False
            if self.radar_task:
                self.radar_task.cancel()
                try:
                    await self.radar_task
                except:
                    pass
            logger.info("🛑 Radar engine stopped")
    
    async def _radar_loop(self, bot):
        """الحلقة الرئيسية للرادار - تعمل كل مساء"""
        while self.is_running:
            try:
                # حساب وقت التشغيل التالي (الساعة 8 مساءً)
                current_time = now()
                target_time = current_time.replace(hour=20, minute=0, second=0, microsecond=0)

                if current_time >= target_time:
                    target_time += timedelta(days=1)

                # انتظار حتى موعد التشغيل
                wait_seconds = (target_time - current_time).total_seconds()
                logger.info(f"⏰ Radar will run at {target_time.strftime('%Y-%m-%d %H:%M')}")

                # نوم قابل للإلغاء: نوم في شرائح صغيرة حتى يحين الموعد
                # (حتى يتوقف الرادار فوراً عند إيقاف المحرك)
                slept = 0.0
                while slept < wait_seconds and self.is_running:
                    step = min(60.0, wait_seconds - slept)
                    await asyncio.sleep(step)
                    slept += step

                if not self.is_running:
                    break

                # تشغيل فحص الواجبات
                try:
                    await self._check_all_users(bot)
                except Exception as e:
                    admin_trace("RADAR_CHECK_ALL_ERR", f"{e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                admin_trace("RADAR_ERR", f"Error in radar loop: {e}")
                # انتظار قصير قبل إعادة المحاولة (بدلاً من النوم 24 ساعة)
                slept = 0.0
                while slept < 3600 and self.is_running:
                    await asyncio.sleep(min(60.0, 3600 - slept))
                    slept += 60.0
    
    async def _check_all_users(self, bot):
        """فحص جميع المشتركين للبحث عن واجبات جديدة"""
        logger.info("🔍 Radar: Checking for new homework for VIP users...")
        
        users = await db_get_vip_users()
        admin_trace("RADAR", f"Checking {len(users)} VIP users")
        
        for user in users:
            if not self.is_running:
                break
            
            try:
                await self._check_user_homework(user, bot)
                # تأخير بين المستخدمين لتجنب الضغط على السيرفر
                await asyncio.sleep(random.uniform(5, 10))
            except Exception as e:
                admin_trace("RADAR_USER_ERR", f"Error checking user {user['telegram_id']}: {e}")
    
    async def _check_user_homework(self, user: Dict, bot):
        """فحص واجبات مستخدم معين"""
        uid = user['telegram_id']
        platform_user = user.get('dars360_user')
        platform_pass_enc = user.get('dars360_pass')

        if not platform_user or not platform_pass_enc:
            return

        platform_pass = decrypt_password(platform_pass_enc)
        admin_trace("RADAR", f"Checking homework for UID {uid}", uid)

        # ✅ جلب رابط المدرسة الخاص بالمستخدم (ديناميكي)
        from hasad_bot.playwright_engine import get_user_school_url
        try:
            base_url = await get_user_school_url(uid)
        except Exception:
            base_url = "https://alamjad1.dars360.com"

        try:
            # استخدام متصفح من pool
            context = await _browser_pool.get_context(uid)
            page = await context.new_page()

            # تسجيل الدخول
            await page.goto(f"{base_url}/Common/Account/Login", timeout=30000)
            await page.locator("#UserName").fill(platform_user)
            await page.locator("#Password").fill(platform_pass)
            await page.click("#BtnLogin")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)

            # الذهاب لصفحة الواجبات
            await page.goto(f"{base_url}/Homework/Homework/StudentHomework")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            
            # البحث عن واجبات جديدة
            hw_cards = await page.locator(".waiting.cmd").all()
            new_homeworks = []
            
            for card in hw_cards:
                # استخراج معلومات الواجب
                subject = await card.locator(".text-theme").first.text_content()
                subject = subject.strip() if subject else "Unknown"
                
                # محاولة استخراج معرف فريد للواجب
                homework_id = f"{subject}_{int(time.time())}"
                try:
                    # محاولة استخراج رابط أو معرف أفضل
                    link = await card.get_attribute("href") or ""
                    if link:
                        homework_id = link
                except:
                    pass
                
                # التحقق من عدم إرسال إشعار مسبق لهذا الواجب
                if not await db_was_notified(uid, homework_id):
                    new_homeworks.append({
                        'subject': subject,
                        'id': homework_id,
                        'card': card
                    })
            
            await page.close()
            
            # إرسال إشعارات للواجبات الجديدة
            name = user.get('real_name') or user.get('name') or 'الطالب'
            
            for hw in new_homeworks:
                if not self.is_running:
                    break
                
                # إنشاء أزرار الإجراء
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 حل الواجب الآن", callback_data=f"radar_solve:{uid}")],
                    [InlineKeyboardButton("🔕 تجاهل هذه المرة", callback_data=f"radar_ignore:{hw['id']}")]
                ])
                
                # إرسال الإشعار
                await bot.send_message(
                    uid,
                    f"🚨 **رادار حصاد الذكي** 🚨\n\n"
                    f"أهلاً {name} 👋\n"
                    f"المعلم للتو نزل واجب جديد في **( {hw['subject']} )**\n\n"
                    f"هل تريدني أن أقوم بحله الآن؟",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                
                # تسجيل الإشعار
                await db_add_radar_notification(uid, hw['id'])
                admin_trace("RADAR_ALERT", f"Sent alert for {hw['subject']} to UID {uid}", uid)
                
                # تأخير قصير بين الإشعارات
                await asyncio.sleep(2)
            
            if new_homeworks:
                logger.info(f"📡 Radar: Found {len(new_homeworks)} new homework for UID {uid}")
            
        except Exception as e:
            admin_trace("RADAR_CHECK_ERR", f"Failed to check UID {uid}: {e}", uid)


# إنشاء نسخة عالمية من الرادار
radar_engine = RadarEngine()


async def handle_radar_callback(update, context):
    """معالجة ردود المستخدم على إشعارات الرادار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    uid = query.from_user.id
    
    if data.startswith("radar_solve:"):
        # المستخدم يريد حل الواجب الآن
        await query.edit_message_text(
            "✅ **تم استلام طلبك!**\n"
            "سيبدأ المحرك بحل الواجب خلال لحظات...",
            parse_mode="Markdown"
        )
        
        # تشغيل محرك حل الواجبات
        from hasad_bot.handlers import solve_homework
        
        # إنشاء تحديث وهمي لتمريره إلى solve_homework
        class MockMessage:
            def __init__(self, chat_id):
                self.chat_id = chat_id
                self.text = "🤖 حل الواجبات"
                self.from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, chat_id):
                self.message = MockMessage(chat_id)
                self.effective_user = query.from_user
                self.callback_query = query
        
        mock_update = MockUpdate(uid)
        await solve_homework(mock_update, context)
        
    elif data.startswith("radar_ignore:"):
        # المستخدم يتجاهل هذا الواجب
        homework_id = data.split(":", 1)[1]
        await query.edit_message_text(
            "👍 **تم التجاهل**\n"
            "لن يتم إرسال إشعار لهذا الواجب مرة أخرى.",
            parse_mode="Markdown"
        )