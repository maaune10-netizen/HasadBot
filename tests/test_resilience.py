"""
اختبارات hasad_bot.resilience
تغطية: CircuitBreaker, retry decorators, registry, resilient_call
"""
import sys
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hasad_bot.resilience import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitBreakerError,
    retry_on_failure,
    circuit_breaker,
    resilient_call,
    groq_retry,
    gemini_retry,
    db_retry,
    network_retry,
)


# =============================================================================
# CircuitBreaker
# =============================================================================
class TestCircuitBreaker:
    """اختبارات CircuitBreaker الأساسي"""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        def good_func():
            return "ok"

        for _ in range(5):
            result = cb.call(good_func)
            assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=3, expected_exceptions=(ValueError,)),
        )

        def bad_func():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(bad_func)
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_raises_immediately(self):
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, expected_exceptions=(ValueError,)),
        )

        def bad_func():
            raise ValueError("fail")

        # افتح الدائرة
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(bad_func)

        # الآن أي استدعاء يجب أن يفشل فوراً
        call_count = 0
        def counting_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        with pytest.raises(CircuitBreakerError):
            cb.call(counting_func)
        assert call_count == 0, "Function should not be called when circuit is open"

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=0.1,  # 100ms
                expected_exceptions=(ValueError,),
            ),
        )

        def bad_func():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(bad_func)
        assert cb.state == CircuitState.OPEN

        # انتظر timeout
        time.sleep(0.15)
        # التحقق من الحالة: يجب أن تكون HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_close_after_success_in_half_open(self):
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=0.1,
                expected_exceptions=(ValueError,),
            ),
        )

        def bad_func():
            raise ValueError("fail")

        def good_func():
            return "ok"

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(bad_func)
        time.sleep(0.15)

        # 2 نجاحات في HALF_OPEN يجب أن تغلق الدائرة
        for _ in range(2):
            assert cb.call(good_func) == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, expected_exceptions=(ValueError,)),
        )

        def bad_func():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(bad_func)
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_get_stats(self):
        cb = CircuitBreaker("my_cb", CircuitBreakerConfig(failure_threshold=3))
        stats = cb.get_stats()
        assert stats["name"] == "my_cb"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0


class TestCircuitBreakerAsync:
    """اختبارات CircuitBreaker مع async"""

    @pytest.mark.asyncio
    async def test_async_call_success(self):
        cb = CircuitBreaker("test_async")

        async def good():
            return "ok"

        result = await cb.acall(good)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_call_opens_circuit(self):
        cb = CircuitBreaker(
            "test_async",
            CircuitBreakerConfig(failure_threshold=2, expected_exceptions=(ValueError,)),
        )

        async def bad():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.acall(bad)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_circuit_open_rejects(self):
        cb = CircuitBreaker(
            "test_async",
            CircuitBreakerConfig(failure_threshold=1, expected_exceptions=(ValueError,)),
        )

        async def bad():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.acall(bad)
        # الآن الدائرة مفتوحة
        async def good():
            return "ok"

        with pytest.raises(CircuitBreakerError):
            await cb.acall(good)


# =============================================================================
# CircuitBreakerRegistry
# =============================================================================
class TestCircuitBreakerRegistry:
    """اختبارات الـ Registry (singleton pattern)"""

    def test_get_returns_same_instance(self):
        CircuitBreakerRegistry.reset_all()
        cb1 = CircuitBreakerRegistry.get("shared")
        cb2 = CircuitBreakerRegistry.get("shared")
        assert cb1 is cb2, "Registry should return same instance for same name"

    def test_get_different_names_different_instances(self):
        CircuitBreakerRegistry.reset_all()
        cb1 = CircuitBreakerRegistry.get("a")
        cb2 = CircuitBreakerRegistry.get("b")
        assert cb1 is not cb2

    def test_get_all_stats(self):
        CircuitBreakerRegistry.reset_all()
        CircuitBreakerRegistry.get("service_a")
        CircuitBreakerRegistry.get("service_b")
        stats = CircuitBreakerRegistry.get_all_stats()
        assert "service_a" in stats
        assert "service_b" in stats

    def test_reset_all(self):
        CircuitBreakerRegistry.reset_all()
        cb = CircuitBreakerRegistry.get("reset_test")
        cb._failure_count = 10
        CircuitBreakerRegistry.reset_all()
        assert cb._failure_count == 0


# =============================================================================
# retry_on_failure decorator
# =============================================================================
class TestRetryDecorator:
    """اختبارات retry decorator"""

    def test_sync_retry_eventually_succeeds(self):
        """محاولات متتالية تفشل ثم تنجح"""
        attempt_count = 0

        @retry_on_failure(max_attempts=3, initial_wait=0.01, max_wait=0.1)
        def flaky():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("temporary")
            return "success"

        result = flaky()
        assert result == "success"
        assert attempt_count == 3

    def test_sync_retry_exhausts_attempts(self):
        attempt_count = 0

        @retry_on_failure(
            max_attempts=2,
            initial_wait=0.01,
            max_wait=0.1,
            retry_on=(ValueError,),
        )
        def always_fails():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("nope")

        with pytest.raises(ValueError):
            always_fails()
        assert attempt_count == 2

    def test_sync_retry_does_not_retry_on_unexpected_exception(self):
        """إذا الـ exception ليس في retry_on، لا يُعاد المحاولة"""
        attempt_count = 0

        @retry_on_failure(
            max_attempts=3,
            initial_wait=0.01,
            max_wait=0.1,
            retry_on=(ValueError,),
        )
        def wrong_error():
            nonlocal attempt_count
            attempt_count += 1
            raise TypeError("different")

        with pytest.raises(TypeError):
            wrong_error()
        assert attempt_count == 1, "Should not retry on unexpected exception"

    @pytest.mark.asyncio
    async def test_async_retry_succeeds(self):
        attempt_count = 0

        @retry_on_failure(max_attempts=3, initial_wait=0.01, max_wait=0.1)
        async def flaky():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ConnectionError("temp")
            return "ok"

        result = await flaky()
        assert result == "ok"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_exhausts(self):
        attempt_count = 0

        @retry_on_failure(
            max_attempts=2,
            initial_wait=0.01,
            max_wait=0.1,
            retry_on=(TimeoutError,),
        )
        async def always_fails():
            nonlocal attempt_count
            attempt_count += 1
            raise TimeoutError("nope")

        with pytest.raises(TimeoutError):
            await always_fails()
        assert attempt_count == 2


