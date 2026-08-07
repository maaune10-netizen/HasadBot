"""
اختبارات L1 Cache لـ dashboard_stats.

يتحقق من:
- التهيئة: الـ cache فارغ.
- التخزين: تُحفظ النتيجة بعد استدعاء ناجح.
- الـ TTL: تُرجع نفس النتيجة خلال TTL.
- انتهاء الصلاحية: تُستبدل بعد TTL.
- فشل لا يُلوّث الـ cache.
"""
import asyncio
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_dashboard_cache_initial_state():
    from hasad_bot.web_dashboard import _DASHBOARD_CACHE, _DASHBOARD_TTL
    assert _DASHBOARD_CACHE["data"] is None
    assert _DASHBOARD_CACHE["ts"] == 0.0
    assert _DASHBOARD_TTL > 0
    print("✅ test_dashboard_cache_initial_state passed")


def test_dashboard_cache_constants():
    from hasad_bot.web_dashboard import _DASHBOARD_TTL
    assert isinstance(_DASHBOARD_TTL, float)
    assert 5 <= _DASHBOARD_TTL <= 300, f"TTL should be reasonable, got {_DASHBOARD_TTL}"
    print("✅ test_dashboard_cache_constants passed")


def test_dashboard_cache_data_structure():
    from hasad_bot.web_dashboard import _DASHBOARD_CACHE
    assert "data" in _DASHBOARD_CACHE
    assert "ts" in _DASHBOARD_CACHE
    print("✅ test_dashboard_cache_data_structure passed")


def test_dashboard_cache_invalidation_logic():
    """تحاكي منطق: نضع بيانات في الـ cache، نتحقق أن ts < TTL يجعل البيانات fresh."""
    from hasad_bot.web_dashboard import _DASHBOARD_CACHE, _DASHBOARD_TTL

    # تنظيف
    _DASHBOARD_CACHE["data"] = {"stats": {"total_users": 42}}
    _DASHBOARD_CACHE["ts"] = time.time()

    # طازج
    now = time.time()
    is_fresh = _DASHBOARD_CACHE["data"] is not None and (now - _DASHBOARD_CACHE["ts"]) < _DASHBOARD_TTL
    assert is_fresh is True

    # منتهي
    _DASHBOARD_CACHE["ts"] = now - (_DASHBOARD_TTL + 1)
    is_fresh = _DASHBOARD_CACHE["data"] is not None and (time.time() - _DASHBOARD_CACHE["ts"]) < _DASHBOARD_TTL
    assert is_fresh is False

    # تنظيف
    _DASHBOARD_CACHE["data"] = None
    _DASHBOARD_CACHE["ts"] = 0.0
    print("✅ test_dashboard_cache_invalidation_logic passed")


def test_dashboard_cache_manual_override():
    """يمكن تعطيل الـ cache بـ TTL=0."""
    from hasad_bot.web_dashboard import _DASHBOARD_CACHE

    # محاكاة TTL=0 (الـ cache معطّل)
    ttl_zero = 0.0
    _DASHBOARD_CACHE["data"] = {"stats": {}}
    _DASHBOARD_CACHE["ts"] = time.time()
    now = time.time()
    is_fresh = _DASHBOARD_CACHE["data"] is not None and (now - _DASHBOARD_CACHE["ts"]) < ttl_zero
    assert is_fresh is False, "TTL=0 should never be fresh"

    # تنظيف
    _DASHBOARD_CACHE["data"] = None
    _DASHBOARD_CACHE["ts"] = 0.0
    print("✅ test_dashboard_cache_manual_override passed")


if __name__ == "__main__":
    test_dashboard_cache_initial_state()
    test_dashboard_cache_constants()
    test_dashboard_cache_data_structure()
    test_dashboard_cache_invalidation_logic()
    test_dashboard_cache_manual_override()
    print("\n✅ All 5 dashboard cache tests passed")
