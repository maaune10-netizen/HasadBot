#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Playwright engine module with browser pooling for HASAD Bot
نسخة احترافية مع تنويع البصمة (User Agent, OS, Browser, Viewport)
"""

import asyncio
import time
import random
import re
from typing import Dict, Optional, List, Any, Tuple
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from hasad_bot.datetime_utils import datetime, now
from dataclasses import dataclass, field

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator
from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import admin_trace
import hashlib
from hasad_bot.database import _db_pool

from hasad_bot.ai_engine.selectors import (
    URLS, LOGIN, HOMEWORK, QUESTIONS, NAVIGATION, SUBMIT, RESULTS,
    ANSWER_KEY, SCROLL, ANTI_DETECT_SCRIPTS, CHROMIUM_ARGS,
    PERMISSIONS_OVERRIDE, PROFILE,
)
from hasad_bot.database import db_get_user

# ==============================================================================
# ENUMS
# ==============================================================================

class HomeworkType(str, Enum):
    SINGLE_PAGE = "single_page"
    MULTI_PAGE = "multi_page"


class QuestionType(str, Enum):
    MCQ = "mcq"
    ESSAY = "essay"
    TRUE_FALSE = "true_false"


# ==============================================================================
# قوائم التنويع (User Agents, Viewports, OS, Browsers)
# ==============================================================================

# ✅ قائمة User Agents متنوعة (جوال + كمبيوتر + متصفحات مختلفة)
USER_AGENTS = [
    # Windows - Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    
    # Windows - Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    
    # Windows - Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    
    # macOS - Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    
    # macOS - Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    
    # Linux - Chrome
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    
    # Linux - Firefox
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    
    # Android - Chrome (جوال)
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    
    # Android - Samsung Internet
    "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
    
    # iOS - Safari (iPhone)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    
    # iOS - Chrome
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
    
    # iPad - Safari
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# ✅ أحجام شاشة متنوعة (جوال + تابلت + كمبيوتر)
VIEWPORTS = [
    # أجهزة كمبيوتر (Desktop)
    {"width": 1920, "height": 1080},  # Full HD
    {"width": 1366, "height": 768},   # Laptop شائع
    {"width": 1536, "height": 864},   # Laptop
    {"width": 1440, "height": 900},   # MacBook
    {"width": 2560, "height": 1440},  # 2K
    {"width": 1280, "height": 720},   # HD
    
    # أجهزة لوحية (Tablet)
    {"width": 1024, "height": 1366},  # iPad Pro 11"
    {"width": 768, "height": 1024},   # iPad Mini
    {"width": 800, "height": 1280},   # Samsung Tablet
    
    # هواتف (Mobile)
    {"width": 375, "height": 812},    # iPhone X/11/12
    {"width": 390, "height": 844},    # iPhone 13/14
    {"width": 393, "height": 852},    # iPhone 15
    {"width": 360, "height": 800},    # Samsung Galaxy
    {"width": 412, "height": 915},    # Pixel 7
    {"width": 414, "height": 896},    # iPhone 11 Pro Max
    {"width": 320, "height": 568},    # iPhone SE
]

# ✅ ألوان وأنظمة تشغيل متنوعة
COLOR_SCHEMES = ["light", "dark"]
LANGUAGES = ["ar-SA", "ar-EG", "ar-AE", "en-US"]


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class ContextMetrics:
    """مقاييس السياق للمراقبة"""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    pages_created: int = 0
    errors: int = 0
    operations: int = 0
    user_agent: str = ""
    viewport: Dict = field(default_factory=dict)
    
    @property
    def age(self) -> float:
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        return time.time() - self.last_used
    
    def record_operation(self):
        self.operations += 1
        self.last_used = time.time()
    
    def record_error(self):
        self.errors += 1


# ==============================================================================
# BROWSER POOL - النسخة الاحترافية مع تنويع البصمة
# ==============================================================================

class BrowserPool:
    """
    مدير متقدم للمتصفحات مع تنويع البصمة
    يدير السياقات لكل مستخدم بشكل مستقل
    """
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
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.contexts: Dict[str, BrowserContext] = {}
        self.metrics: Dict[str, ContextMetrics] = {}
        self.is_ready = False
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """تهيئة المتصفح الرئيسي"""
        async with self._lock:
            if self.is_ready:
                return
            
            logger.info("🚀 Initializing Playwright browser pool...")
            
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=config.playwright_headless,
                    args=CHROMIUM_ARGS,
                    handle_sigterm=False,
                    handle_sigint=False,
                )
                self.is_ready = True
                
                # بدء مهمة تنظيف الخلفية
                self._cleanup_task = asyncio.create_task(self._cleanup_idle_contexts())
                
                logger.success("✅ Browser pool initialized")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize browser: {e}")
                raise
    
    async def get_context(self, user_id: int, storage_state: Optional[str] = None) -> BrowserContext:
        """
        الحصول على سياق للمستخدم مع التحقق من الصلاحية
        إذا كان السياق تالفاً، يتم إنشاء سياق جديد
        """
        context_key = f"user_{user_id}"

        # ✅ قفل على مستوى الـ pool لتفادي سباق الشروط
        # (طلبان متزامنان لنفس المستخدم قد ينشئان سياقين)
        async with self._lock:
            # التحقق من وجود السياق وأنه لا يزال صالحاً
            if context_key in self.contexts:
                context = self.contexts[context_key]

                # اختبار صحة السياق
                is_valid = await self._is_context_valid(context)

                if is_valid:
                    # تحديث المقاييس
                    if context_key in self.metrics:
                        self.metrics[context_key].record_operation()
                    admin_trace("BROWSER_POOL", f"Using existing context for user {user_id}", user_id)
                    return context
                else:
                    # السياق تالف، نحتاج لتنظيفه
                    admin_trace("BROWSER_POOL", f"Context for user {user_id} is invalid, cleaning up", user_id)
                    await self._force_close_context(context_key)

            # إنشاء سياق جديد
            return await self._create_new_context(user_id, storage_state)
    
    async def _is_context_valid(self, context: BrowserContext) -> bool:
        """التحقق من صحة السياق"""
        try:
            # محاولة إنشاء صفحة مؤقتة للاختبار
            test_page = await context.new_page()
            await test_page.close()
            return True
        except Exception as e:
            # أي خطأ يعني أن السياق تالف
            logger.debug(f"Context validation failed: {e}")
            return False
    
    async def _create_new_context(self, user_id: int, storage_state: Optional[str] = None) -> BrowserContext:
        """إنشاء سياق جديد للمستخدم مع بصمة عشوائية فريدة"""
        from hasad_bot.config import config
        
        context_key = f"user_{user_id}"
        
        # التأكد من عدم وجود سياق قديم
        if context_key in self.contexts:
            await self._force_close_context(context_key)
        
        # ✅ اختيار بصمة عشوائية لكل سياق
        selected_user_agent = random.choice(USER_AGENTS)
        selected_viewport = random.choice(VIEWPORTS)
        selected_color_scheme = random.choice(COLOR_SCHEMES)
        selected_language = random.choice(LANGUAGES)
        
        # ✅ استخراج معلومات من الـ User Agent
        is_mobile = "Mobile" in selected_user_agent or "iPhone" in selected_user_agent or "Android" in selected_user_agent
        is_ios = "iPhone" in selected_user_agent or "iPad" in selected_user_agent
        is_android = "Android" in selected_user_agent
        is_windows = "Windows" in selected_user_agent
        is_mac = "Macintosh" in selected_user_agent
        is_linux = "Linux" in selected_user_agent and not "Android" in selected_user_agent
        
        # ✅ تحديد نوع المتصفح
        if "Chrome" in selected_user_agent and "Edg" not in selected_user_agent:
            browser_type = "Chrome"
        elif "Firefox" in selected_user_agent:
            browser_type = "Firefox"
        elif "Safari" in selected_user_agent and "Chrome" not in selected_user_agent:
            browser_type = "Safari"
        elif "Edg" in selected_user_agent:
            browser_type = "Edge"
        elif "SamsungBrowser" in selected_user_agent:
            browser_type = "Samsung Internet"
        else:
            browser_type = "Unknown"
        
        admin_trace("BROWSER_POOL", f"Creating context for user {user_id}: {browser_type} | {'Mobile' if is_mobile else 'Desktop'} | {selected_viewport['width']}x{selected_viewport['height']}", user_id)
        
        # إنشاء مجلد التخزين
        storage_dir = Path(config.storage_dir)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"storage_{user_id}.json"
        
        try:
            # ✅ إنشاء السياق ببصمة عشوائية
            context = await self.browser.new_context(
                viewport=selected_viewport,
                user_agent=selected_user_agent,
                storage_state=str(storage_path) if storage_path.exists() else None,
                locale=selected_language,
                timezone_id="Asia/Riyadh",
                permissions=["geolocation"],
                color_scheme=selected_color_scheme,
                is_mobile=is_mobile,
                has_touch=is_mobile,
                extra_http_headers={
                    "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
            )
            
            # ✅ إضافة سكريبتات إخفاء الأتمتة المتقدمة
            await context.add_init_script("\n".join(ANTI_DETECT_SCRIPTS) + "\n" + PERMISSIONS_OVERRIDE)
            
            self.contexts[context_key] = context
            self.metrics[context_key] = ContextMetrics(
                user_agent=selected_user_agent,
                viewport=selected_viewport
            )
            
            admin_trace("BROWSER_POOL", f"✅ Created context for user {user_id} ({browser_type} | {'Mobile' if is_mobile else 'Desktop'})", user_id)
            return context
            
        except Exception as e:
            admin_trace("BROWSER_POOL_ERR", f"Failed to create context: {e}", user_id)
            raise
    
    async def _force_close_context(self, context_key: str):
        """إغلاق سياق بشكل قسري وإزالته من القواميس"""
        try:
            if context_key in self.contexts:
                context = self.contexts[context_key]
                
                # إغلاق كل الصفحات المفتوحة
                for page in context.pages:
                    try:
                        if not page.is_closed():
                            await page.close()
                    except:
                        pass
                
                # إغلاق السياق
                try:
                    await context.close()
                except:
                    pass
                
                # إزالة من القواميس
                del self.contexts[context_key]
                
            if context_key in self.metrics:
                del self.metrics[context_key]
                
        except Exception as e:
            logger.debug(f"Error force closing context: {e}")
    
    async def close_context(self, user_id: int, force: bool = False):
        """إغلاق سياق المستخدم"""
        context_key = f"user_{user_id}"
        
        if context_key in self.contexts:
            admin_trace("BROWSER_POOL", f"Closing context for user {user_id}", user_id)
            await self._force_close_context(context_key)
            admin_trace("BROWSER_POOL", f"✅ Context closed for user {user_id}", user_id)
            return True
        
        admin_trace("BROWSER_POOL", f"No context found for user {user_id}", user_id)
        return False
    
    async def _cleanup_idle_contexts(self):
        """تنظيف السياقات الخاملة (تعمل في الخلفية)"""
        IDLE_TIMEOUT = 1800  # 30 دقيقة (مُرفع من 10 دقائق — جلسات حل الواجبات الطويلة)
        MAX_AGE = 6 * 3600  # 6 ساعات كحد أقصى لحياة السياق

        while self.is_ready:
            try:
                await asyncio.sleep(60)

                if not self.is_ready:
                    break

                now_ts = time.time()
                to_remove = []

                for key, metrics in self.metrics.items():
                    # ✅ تجاوز الحد الأقصى للعمر (حتى لو الجلسة "نشطة" ظاهرياً)
                    if metrics.age > MAX_AGE:
                        to_remove.append(key)
                        continue

                    if metrics.idle_time > IDLE_TIMEOUT:
                        # ✅ حماية: لا ننظّف سياق مستخدم في جلسة نشطة فعلاً
                        try:
                            user_id = int(key.split("_")[1])
                            from hasad_bot.ai_engine.state import active_sessions
                            session = active_sessions.get(user_id)
                            if session and getattr(session, 'is_running', False):
                                # الجلسة تعمل — حدّث last_used بدل التنظيف
                                metrics.last_used = now_ts
                                continue
                        except Exception:
                            pass
                        to_remove.append(key)

                for key in to_remove:
                    user_id = int(key.split("_")[1])
                    admin_trace("BROWSER_POOL", f"Cleaning idle context for user {user_id}", user_id)
                    await self._force_close_context(key)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
    
    async def close_all_contexts(self):
        """إغلاق جميع السياقات"""
        for key in list(self.contexts.keys()):
            await self._force_close_context(key)
        logger.info("✅ All contexts closed")
    
    async def close(self):
        """إغلاق المتصفح بالكامل"""
        logger.info("🛑 Closing browser pool...")
        
        self.is_ready = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except:
                pass
        
        await self.close_all_contexts()
        
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
        
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
        
        self.is_ready = False
        logger.info("🔒 Browser pool closed")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات عن حالة الـ pool"""
        return {
            "status": "ready" if self.is_ready else "not_ready",
            "total_contexts": len(self.contexts),
            "contexts": {
                uid: {
                    "age": metrics.age,
                    "idle": metrics.idle_time,
                    "pages_created": metrics.pages_created,
                    "operations": metrics.operations,
                    "errors": metrics.errors,
                    "user_agent": metrics.user_agent[:50] + "...",
                    "viewport": metrics.viewport
                }
                for uid, metrics in self.metrics.items()
            },
            "total_contexts_created": len(self.metrics),
            "total_pages_created": sum(m.pages_created for m in self.metrics.values()),
            "uptime": time.time() - self._get_start_time() if hasattr(self, '_start_time') else 0,
            "total_errors": sum(m.errors for m in self.metrics.values())
        }
    
    def _get_start_time(self) -> float:
        if not hasattr(self, '_start_time'):
            self._start_time = time.time()
        return self._start_time


