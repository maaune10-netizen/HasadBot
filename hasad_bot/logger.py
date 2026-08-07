#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Logging module for HASAD Bot - نسخة متكاملة
تجمع بين التسجيل القديم والنظام المتقدم
"""

import asyncio
import json
import time
import sys
import traceback
import inspect
import functools
from pathlib import Path
from hasad_bot.datetime_utils import datetime, now
from typing import Any, Callable, Dict, Optional

from loguru import logger
from colorama import Fore, Style, init

# تهيئة colorama
init(autoreset=True)

# ==============================================================================
# متغيرات عامة
# ==============================================================================

_db_pool = None

# Import config at runtime to avoid circular imports
def get_log_dir():
    try:
        from hasad_bot.config import config
        return config.log_dir
    except:
        return Path("P:/Hasad_Data/logers")

LOG_DIR = get_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ملفات اللوج المختلفة
MAIN_LOG = LOG_DIR / "hasad_main.log"
ERROR_LOG = LOG_DIR / "hasad_errors.log"
DEBUG_LOG = LOG_DIR / "hasad_debug.log"
EVENT_LOG = LOG_DIR / "hasad_events.log"
SECURITY_LOG = LOG_DIR / "hasad_security.log"
PERFORMANCE_LOG = LOG_DIR / "hasad_performance.log"


# ==============================================================================
# تهيئة Loguru المتقدمة
# ==============================================================================

def setup_advanced_logging():
    """تهيئة نظام اللوج المتقدم"""
    
    # إزالة المعالج الافتراضي
    logger.remove()
    
    # تنسيق اللوج الجميل — ألوان واضحة لكل مستوى
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # تنسيق مبسط للترمينال
    terminal_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<level>{message}</level>"
    )
    
    # 1. طباعة في التيرمينال بألوان — INFO فما فوق
    logger.add(
        sys.stderr,
        format=terminal_format,
        level="INFO",
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # 2. الملف الرئيسي - كل شيء (DEBUG فما فوق)
    logger.add(
        MAIN_LOG,
        format=log_format,
        level="DEBUG",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True
    )
    
    # 3. ملف الأخطاء فقط (ERROR فما فوق)
    logger.add(
        ERROR_LOG,
        format=log_format,
        level="ERROR",
        rotation="50 MB",
        retention="60 days",
        compression="zip",
        encoding="utf-8"
    )
    
    # 4. ملف الأحداث
    logger.add(
        EVENT_LOG,
        format="{time:YYYY-MM-DD HH:mm:ss} | {extra[event_type]:<20} | UID:{extra[user_id]:<12} | {message}",
        level="INFO",
        filter=lambda record: "event_type" in record["extra"],
        rotation="100 MB",
        encoding="utf-8"
    )
    
    # 5. ملف الأمان
    logger.add(
        SECURITY_LOG,
        format="{time:YYYY-MM-DD HH:mm:ss} | {extra[user_id]:<10} | {extra[action]:<20} | {message}",
        level="INFO",
        filter=lambda record: record["extra"].get("category") == "security",
        rotation="50 MB",
        encoding="utf-8"
    )
    
    # 6. ملف الأداء
    logger.add(
        PERFORMANCE_LOG,
        format="{time:YYYY-MM-DD HH:mm:ss} | {extra[duration]:<10}ms | {message}",
        level="INFO",
        filter=lambda record: record["extra"].get("category") == "performance",
        rotation="50 MB",
        encoding="utf-8"
    )
    
    logger.success("✅ Advanced logging system initialized")
    return logger


# ==============================================================================
# ديكوراتير لتسجيل الدوال تلقائياً
# ==============================================================================

def log_function_call(func: Callable) -> Callable:
    """
    ديكوراتير يسجل كل استدعاء دالة تلقائياً
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        module_name = func.__module__
        
        # استخراج user_id إذا موجود
        user_id = "SYSTEM"
        for arg in args:
            if hasattr(arg, "effective_user") and arg.effective_user:
                user_id = arg.effective_user.id
                break
            elif hasattr(arg, "from_user") and arg.from_user:
                user_id = arg.from_user.id
                break
            elif hasattr(arg, "user_id"):
                user_id = arg.user_id
                break
        
        try:
            # تسجيل بداية الاستدعاء
            logger.bind(
                event_type="FUNCTION_CALL",
                user_id=user_id,
                category="function"
            ).debug(f"Calling {module_name}.{func_name}")
            
            # تنفيذ الدالة
            result = await func(*args, **kwargs)
            
            # حساب وقت التنفيذ
            duration = (time.time() - start_time) * 1000
            
            # تسجيل النجاح
            logger.bind(
                event_type="FUNCTION_SUCCESS",
                user_id=user_id,
                category="performance",
                duration=duration
            ).info(f"{module_name}.{func_name} completed in {duration:.2f}ms")
            
            return result
            
        except Exception as e:
            error_trace = traceback.format_exc()
            duration = (time.time() - start_time) * 1000
            
            logger.bind(
                event_type="FUNCTION_ERROR",
                user_id=user_id,
                category="error"
            ).error(f"{module_name}.{func_name} failed: {e}\n{error_trace}")
            raise
            
    return async_wrapper


