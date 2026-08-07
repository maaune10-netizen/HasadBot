"""
اختبارات hasad_bot.datetime_utils
تغطية: now/now_aware/now_naive/now_riyadh, timestamp conversions, to_riyadh, is_naive
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hasad_bot.datetime_utils import (
    now, now_riyadh, now_aware, now_naive, now_timestamp,
    format_datetime, parse_datetime, get_today, get_now_time,
    add_days, add_hours, add_minutes,
    timestamp_to_datetime, datetime_to_timestamp,
    to_riyadh, is_naive, RIYADH_TZ,
)


class TestNowFunctions:
    """اختبارات دوال الوقت الحالي"""

    def test_now_returns_naive(self):
        """now() يجب أن يكون naive (لا tzinfo)"""
        result = now()
        assert isinstance(result, datetime)
        assert is_naive(result), "now() should return naive datetime"

    def test_now_riyadh_returns_aware(self):
        """now_riyadh() يجب أن يكون aware مع Asia/Riyadh"""
        result = now_riyadh()
        assert isinstance(result, datetime)
        assert not is_naive(result)
        assert result.tzinfo.zone == "Asia/Riyadh"

    def test_now_aware_is_alias_for_now_riyadh(self):
        """now_aware() يجب أن يكون alias لـ now_riyadh()"""
        a = now_aware()
        r = now_riyadh()
        assert a.tzinfo is not None
        assert r.tzinfo is not None
        assert a.tzinfo.zone == r.tzinfo.zone == "Asia/Riyadh"

    def test_now_naive_explicit(self):
        """now_naive() صراحةً يعطي naive"""
        result = now_naive()
        assert is_naive(result)

    def test_now_timestamp_returns_int(self):
        """now_timestamp() يعيد Unix timestamp صحيح"""
        ts = now_timestamp()
        assert isinstance(ts, int)
        # 2025-01-01 timestamp = 1735689600
        assert ts > 1735689600, "Timestamp should be after 2025"


class TestFormatAndParse:
    """اختبارات format_datetime و parse_datetime"""

    def test_format_datetime_default(self):
        """التنسيق الافتراضي YYYY-MM-DD HH:MM:SS"""
        dt = datetime(2026, 6, 1, 12, 30, 45)
        assert format_datetime(dt) == "2026-06-01 12:30:45"

    def test_format_datetime_custom(self):
        """تنسيق مخصص"""
        dt = datetime(2026, 6, 1, 12, 30, 45)
        assert format_datetime(dt, "%d/%m/%Y") == "01/06/2026"

    def test_format_datetime_none_uses_now(self):
        """إذا كان None يستخدم now()"""
        result = format_datetime(None)
        # التحقق من أن النتيجة قابلة للفهم
        assert len(result) == 19  # YYYY-MM-DD HH:MM:SS

    def test_parse_datetime_round_trip(self):
        """round-trip: format ثم parse يعطي نفس النتيجة"""
        original = datetime(2026, 6, 1, 12, 30, 45)
        formatted = format_datetime(original)
        parsed = parse_datetime(formatted)
        assert parsed == original


class TestGetDateAndTime:
    """اختبارات get_today و get_now_time"""

    def test_get_today_returns_date(self):
        """get_today يعيد date object"""
        from datetime import date
        result = get_today()
        assert isinstance(result, date)

    def test_get_now_time_returns_time(self):
        """get_now_time يعيد time object"""
        from datetime import time
        result = get_now_time()
        assert isinstance(result, time)


class TestAddFunctions:
    """اختبارات add_days / add_hours / add_minutes"""

    def test_add_days(self):
        base = datetime(2026, 6, 1, 12, 0, 0)
        result = add_days(base, days=5)
        assert result == datetime(2026, 6, 6, 12, 0, 0)

    def test_add_hours(self):
        base = datetime(2026, 6, 1, 12, 0, 0)
        result = add_hours(base, hours=3)
        assert result == datetime(2026, 6, 1, 15, 0, 0)

    def test_add_minutes(self):
        base = datetime(2026, 6, 1, 12, 0, 0)
        result = add_minutes(base, minutes=30)
        assert result == datetime(2026, 6, 1, 12, 30, 0)

    def test_add_negative_values(self):
        """إضافة قيم سالبة تعمل بشكل صحيح (طرح)"""
        base = datetime(2026, 6, 1, 12, 0, 0)
        assert add_days(base, days=-1) == datetime(2026, 5, 31, 12, 0, 0)
        assert add_hours(base, hours=-2) == datetime(2026, 6, 1, 10, 0, 0)
        assert add_minutes(base, minutes=-30) == datetime(2026, 6, 1, 11, 30, 0)


class TestTimestampConversion:
    """اختبارات تحويلات timestamp"""

    def test_timestamp_to_datetime_aware_default(self):
        """timestamp_to_datetime افتراضياً يعيد aware مع Riyadh tz"""
        ts = 1700000000  # 2023-11-14 22:13:20 UTC
        result = timestamp_to_datetime(ts)
        assert not is_naive(result)
        assert result.tzinfo.zone == "Asia/Riyadh"

    def test_timestamp_to_datetime_with_explicit_tz(self):
        """timestamp_to_datetime مع tz معيّن"""
        ts = 1700000000
        tokyo = pytz.timezone("Asia/Tokyo")
        result = timestamp_to_datetime(ts, tz=tokyo)
        assert result.tzinfo.zone == "Asia/Tokyo"

    def test_datetime_to_timestamp_naive(self):
        """datetime_to_timestamp من naive datetime"""
        dt = datetime(2026, 6, 1, 12, 0, 0)  # naive
        ts = datetime_to_timestamp(dt)
        assert isinstance(ts, int)

    def test_datetime_to_timestamp_aware(self):
        """datetime_to_timestamp من aware datetime"""
        dt = pytz.timezone("UTC").localize(datetime(2026, 6, 1, 12, 0, 0))
        ts = datetime_to_timestamp(dt)
        assert isinstance(ts, int)
        # تأكد أن النتيجة تطابق dt.timestamp() (المتوقع من Python)
        assert ts == int(dt.timestamp())
        # يجب أن يكون بعد 2025-01-01
        assert ts > 1735689600

    def test_round_trip_timestamp(self):
        """round-trip: timestamp -> datetime -> timestamp"""
        original_ts = now_timestamp()
        dt = timestamp_to_datetime(original_ts)
        recovered_ts = datetime_to_timestamp(dt)
        # قد يكون هناك فرق <= 1 ثانية بسبب microseconds
        assert abs(original_ts - recovered_ts) <= 1


class TestToRiyadh:
    """اختبارات to_riyadh"""

    def test_to_riyadh_from_naive(self):
        """تحويل naive إلى Riyadh aware (يفترض أن الـ datetime بالفعل في Riyadh)"""
        naive = datetime(2026, 6, 1, 12, 0, 0)
        result = to_riyadh(naive)
        assert not is_naive(result)
        assert result.tzinfo.zone == "Asia/Riyadh"
        assert result.hour == 12  # يبقى كما هو (محلي)

    def test_to_riyadh_from_aware_other_tz(self):
        """تحويل aware من timezone آخر إلى Riyadh"""
        tokyo = pytz.timezone("Asia/Tokyo")
        tokyo_dt = tokyo.localize(datetime(2026, 6, 1, 12, 0, 0))
        result = to_riyadh(tokyo_dt)
        assert not is_naive(result)
        assert result.tzinfo.zone == "Asia/Riyadh"
        # Tokyo is UTC+9, Riyadh is UTC+3, so noon Tokyo = 6am Riyadh
        assert result.hour == 6

    def test_to_riyadh_from_utc(self):
        """تحويل من UTC إلى Riyadh"""
        utc = pytz.timezone("UTC")
        utc_dt = utc.localize(datetime(2026, 6, 1, 12, 0, 0))
        result = to_riyadh(utc_dt)
        assert result.tzinfo.zone == "Asia/Riyadh"
        # UTC+3 = Riyadh
        assert result.hour == 15  # 12:00 UTC + 3h = 15:00 Riyadh


class TestIsNaive:
    """اختبارات is_naive"""

    def test_is_naive_naive(self):
        assert is_naive(datetime(2026, 1, 1)) is True

    def test_is_naive_aware(self):
        aware = pytz.timezone("UTC").localize(datetime(2026, 1, 1))
        assert is_naive(aware) is False


class TestRegression:
    """اختبارات regression — الأخطاء التي أصلحناها سابقاً"""

    def test_now_with_replace_method(self):
        """
        Bug #1 (radar_engine): كان `now = now()` يكسر الـ scope.
        نتأكد من أن `now().replace()` يعمل بدون UnboundLocalError.
        """
        n = now()
        # إذا كان الـ assignment في function local scope يكسر،
        # الـ replace يعمل بشكل طبيعي
        target = n.replace(hour=20, minute=0, second=0, microsecond=0)
        assert target.hour == 20
        assert target.minute == 0
        assert target.second == 0
        assert target.microsecond == 0