# ==============================================================================
# INSTANCE
# ==============================================================================

_browser_pool = BrowserPool()


@asynccontextmanager
async def get_user_page(user_id: int, storage_state: Optional[str] = None):
    """مدخل سياقي للحصول على صفحة للمستخدم"""
    context = await _browser_pool.get_context(user_id, storage_state)
    page = await context.new_page()
    
    context_key = f"user_{user_id}"
    if context_key in _browser_pool.metrics:
        _browser_pool.metrics[context_key].pages_created += 1
    
    try:
        yield page
    finally:
        try:
            if not page.is_closed():
                await page.close()
        except:
            pass


# ==============================================================================
# دوال مساعدة أساسية (باقي الكود كما هو)
# ==============================================================================

async def random_delay(min_ms: int = 300, max_ms: int = 1500) -> None:
    """تأخير عشوائي"""
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


async def scroll_element_to_center(page: Page, element_locator):
    """سكرول العنصر لوسط الشاشة"""
    try:
        element_handle = await element_locator.element_handle()
        await page.evaluate("""
            (element) => {
                element.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center',
                    inline: 'center'
                });
            }
        """, element_handle)
        await asyncio.sleep(0.3)
    except Exception:
        try:
            await element_locator.scroll_into_view_if_needed()
        except:
            pass