def log_sync_function_call(func: Callable) -> Callable:
    """ديكوراتير للدوال المتزامنة"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = (time.time() - start_time) * 1000
            logger.debug(f"{func.__name__} completed in {duration:.2f}ms")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed: {e}\n{traceback.format_exc()}")
            raise
    return wrapper


# ==============================================================================
# كلاس التسجيل المتقدم
# ==============================================================================

class AdvancedLogger:
    """كلاس متقدم للتسجيل"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._setup_complete = False
    
    def setup(self):
        """تهيئة النظام"""
        if not self._setup_complete:
            setup_advanced_logging()
            self._setup_complete = True
    
    # ==========================================================================
    # دوال التسجيل الأساسية
    # ==========================================================================
    
    def event(self, event_type: str, user_id: Any = "SYSTEM", **kwargs):
        """تسجيل حدث عام"""
        details = kwargs.get('details', {})
        detail_str = ""
        if isinstance(details, dict) and details:
            parts = [f"{k}={v}" for k, v in details.items()]
            detail_str = " | " + ", ".join(parts)
        logger.bind(
            event_type=event_type,
            user_id=user_id,
            **kwargs
        ).info(f"{event_type}{detail_str}")
    
    def security(self, action: str, user_id: Any = "SYSTEM", details: str = ""):
        """تسجيل حدث أمني"""
        logger.bind(
            event_type="SECURITY",
            user_id=user_id,
            category="security",
            action=action
        ).info(f"{action}: {details}")
    
    def performance(self, operation: str, duration: float, user_id: Any = "SYSTEM"):
        """تسجيل أداء"""
        logger.bind(
            category="performance",
            duration=duration,
            user_id=user_id
        ).info(f"{operation}")
    
    def error(self, error_msg: str, user_id: Any = "SYSTEM", **kwargs):
        """تسجيل خطأ"""
        logger.bind(
            event_type="ERROR",
            user_id=user_id,
            category="error",
            **kwargs
        ).error(error_msg)
    
    def user_action(self, user_id: int, action: str, details: str = ""):
        """تسجيل إجراء مستخدم"""
        logger.bind(
            event_type="USER_ACTION",
            user_id=user_id,
            category="user"
        ).info(f"{action}: {details}")
    
    def bot_action(self, action: str, details: str = ""):
        """تسجيل إجراء بوت"""
        logger.bind(
            event_type="BOT_ACTION",
            user_id="BOT",
            category="bot"
        ).info(f"{action}: {details}")
    
    def admin_action(self, admin_id: int, action: str, target_id: int = None, details: str = ""):
        """تسجيل إجراء أدمن"""
        target = f" on {target_id}" if target_id else ""
        logger.bind(
            event_type="ADMIN_ACTION",
            user_id=admin_id,
            category="security"
        ).info(f"{action}{target}: {details}")
        
        # تسجيل في admin_actions في قاعدة البيانات
        if _db_pool:
            asyncio.create_task(self._save_admin_action(admin_id, action, target_id, details))
    
    async def _save_admin_action(self, admin_id: int, action: str, target_id: int, details: str):
        """حفظ إجراء الأدمن في قاعدة البيانات"""
        try:
            from hasad_bot.database import log_admin_action
            await log_admin_action(
                admin_id=admin_id,
                admin_name=str(admin_id),
                action_type=action,
                target_user_id=target_id,
                details=details
            )
        except:
            pass
    
    def api_call(self, api_name: str, duration: float, success: bool, user_id: Any = "SYSTEM"):
        """تسجيل نداء API"""
        status = "SUCCESS" if success else "FAILED"
        logger.bind(
            event_type="API_CALL",
            user_id=user_id,
            category="performance",
            duration=duration
        ).info(f"{api_name}: {status} ({duration:.2f}ms)")
    
    def database_query(self, query_type: str, duration: float, user_id: Any = "SYSTEM"):
        """تسجيل استعلام قاعدة بيانات"""
        logger.bind(
            category="performance",
            duration=duration,
            user_id=user_id
        ).debug(f"DB {query_type}: {duration:.2f}ms")
    
    # ==========================================================================
    # دوال للتوافق مع الكود القديم
    # ==========================================================================
    
    async def log_event(self, user_id: int, event_type: str, event_name: str, **kwargs):
        """توافق مع log_event القديم"""
        await self._log_event_to_db(user_id, event_type, event_name, kwargs)
    
    async def _log_event_to_db(self, user_id: int, event_type: str, event_name: str, kwargs: dict):
        """تسجيل الحدث في قاعدة البيانات"""
        global _db_pool
        if not _db_pool:
            return
            
        try:
            conn = await _db_pool.get_connection()
            await conn.execute("""
                INSERT INTO event_logs (
                    user_id, event_type, event_name, details, 
                    response_time, success, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, 
                event_type, 
                event_name, 
                json.dumps(kwargs.get('details', {}), ensure_ascii=False),
                kwargs.get('response_time', 0),
                1 if kwargs.get('success', True) else 0,
                kwargs.get('error', ''),
                time.time()
            ))
            await conn.commit()
        except Exception as e:
            logger.error(f"Event logging error: {e}")
    
    # ==========================================================================
    # دوال مساعدة
    # ==========================================================================
    
    def get_log_files_info(self) -> Dict[str, Dict]:
        """الحصول على معلومات ملفات اللوج"""
        files_info = {}
        for log_file in [MAIN_LOG, ERROR_LOG, DEBUG_LOG, EVENT_LOG, SECURITY_LOG, PERFORMANCE_LOG]:
            if log_file.exists():
                stat = log_file.stat()
                files_info[log_file.name] = {
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    "path": str(log_file)
                }
        return files_info
    
    async def export_logs(self, log_type: str = "all") -> Optional[Path]:
        """تصدير ملفات اللوج"""
        import shutil
        from datetime import datetime
        
        timestamp = now().strftime("%Y%m%d_%H%M%S")
        export_dir = LOG_DIR / f"export_{timestamp}"
        export_dir.mkdir(exist_ok=True)
        
        if log_type == "all":
            for log_file in LOG_DIR.glob("hasad_*.log*"):
                shutil.copy2(log_file, export_dir / log_file.name)
        else:
            log_file = LOG_DIR / f"hasad_{log_type}.log"
            if log_file.exists():
                shutil.copy2(log_file, export_dir / log_file.name)
        
        # ضغط المجلد
        shutil.make_archive(str(export_dir), 'zip', export_dir)
        zip_path = Path(str(export_dir) + ".zip")
        
        # حذف المجلد غير المضغوط
        shutil.rmtree(export_dir)
        
        return zip_path


# ==============================================================================
# دوال للتوافق مع الكود القديم (API مألوفة)
# ==============================================================================

def setup_colored_logging():
    """إعداد تسجيل ملون"""
    setup_advanced_logging()


def trace_colored(step: str, detail: str, level: str = "INFO", user_id: int = 0):
    """تسجيل ملون للترمينال"""
    timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
    
    color = Fore.WHITE
    if level == "MATCH":
        color = Fore.GREEN
    elif level == "SKIP":
        color = Fore.YELLOW
    elif level == "FATAL":
        color = Fore.RED
    elif level == "NAV":
        color = Fore.MAGENTA
    
    print(f"{Fore.YELLOW}[{timestamp}] {color}[{step}] -> {detail}{Style.RESET_ALL}")
    
    # تسجيل في الملف
    try:
        from hasad_bot.utils import admin_trace
        admin_trace(step, detail, str(user_id))
    except:
        pass


# ==============================================================================
# دوال التسجيل الأساسية (للكود القديم)
# ==============================================================================

async def init_logger(db_pool):
    """تهيئة الـ logger بقاعدة البيانات"""
    global _db_pool
    _db_pool = db_pool
    logger.info("Logger initialized with database tables")


# ==============================================================================
# دوال تسجيل بمستويات واضحة
# ==============================================================================

def log_success(message: str, **kwargs):
    """تسجيل نجاح — 🟢 أخضر"""
    logger.success(f"✅ {message}")

def log_warning(message: str, **kwargs):
    """تسجيل تحذير — 🟡 أصفر"""
    logger.warning(f"⚠️ {message}")

def log_error(message: str, **kwargs):
    """تسجيل خطأ — 🔴 أحمر"""
    logger.error(f"❌ {message}")

def log_info(message: str, **kwargs):
    """تسجيل معلومة — 🔵 أزرق"""
    logger.info(f"ℹ️ {message}")

def log_action(action: str, details: str = "", user_id: int = 0):
    """تسجيل إجراء — واضح ومختصر"""
    logger.info(f"[{action}] {details}" if details else f"[{action}]")


async def log_event(user_id: int, event_type: str, event_name: str, **kwargs):
    """تسجيل حدث - توافق مع الكود القديم"""
    adv_logger = AdvancedLogger()
    await adv_logger._log_event_to_db(user_id, event_type, event_name, kwargs)
    
    # تسجيل في loguru
    adv_logger.event(event_name, user_id=user_id, details=kwargs.get('details', {}))


async def log_button_click(user_id: int, button_name: str, category: str):
    """تسجيل نقرة الزر في قاعدة البيانات (canonical implementation)

    Args:
        user_id: معرّف المستخدم
        button_name: اسم الزر (مثلاً "🤖 حل الواجبات")
        category: التصنيف (main, admin, command, settings, support, ...)

    Note: جدول button_clicks يُنشأ في database._create_tables — لا حاجة CREATE هنا.
    """
    try:
        from hasad_bot.database import _db_pool
        from hasad_bot.utils import now_hijri

        conn = await _db_pool.get_connection()

        await conn.execute(
            "INSERT INTO button_clicks (user_id, button_name, button_category, click_time) "
            "VALUES (?, ?, ?, ?)",
            (user_id, button_name, category, time.time()),
        )
        await conn.commit()

        logger.info(f"[{now_hijri()}] User {user_id} clicked '{button_name}' in '{category}'")

    except Exception as e:
        logger.error(f"Failed to log button click: {e}")

async def log_api_call(user_id: int, api_name: str, response_time: float, success: bool = True, error: str = ""):
    """تسجيل نداء API"""
    await log_event(
        user_id, 
        f'API_{api_name.upper()}', 
        api_name,
        response_time=response_time,
        success=success,
        error=error
    )


async def log_error(user_id: int, error_message: str, source: str = "SYSTEM"):
    """تسجيل خطأ"""
    await log_event(
        user_id,
        'ERROR',
        source,
        success=False,
        error=error_message
    )


async def log_system_metrics(cpu_percent: float, memory_percent: float, active_users: int):
    """تسجيل مقاييس النظام"""
    global _db_pool
    if not _db_pool:
        return
        
    try:
        conn = await _db_pool.get_connection()
        await conn.execute("""
            INSERT INTO system_metrics (
                timestamp, cpu_percent, memory_percent, active_users
            ) VALUES (?, ?, ?, ?)
        """, (time.time(), cpu_percent, memory_percent, active_users))
        await conn.commit()
    except Exception as e:
        logger.error(f"System metrics logging error: {e}")


async def update_user_stats(user_id: int, event_type: str):
    """تحديث إحصائيات المستخدم"""
    global _db_pool
    if not _db_pool:
        return
        
    try:
        conn = await _db_pool.get_connection()
        
        async with conn.execute("SELECT user_id FROM user_stats WHERE user_id = ?", (user_id,)) as c:
            exists = await c.fetchone()
        
        now = time.time()
        
        if exists:
            if event_type == 'LOGIN':
                await conn.execute("""
                    UPDATE user_stats SET total_logins = total_logins + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'HOMEWORK':
                await conn.execute("""
                    UPDATE user_stats SET total_homeworks = total_homeworks + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'QUESTION_SOLVED':
                await conn.execute("""
                    UPDATE user_stats SET total_questions = total_questions + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'ERROR':
                await conn.execute("""
                    UPDATE user_stats SET total_errors = total_errors + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'API_GROQ':
                await conn.execute("""
                    UPDATE user_stats SET groq_calls = groq_calls + 1, total_api_calls = total_api_calls + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'API_GEMINI':
                await conn.execute("""
                    UPDATE user_stats SET gemini_calls = gemini_calls + 1, total_api_calls = total_api_calls + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            elif event_type == 'DB_HIT':
                await conn.execute("""
                    UPDATE user_stats SET db_hits = db_hits + 1, last_active = ? 
                    WHERE user_id = ?
                """, (now, user_id))
            else:
                await conn.execute("""
                    UPDATE user_stats SET last_active = ? WHERE user_id = ?
                """, (now, user_id))
        else:
            await conn.execute("""
                INSERT INTO user_stats (user_id, last_active) VALUES (?, ?)
            """, (user_id, now))
        
        await conn.commit()
    except Exception as e:
        logger.error(f"Update user stats error: {e}")


# ==============================================================================
# إنشاء النسخة العالمية
# ==============================================================================

advanced_logger = AdvancedLogger()


# ==============================================================================
# التهيئة التلقائية
# ==============================================================================

def init_advanced_logging():
    """تهيئة نظام اللوج المتقدم"""
    advanced_logger.setup()
    
    # ✅ تسجيل كل شيء تلقائياً
    import sys
    
    class AutoLogger:
        def __init__(self, level):
            self.level = level
            self.buffer = []
        
        def write(self, msg):
            if msg and msg.strip():
                self.buffer.append(msg)
                if msg.endswith('\n'):
                    full = ''.join(self.buffer).strip()
                    if full:
                        logger.log(self.level, full)
                    self.buffer = []
        
        def flush(self):
            if self.buffer:
                full = ''.join(self.buffer).strip()
                if full:
                    logger.log(self.level, full)
                self.buffer = []
    
    sys.stdout = AutoLogger("INFO")
    sys.stderr = AutoLogger("ERROR")
    
    return advanced_logger