# =============================================================================
# circuit_breaker decorator
# =============================================================================
class TestCircuitBreakerDecorator:
    """اختبارات circuit_breaker decorator"""

    def test_circuit_breaker_decorator_basic(self):
        CircuitBreakerRegistry.reset_all()

        @circuit_breaker(name="dec_test", failure_threshold=2)
        def fails():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                fails()
        # الآن الدائرة مفتوحة
        with pytest.raises(CircuitBreakerError):
            fails()

    @pytest.mark.asyncio
    async def test_circuit_breaker_async_decorator(self):
        CircuitBreakerRegistry.reset_all()

        @circuit_breaker(name="async_dec", failure_threshold=1)
        async def async_fails():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await async_fails()
        with pytest.raises(CircuitBreakerError):
            await async_fails()


# =============================================================================
# resilient_call decorator
# =============================================================================
class TestResilientCall:
    """اختبارات resilient_call (retry + circuit breaker)"""

    @pytest.mark.asyncio
    async def test_resilient_recovers(self):
        """يجب أن يتعافى بعد عدة محاولات"""
        CircuitBreakerRegistry.reset_all()
        attempt_count = 0

        @resilient_call(
            name="resilient_test",
            max_attempts=3,
            failure_threshold=5,
            initial_wait=0.01,
            max_wait=0.1,
        )
        async def sometimes_fails():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ConnectionError("temp")
            return "recovered"

        result = await sometimes_fails()
        assert result == "recovered"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_resilient_opens_circuit_on_repeated_failure(self):
        """عند فشل متكرر، الدائرة تُفتح"""
        CircuitBreakerRegistry.reset_all()

        @resilient_call(
            name="resilient_fail",
            max_attempts=2,
            failure_threshold=2,
            initial_wait=0.01,
            max_wait=0.05,
            expected_exceptions=(ValueError,),
        )
        async def always_fails():
            raise ValueError("fail")

        # 2 محاولات فاشلة = تفتح الدائرة
        for _ in range(2):
            with pytest.raises(ValueError):
                await always_fails()

        # الاستدعاء التالي يجب أن يفشل فوراً (circuit open)
        with pytest.raises(CircuitBreakerError):
            await always_fails()


# =============================================================================
# Pre-configured decorators
# =============================================================================
class TestPreconfigured:
    """اختبارات الـ pre-configured decorators"""

    def test_groq_retry_partial(self):
        """groq_retry يجب أن يكون callable (مُكوَّن مسبقاً)"""
        assert callable(groq_retry)

    def test_gemini_retry_partial(self):
        assert callable(gemini_retry)

    def test_db_retry_partial(self):
        assert callable(db_retry)

    def test_network_retry_partial(self):
        assert callable(network_retry)

    def test_groq_retry_usable_as_decorator(self):
        """groq_retry يمكن استخدامه كـ decorator"""
        @groq_retry()
        def my_call():
            return "groq_response"

        assert my_call() == "groq_response"


# =============================================================================
# Integration: registry + circuit breaker + retry
# =============================================================================
class TestIntegration:
    """اختبارات تكاملية"""

    @pytest.mark.asyncio
    async def test_shared_circuit_breaker_across_functions(self):
        """نفس الـ circuit breaker يخدم عدة دوال بنفس الاسم"""
        CircuitBreakerRegistry.reset_all()
        # ملاحظة: لا تستدعي get() قبل الـ decorators — فالـ decorators تنشئ
        # الـ breaker بالـ config الصحيح. get() الافتراضي يستخدم config افتراضي.
        # remove the breaker so it's created with the right config
        if "shared_service" in CircuitBreakerRegistry._breakers:
            del CircuitBreakerRegistry._breakers["shared_service"]

        @circuit_breaker(name="shared_service", failure_threshold=2)
        async def func_a():
            raise ValueError("a")

        @circuit_breaker(name="shared_service", failure_threshold=2)
        async def func_b():
            raise ValueError("b")

        # كلاهما يشتركان في نفس الـ breaker
        with pytest.raises(ValueError):
            await func_a()
        with pytest.raises(ValueError):
            await func_b()
        # الآن الدائرة مفتوحة لكليهما
        with pytest.raises(CircuitBreakerError):
            await func_a()
        with pytest.raises(CircuitBreakerError):
            await func_b()

    def test_stats_observable(self):
        """يمكن مراقبة الإحصائيات"""
        CircuitBreakerRegistry.reset_all()
        # remove to ensure fresh config from decorator
        if "observed" in CircuitBreakerRegistry._breakers:
            del CircuitBreakerRegistry._breakers["observed"]

        @circuit_breaker(name="observed", failure_threshold=10)
        def sometimes_fails(n: int):
            if n % 2 == 0:
                raise ValueError("even")
            return n

        # بعض النجاحات والفشللات
        for i in range(5):
            try:
                sometimes_fails(i)
            except ValueError:
                pass

        stats = CircuitBreakerRegistry.get_all_stats()
        assert "observed" in stats
        assert stats["observed"]["failure_count"] >= 2  # 0, 2, 4 فشلت