async def scroll_to_bottom(page: Page) -> None:
    """سكرول لأسفل الصفحة"""
    await page.evaluate(SCROLL.TO_BOTTOM)
    await random_delay(1000, 2000)


# ==============================================================================
# تسجيل الدخول
# ==============================================================================

async def login(page: Page, username: str, password: str, user_id: int = None) -> bool:
    """تسجيل الدخول إلى المنصة - يدعم جميع المدارس"""
    try:
        # ✅ جلب رابط المدرسة من قاعدة البيانات
        base_url = URLS.DEFAULT_BASE
        
        if user_id:
            user = await db_get_user(user_id)
            if user:
                platform_url = user.get('platform_url', '')
                if platform_url:
                    base_url = platform_url
        
        login_url = f"{base_url}{URLS.LOGIN_PAGE}"
        
        logger.info(f"[LOGIN] 🔑 جاري تسجيل الدخول إلى {base_url}...")
        
        if page.is_closed():
            logger.error("[LOGIN] ❌ الصفحة مغلقة!")
            return False
        
        await page.goto(login_url, wait_until="load", timeout=60000)
        
        await page.wait_for_selector(LOGIN.USERNAME, state="visible", timeout=30000)
        await page.wait_for_selector(LOGIN.PASSWORD, state="visible", timeout=30000)
        
        await page.fill(LOGIN.USERNAME, username)
        await asyncio.sleep(0.5)
        await page.fill(LOGIN.PASSWORD, password)
        await asyncio.sleep(0.5)
        
        await page.click(LOGIN.SUBMIT)
        
        try:
            await page.wait_for_url(f"{base_url}/**/Home/**", timeout=15000)
            logger.success("[LOGIN] ✅ تم الدخول بنجاح")
            return True
        except:
            error_element = await page.locator(LOGIN.ERROR_VISIBLE).count()
            if error_element > 0:
                error_text = await page.locator(LOGIN.ERROR_MSG).text_content()
                logger.error(f"[LOGIN] ❌ {error_text}")
                return False
            raise
        
    except Exception as e:
        logger.error(f"[LOGIN] ❌ فشل: {e}")
        return False
    
