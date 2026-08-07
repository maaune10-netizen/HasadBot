#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HASAD Bot - Resilience Module
وحدة المرونة: Circuit Breaker + Retry Logic
============================================

توفر هذه الوحدة أدوات لحماية البوت من فشل الخدمات الخارجية:
- Circuit Breaker: يمنع الطلبات لخدمة فاشلة
- Retry with Exponential Backoff: إعادة المحاولة بذكاء
- Async support: دعم كامل للعمليات غير المتزامنة
- Metrics: تتبع حالات الفشل والنجاح

الاستخدام:
    from hasad_bot.resilience import retry_on_failure, circuit_breaker
    
    @retry_on_failure(max_attempts=3)
    async def call_groq_api():
        ...
    
    @circuit_breaker(name="groq", failure_threshold=5)
    async def risky_call():
        ...
"""

import asyncio
import functools
import inspect
import time
import threading
from enum import Enum
from typing import Callable, Optional, Type, Tuple, Any
from dataclasses import dataclass, field

try:
    from tenacity import (
        retry as tenacity_retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
        RetryError,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

from loguru import logger


# ==============================================================================
# Circuit Breaker
# ==============================================================================

class CircuitState(Enum):
    """حالات Circuit Breaker"""
    CLOSED = "closed"          # يعمل بشكل طبيعي
    OPEN = "open"              # محظور (يفشل بسرعة)
    HALF_OPEN = "half_open"    # اختبار التعافي


@dataclass
class CircuitBreakerConfig:
    """إعدادات Circuit Breaker"""
    failure_threshold: int = 5          # عدد الفشللات لفتح الدائرة
    success_threshold: int = 2          # عدد النجاحات لإغلاق الدائرة من HALF_OPEN
    timeout_seconds: float = 60.0       # مدة الانتظار قبل HALF_OPEN
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)


class CircuitBreakerError(Exception):
    """يُرفع عندما تكون الدائرة مفتوحة"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker Pattern

    الحالات:
    - CLOSED: العمل طبيعي، يُسجَّل الفشل
    - OPEN: يُرفض كل طلب فوراً (CircuitBreakerError)
    - HALF_OPEN: يُسمح بعدد محدود من الطلبات لاختبار التعافي
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            # التحقق من timeout لإعادة التعافي التلقائي
            if self._state == CircuitState.OPEN and self._last_failure_time:
                if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitState):
        """تغيير الحالة مع تسجيل"""
        old_state = self._state
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
        logger.info(
            f"🔌 Circuit '{self.name}': {old_state.value} → {new_state.value}"
        )

    def _record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            # NOTE: في حالة CLOSED، لا نُعدّل الـ failure_count عند النجاح.
            # الـ failure_count يتراكم، والدائرة تُفتح عند threshold.
            # الـ reset يحدث فقط في reset() أو عند الانتقال إلى CLOSED من HALF_OPEN.

    def _record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def call(self, func: Callable, *args, **kwargs):
        """استدعاء دالة مع حماية Circuit Breaker"""
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit '{self.name}' is OPEN. Try again later."
            )
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.config.expected_exceptions:
            self._record_failure()
            raise

    async def acall(self, func: Callable, *args, **kwargs):
        """استدعاء دالة async مع حماية Circuit Breaker"""
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit '{self.name}' is OPEN. Try again later."
            )
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except self.config.expected_exceptions:
            self._record_failure()
            raise

    def reset(self):
        """إعادة تعيين Circuit Breaker يدوياً"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)

    def get_stats(self) -> dict:
        """إحصائيات Circuit Breaker"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
            }


# ==============================================================================
# Circuit Breaker Registry (singleton)
# ==============================================================================

class CircuitBreakerRegistry:
    """سجل مركزي لـ Circuit Breakers"""
    _breakers: dict = {}
    _lock = threading.RLock()

    @classmethod
    def get(cls, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name, config)
            return cls._breakers[name]

    @classmethod
    def get_all_stats(cls) -> dict:
        with cls._lock:
            return {name: cb.get_stats() for name, cb in cls._breakers.items()}

    @classmethod
    def reset_all(cls):
        with cls._lock:
            for cb in cls._breakers.values():
                cb.reset()


# ==============================================================================
# Retry Decorator (uses tenacity internally)
# ==============================================================================

def _log_retry_attempt(retry_state):
    """Log retry attempt"""
    exception = retry_state.outcome.exception()
    logger.warning(
        f"🔄 Retry attempt {retry_state.attempt_number} after exception: "
        f"{type(exception).__name__}: {exception}"
    )