# ==============================================================================
# استخراج الواجبات (محسّن - يحتوي على start_button)
# ==============================================================================

async def extract_homeworks(page, base_url: str = URLS.DEFAULT_BASE, fast_mode: bool = True) -> List[Dict]:
    """استخراج قائمة الواجبات مع زر البدء
    fast_mode=True: يستخدم page.evaluate() لاستخراج كل البيانات دفعة واحدة (~1-2s)
    fast_mode=False: يستخدم DOM queries فردية (للتوافق)
    """
    if not base_url or base_url.strip() == "":
        admin_trace("EXTRACT_WARN", f"base_url is empty, using default: {URLS.DEFAULT_BASE}")
        base_url = URLS.DEFAULT_BASE

    homeworks = []
    total_questions_sum = 0

    try:
        try:
            await page.wait_for_selector(HOMEWORK.CARD, timeout=10000)
        except Exception as card_err:
            # 🔍 Diagnostic: خذ screenshot واحفظ HTML عشان نعرف وش على الصفحة
            try:
                import os
                diag_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "diagnostics")
                os.makedirs(diag_dir, exist_ok=True)
                ts = int(time.time())
                await page.screenshot(path=os.path.join(diag_dir, f"extract_fail_{ts}.png"), full_page=True)
                html = await page.content()
                with open(os.path.join(diag_dir, f"extract_fail_{ts}.html"), "w", encoding="utf-8") as f:
                    f.write(html)
                # List all visible class names for debugging
                classes = await page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    const classes = new Set();
                    all.forEach(el => el.classList.forEach(c => classes.add(c)));
                    return Array.from(classes).sort();
                }""")
                admin_trace("EXTRACT_DIAG", f"URL: {page.url} | Classes: {classes[:50]}")
                admin_trace("EXTRACT_DIAG", f"Card selector '{HOMEWORK.CARD}' not found. Screenshot + HTML saved to diagnostics/")
            except Exception as diag_err:
                admin_trace("EXTRACT_DIAG_ERR", str(diag_err)[:100])
            raise card_err

        if fast_mode:
            # 🚀 وضع سريع: JavaScript واحد يستخرج كل البيانات
            raw_data = await page.evaluate(f"""() => {{
                const cards = document.querySelectorAll('{HOMEWORK.CARD}');
                const results = [];
                cards.forEach(card => {{
                    try {{
                        const spans = card.querySelectorAll('{HOMEWORK.CARD_SUBJECT}');
                        const subject = spans[0] ? spans[0].innerText.trim() : 'غير معروف';
                        const name = spans[1] ? spans[1].innerText.trim() : 'واجب';
                        const orangeSpans = card.querySelectorAll('{HOMEWORK.CARD_QUESTION_COUNT}');
                        let qText = orangeSpans[1] ? orangeSpans[1].innerText.trim() : '0';
                        let qMatch = qText.match(/(\\d+)/);
                        const questions = qMatch ? parseInt(qMatch[1]) : 0;
                        const btn = card.querySelector("{HOMEWORK.CARD_START_BTN}");
                        const onclick = btn ? btn.getAttribute('onclick') || '' : '';
                        const idMatch = onclick.match(/ID=([^&]+)/);
                        const hwId = idMatch ? idMatch[1] : null;
                        results.push({{
                            subject: subject,
                            name: name,
                            questions: questions,
                            id: hwId
                        }});
                    }} catch(e) {{}}
                }});
                return results;
            }}""")

            for item in raw_data:
                if item.get('id'):
                    total_questions_sum += item.get('questions', 0)
                    homeworks.append({
                        'id': item['id'],
                        'name': item.get('name', 'واجب'),
                        'subject': item.get('subject', 'غير معروف'),
                        'questions': item.get('questions', 0),
                        'start_button': None,
                        'element': None,
                        'base_url': base_url
                    })

        else:
            # وضع التوافق: DOM queries فردية
            cards = await page.locator(HOMEWORK.CARD).all()
            extract_errors = []

            for idx, card in enumerate(cards):
                try:
                    subject_element = card.locator(HOMEWORK.CARD_SUBJECT).first
                    subject = await subject_element.text_content() or "غير معروف"
                    subject = subject.strip()

                    hw_name_element = card.locator(HOMEWORK.CARD_SUBJECT).nth(1)
                    homework_name = await hw_name_element.text_content() or "واجب"
                    homework_name = homework_name.strip()

                    questions_element = card.locator(HOMEWORK.CARD_QUESTION_COUNT).nth(1)
                    questions_text = await questions_element.text_content() or "0"
                    questions_match = re.search(r'(\d+)', questions_text)
                    questions_count = int(questions_match.group(1)) if questions_match else 0

                    total_questions_sum += questions_count

                    start_button = card.locator(HOMEWORK.CARD_START_BTN_TEXT).first
                    if await start_button.count() == 0:
                        start_button = card.locator(HOMEWORK.CARD_START_BTN).first
                    if await start_button.count() == 0:
                        continue

                    onclick = await start_button.get_attribute("onclick") or ""
                    id_match = re.search(r'ID=([^&]+)', onclick)
                    homework_id = id_match.group(1) if id_match else None

                    homeworks.append({
                        'id': homework_id,
                        'name': homework_name,
                        'subject': subject,
                        'questions': questions_count,
                        'element': card,
                        'start_button': start_button,
                        'base_url': base_url
                    })

                except Exception as e:
                    err_str = str(e)
                    if len(extract_errors) < 3:
                        admin_trace("EXTRACT_ERR", f"Card {idx}: {err_str[:80]}")
                    extract_errors.append((idx, err_str[:80]))
                    continue

            if extract_errors:
                admin_trace("EXTRACT_ERR_SUMMARY",
                    f"⚠️ {len(extract_errors)} بطاقة فشلت | Card {extract_errors[0][0]}: {extract_errors[0][1]}")

        admin_trace("EXTRACT", f"Found {len(homeworks)} homework cards")
        admin_trace("HW_SUMMARY", f"✅ إجمالي الواجبات: {len(homeworks)} | إجمالي الأسئلة: {total_questions_sum}")

    except Exception as e:
        admin_trace("EXTRACT_ALL_ERR", str(e))

    return homeworks

# ==============================================================================
# استخراج إجمالي عدد الأسئلة
# ==============================================================================

async def get_total_questions_count(page: Page) -> int:
    """استخراج إجمالي عدد الأسئلة"""
    try:
        # الطريقة 1: من عنصر progress
        try:
            await page.wait_for_selector(QUESTIONS.TOTAL_COUNT, timeout=3000)
            total_element = page.locator(QUESTIONS.TOTAL_COUNT).first
            if await total_element.is_visible():
                total_text = await total_element.text_content()
                if total_text and total_text.strip().isdigit():
                    return int(total_text.strip())
        except:
            pass
        
        # الطريقة 2: عد الأسئلة الظاهرة
        questions = await page.locator(QUESTIONS.CONTAINER).all()
        return len(questions)
        
    except Exception as e:
        admin_trace("TOTAL_Q_ERR", str(e))
        try:
            questions = await page.locator(QUESTIONS.CONTAINER).all()
            return len(questions)
        except:
            return 0


# ==============================================================================
# الأسئلة
# ==============================================================================

async def get_all_questions(page: Page) -> List[Locator]:
    """جلب كل الأسئلة الظاهرة"""
    try:
        return await page.locator(QUESTIONS.CONTAINER).all()
    except Exception as e:
        logger.error(f"[QUESTIONS] ❌ فشل: {e}")
        return []


async def extract_question_data(question: Locator) -> Dict[str, Any]:
    """استخراج بيانات السؤال"""
    data = {
        'text': '',
        'options': [],
        'img_src': None,
        'type': QuestionType.MCQ,
        'already_answered': False,
        'element': question
    }
    
    try:
        checked = await question.locator(QUESTIONS.OPTION_CHECKED).count()
        data['already_answered'] = checked > 0
        
        text_elem = question.locator(QUESTIONS.TEXT).first
        if await text_elem.is_visible():
            data['text'] = (await text_elem.text_content() or "").strip()
        
        opt_elements = await question.locator(QUESTIONS.OPTION_TEXT).all()
        for opt in opt_elements:
            if await opt.is_visible():
                opt_text = (await opt.text_content() or "").strip()
                if opt_text:
                    data['options'].append(opt_text)
        
        img_elem = question.locator(QUESTIONS.IMAGE).first
        if await img_elem.is_visible():
            data['img_src'] = await img_elem.get_attribute("src")
        
        if not data['options']:
            textarea = question.locator("textarea").first
            if await textarea.is_visible():
                data['type'] = QuestionType.ESSAY
        
    except Exception as e:
        logger.error(f"[QUESTION] ⚠️ خطأ: {e}")
    
    return data


async def detect_homework_type(page: Page) -> HomeworkType:
    """كشف نوع الواجب"""
    try:
        next_btn = page.locator(NAVIGATION.NEXT_PAGE).first
        if await next_btn.is_visible() and not await next_btn.is_disabled():
            return HomeworkType.MULTI_PAGE
        return HomeworkType.SINGLE_PAGE
    except Exception:
        return HomeworkType.SINGLE_PAGE


# ==============================================================================
# الإجابات
# ==============================================================================

async def click_answer(question: Locator, answer_index: int) -> bool:
    """النقر على إجابة"""
    try:
        if answer_index < 1:
            return False
        
        options = await question.locator(QUESTIONS.OPTION).all()
        
        if answer_index <= len(options):
            option = options[answer_index - 1]
            await scroll_element_to_center(question.page, option)
            await random_delay(500, 1200)
            await option.click(force=True)
            return True
            
    except Exception as e:
        logger.error(f"[CLICK] ❌ فشل: {e}")
    
    return False


# ==============================================================================
# التنقل
# ==============================================================================


async def extract_exams(page) -> List[Dict]:
    """استخراج قائمة الاختبارات"""
    exams = []
    cards = await page.locator(HOMEWORK.CARD).all()
    for card in cards:
        subject = await card.locator(HOMEWORK.CARD_SUBJECT).first.inner_text()
        start_button = card.locator(HOMEWORK.CARD_START_BTN_TEXT).first
        exams.append({'subject': subject, 'start_button': start_button})
    return exams



async def go_to_next_page(page) -> bool:
    """الانتقال للصفحة التالية"""
    try:
        next_btn = page.locator(NAVIGATION.NEXT_PAGE).first
        
        if not await next_btn.is_visible() or await next_btn.is_disabled():
            return False
        
        await random_delay(1000, 2500)
        await next_btn.click(force=True)
        await page.wait_for_load_state("domcontentloaded")
        await random_delay(1500, 3000)
        
        # التحقق من وجود أسئلة
        questions_count = await page.locator(QUESTIONS.CONTAINER).count()
        if questions_count > 0:
            return True
        
        await random_delay(1000, 2000)
        questions_count = await page.locator(QUESTIONS.CONTAINER).count()
        return questions_count > 0
        
    except Exception as e:
        logger.error(f"[NAV] ❌ فشل: {e}")
        return False


# ==============================================================================
# تسليم الواجب
# ==============================================================================

async def submit_homework(page) -> bool:
    """تسليم الواجب"""
    try:
        submit_btn = page.locator(SUBMIT.FINISH).first
        
        if await submit_btn.is_visible():
            await submit_btn.click()
            
            try:
                await page.wait_for_selector(SUBMIT.CONFIRM_YES, timeout=5000)
                await random_delay(1000, 2000)
                
                confirm_yes = page.locator(SUBMIT.CONFIRM_YES).first
                if await confirm_yes.is_visible():
                    await confirm_yes.click()
                    await random_delay(2000, 3000)
                    return True
            except:
                return False
        else:
            return False
            
    except Exception as e:
        admin_trace("SUBMIT_ERR", str(e))
        return False


# ==============================================================================
# النتائج
# ==============================================================================

async def extract_results(page) -> Dict[str, int]:
    """استخراج النتائج"""
    results = {'total': 0, 'correct': 0, 'wrong': 0, 'grade': 0}
    
    try:
        await page.wait_for_selector(f"{RESULTS.WIDGET}, {RESULTS.WIDGET_ALT}", timeout=10000)
        await random_delay(1000, 2000)
        
        # عدد الأسئلة
        total_el = page.locator(RESULTS.QUESTION_COUNT).first
        if await total_el.count() > 0:
            text = await total_el.text_content()
            if text and text.strip().isdigit():
                results['total'] = int(text.strip())
        
        # الإجابات الصحيحة
        correct_el = page.locator(RESULTS.CORRECT_COUNT).first
        if await correct_el.count() > 0:
            text = await correct_el.text_content()
            if text and text.strip().isdigit():
                results['correct'] = int(text.strip())
        
        # الإجابات الخاطئة
        wrong_el = page.locator(RESULTS.WRONG_COUNT).first
        if await wrong_el.count() > 0:
            text = await wrong_el.text_content()
            if text and text.strip().isdigit():
                results['wrong'] = int(text.strip())
        
        # الدرجات
        grade_el = page.locator(RESULTS.GRADE_COUNT).first
        if await grade_el.count() > 0:
            text = await grade_el.text_content()
            if text and text.strip().isdigit():
                results['grade'] = int(text.strip())
        
    except Exception as e:
        admin_trace("EXTRACT_RESULTS_ERR", str(e))
    
    return results


# ==============================================================================
# استخراج نموذج الإجابة (للتعلم)
# ==============================================================================

from hasad_bot.utils import generate_knowledge_uuid, clean_question_text, get_full_image_url

async def scrape_answer_key(page, subject_name: str = "", session = None) -> List[Dict[str, str]]:
    """استخراج نموذج الإجابة وحفظه في قاعدة المعرفة (يدعم MCQ و Essay)"""
    from hasad_bot.utils import generate_stable_uuid
    
    answers = []
    saved_count = 0
    
    try:
        await scroll_to_bottom(page)
        await random_delay(1000, 2000)
        
        data = await page.evaluate(f'''() => {{
            let ext = [];
            
            // ============================================================
            // 1. MCQ (اختيار من متعدد)
            // ============================================================
            document.querySelectorAll('{ANSWER_KEY.QUESTION_CONTAINER}').forEach(b => {{
                let qEl = b.querySelector('{ANSWER_KEY.QUESTION_TEXT}'); if(!qEl) return;
                let img = qEl.querySelector('img'), ans = "غير محدد", green = false;
                let gSec = b.querySelectorAll('{ANSWER_KEY.CORRECT_SECTION}');
                if(gSec.length){{
                    for(let el of gSec){{ 
                        let chk = el.querySelector('{ANSWER_KEY.CORRECT_INPUT}'), sp = el.querySelector('{ANSWER_KEY.ANSWER_TEXT}'); 
                        if(chk && sp){{ ans = sp.innerText.trim(); green = true; break; }} 
                    }}
                    if(!green) gSec.forEach(el => {{ 
                        let sp = el.querySelector('{ANSWER_KEY.ANSWER_TEXT}'), inp = el.querySelector('{ANSWER_KEY.CORRECT_INPUT_ALT}'); 
                        if(sp && sp.innerText.trim()){{ ans = sp.innerText.trim(); green = true; }} 
                        else if(inp && inp.value){{ ans = inp.value.trim(); green = true; }} 
                    }});
                }}
                if(!green && b.querySelector('{ANSWER_KEY.CORRECT_ICON}')){{ 
                    let chk = b.querySelector('{ANSWER_KEY.CORRECT_INPUT}'); 
                    if(chk && chk.parentElement.querySelector('span')) ans = chk.parentElement.querySelector('span').innerText.trim(); 
                }}
                ext.push({{
                    img_src: img ? img.getAttribute('src') : "", 
                    text: qEl.innerText.trim() || "[صورة]", 
                    ans: ans, 
                    log_type: green ? "FROM_GREEN_MODEL" : "FROM_GRAY_STUDENT"
                }});
            }});
            
            // ============================================================
            // 2. Essay (مقالي) - يفرق بين الرمادي والأخضر مثل MCQ
            // ============================================================
            let essayInputs = document.querySelectorAll('{ANSWER_KEY.ESSAY_READONLY_INPUTS}');
            for (let input of essayInputs) {{
                let answer = input.value.trim();
                if(answer && answer.length > 2){{
                    let questionDiv = input.closest('{ANSWER_KEY.QUESTION_CONTAINER}, {ANSWER_KEY.QUESTION_CONTAINER_ALT}');
                    let questionText = "";
                    if(questionDiv){{
                        let qText = questionDiv.querySelector('{ANSWER_KEY.QUESTION_TEXT}');
                        if(qText){{
                            questionText = qText.innerText.trim();
                        }}
                    }}
                    
                    let isGreen = false;
                    if(input.classList.contains('text-success')){{
                        isGreen = true;
                    }}
                    else if(input.closest('{ANSWER_KEY.ESSAY_CORRECT_SECTION}')){{
                        isGreen = true;
                    }}
                    else if(input.parentElement && input.parentElement.classList.contains('text-success')){{
                        isGreen = true;
                    }}
                    
                    ext.push({{
                        img_src: "",
                        text: questionText || "سؤال مقالي",
                        ans: answer,
                        log_type: isGreen ? "FROM_GREEN_MODEL" : "FROM_GRAY_STUDENT"
                    }});
                }}
            }}
            
            return ext;
        }}''')
        
        conn = _db_pool.get_knowledge_connection()
        cursor = conn.cursor()
        
        for item in data:
            if item['ans'] == "غير محدد" or len(item['ans']) < 1:
                continue
            
            clean_text = clean_question_text(item['text'])
            img_uuid = generate_knowledge_uuid(clean_text, item['img_src'])
            full_img_url = get_full_image_url(item['img_src'])
            
            # إذا كان UUID موجود في session.solved_uuids نتخطى
            if img_uuid in session.solved_uuids:
                continue
            
            cursor.execute(
                "INSERT OR REPLACE INTO knowledge (subject_name, img_uuid, full_img_url, question_text, answer, status) VALUES (?, ?, ?, ?, ?, ?)",
                (subject_name, img_uuid, full_img_url, clean_text, item['ans'], item['log_type'])
            )
            
            if cursor.rowcount > 0:
                saved_count += 1
                answers.append(item)
                admin_trace("SAVED", f"[{subject_name}] {clean_text[:40]}... → {item['ans'][:30]}")
        
        conn.commit()
        
        if saved_count > 0:
            admin_trace("SCRAPE", f"✅ Saved {saved_count} answers for {subject_name}")
        else:
            admin_trace("SCRAPE", f"⚠️ No answers saved for {subject_name}")
        
    except Exception as e:
        logger.error(f"[SCRAPE] ❌ فشل: {e}")
        admin_trace("SCRAPE_ERR", str(e), subject_name)
    
    return answers        
# ==============================================================================
# دوال للتوافق مع الكود القديم
# ==============================================================================

async def get_homeworks_list(user_id: int, platform_user: str, platform_pass: str):
    """للتوافق مع الكود القديم"""
    try:
        from hasad_bot.database import db_get_user
        
        user = await db_get_user(user_id)
        base_url = user.get('platform_url', URLS.DEFAULT_BASE) if user else URLS.DEFAULT_BASE
        
        context = await _browser_pool.get_context(user_id)
        page = await context.new_page()
        
        await page.goto(f"{base_url}{URLS.HOMEWORK_LIST}", timeout=15000)
        await page.wait_for_load_state("networkidle")
        
        homeworks = await extract_homeworks(page)
        await page.close()
        return homeworks
        
    except Exception as e:
        admin_trace("GET_HOMEWORKS_ERR", str(e), user_id)
        return []

async def get_homework_count(user_id: int, platform_user: str, platform_pass: str):
    """للتوافق مع الكود القديم"""
    try:
        from hasad_bot.database import db_get_user
        
        user = await db_get_user(user_id)
        base_url = user.get('platform_url', URLS.DEFAULT_BASE) if user else URLS.DEFAULT_BASE
        
        context = await _browser_pool.get_context(user_id)
        page = await context.new_page()
        
        await page.goto(f"{base_url}{URLS.HOMEWORK_LIST}", timeout=15000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector(HOMEWORK.CARD, timeout=10000)
        
        hw_cards = await page.locator(HOMEWORK.CARD).all()
        count = len(hw_cards)
        await page.close()
        return count
        
    except Exception as e:
        admin_trace("GET_HW_COUNT_ERR", str(e), user_id)
        return 0