def retry_on_failure(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    exponential_multiplier: float = 2.0,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator: إعادة المحاولة عند الفشل مع exponential backoff

    Args:
        max_attempts: عدد المحاولات الكلي (يشمل المحاولة الأولى)
        initial_wait: الانتظار الأول بالثواني
        max_wait: الحد الأقصى للانتظار
        exponential_multiplier: معامل الـ exponential
        retry_on: tuple من الـ exceptions التي تستدعي retry

    Usage:
        @retry_on_failure(max_attempts=3, initial_wait=1)
        async def call_external_api():
            ...
    """
    if not TENACITY_AVAILABLE:
        logger.warning("tenacity not installed; retry decorator is a no-op")
        def decorator(func):
            return func
        return decorator

    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)

        retry_decorator = tenacity_retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(
                multiplier=initial_wait,
                max=max_wait,
                exp_base=exponential_multiplier,
            ),
            retry=retry_if_exception_type(retry_on),
            before_sleep=_log_retry_attempt,
            reraise=True,
        )

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await retry_decorator(func)(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return retry_decorator(func)(*args, **kwargs)
            return sync_wrapper

    return decorator


# ==============================================================================
# Circuit Breaker Decorator
# ==============================================================================

def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout_seconds: float = 60.0,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator: حماية دالة بـ Circuit Breaker

    Args:
        name: معرّف الـ Circuit (للتسجيل المركزي)
        failure_threshold: عدد الفشللات لفتح الدائرة
        success_threshold: عدد النجاحات لإغلاقها من HALF_OPEN
        timeout_seconds: مدة الانتظار قبل HALF_OPEN
        expected_exceptions: الاستثناءات التي تُحسب كفشل

    Usage:
        @circuit_breaker(name="groq", failure_threshold=5)
        async def call_groq():
            ...
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout_seconds=timeout_seconds,
        expected_exceptions=expected_exceptions,
    )
    breaker = CircuitBreakerRegistry.get(name, config)

    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await breaker.acall(func, *args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return breaker.call(func, *args, **kwargs)
            return sync_wrapper

    return decorator


# ==============================================================================
# Combined: Retry + Circuit Breaker
# ==============================================================================

def resilient_call(
    name: str,
    max_attempts: int = 3,
    failure_threshold: int = 5,
    timeout_seconds: float = 60.0,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator مركّب: Circuit Breaker + Retry

    الترتيب: الـ retry يعمل داخل الـ circuit breaker.
    - إذا الـ circuit مفتوح: يفشل فوراً
    - إذا الـ circuit مغلق: يحاول بالـ retry

    Usage:
        @resilient_call(name="groq", max_attempts=3, failure_threshold=5)
        async def call_groq_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)

        # تطبيق circuit breaker أولاً
        breaker = CircuitBreakerRegistry.get(
            name,
            CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                timeout_seconds=timeout_seconds,
                expected_exceptions=expected_exceptions,
            ),
        )

        # ثم تطبيق retry
        if TENACITY_AVAILABLE:
            retry_decorator = tenacity_retry(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(
                    multiplier=initial_wait,
                    max=max_wait,
                ),
                retry=retry_if_exception_type(expected_exceptions),
                before_sleep=_log_retry_attempt,
                reraise=True,
            )
        else:
            retry_decorator = lambda f: f  # no-op

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # circuit breaker outside, retry inside
                async def inner():
                    return await retry_decorator(func)(*args, **kwargs)
                return await breaker.acall(inner)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                def inner():
                    return retry_decorator(func)(*args, **kwargs)
                return breaker.call(inner)
            return sync_wrapper

    return decorator


# ==============================================================================
# Pre-configured for common HASAD Bot services
# ==============================================================================

# Groq API: sensitive to rate limits
groq_retry = functools.partial(
    retry_on_failure,
    max_attempts=3,
    initial_wait=2.0,
    max_wait=15.0,
    retry_on=(Exception,),
)

# Gemini API: similar
gemini_retry = functools.partial(
    retry_on_failure,
    max_attempts=3,
    initial_wait=2.0,
    max_wait=15.0,
    retry_on=(Exception,),
)

# Database: short retry (locks are temporary)
db_retry = functools.partial(
    retry_on_failure,
    max_attempts=3,
    initial_wait=0.5,
    max_wait=2.0,
    retry_on=(Exception,),
)

# Network requests
network_retry = functools.partial(
    retry_on_failure,
    max_attempts=3,
    initial_wait=1.0,
    max_wait=5.0,
    retry_on=(ConnectionError, TimeoutError, OSError),
)


__all__ = [
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitBreakerError",
    "retry_on_failure",
    "circuit_breaker",
    "resilient_call",
    "groq_retry",
    "gemini_retry",
    "db_retry",
    "network_retry",
]
