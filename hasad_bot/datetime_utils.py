"""
Centralized datetime utilities to avoid import conflicts
هذا الملف يحل مشكلة datetime في كل المشروع
"""
from datetime import datetime, timedelta, date, time
import pytz

# Timezone - Riyadh
RIYADH_TZ = pytz.timezone('Asia/Riyadh')


def now():
    """
    Get current datetime (naive, no timezone).
    ⚠️ للاستخدام السريع فقط. للعمليات الحساسة للـ timezone استخدم now_riyadh().
    """
    return datetime.now()


def now_riyadh():
    """Get current Riyadh time (timezone-aware)"""
    return datetime.now(RIYADH_TZ)


def now_aware():
    """Alias for now_riyadh() - timezone-aware current time"""
    return now_riyadh()


def now_naive():
    """
    Explicitly get naive current datetime.
    Same as now() but makes intent clear.
    """
    return datetime.now()


def now_timestamp():
    """Get current Unix timestamp"""
    return int(datetime.now().timestamp())


def format_datetime(dt=None, fmt='%Y-%m-%d %H:%M:%S'):
    """Format datetime to string"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def parse_datetime(date_string, fmt='%Y-%m-%d %H:%M:%S'):
    """Parse datetime from string"""
    return datetime.strptime(date_string, fmt)


def get_today():
    """Get today's date"""
    return datetime.now().date()


def get_now_time():
    """Get current time"""
    return datetime.now().time()


def add_days(dt=None, days=0):
    """Add days to datetime"""
    if dt is None:
        dt = datetime.now()
    return dt + timedelta(days=days)


def add_hours(dt=None, hours=0):
    """Add hours to datetime"""
    if dt is None:
        dt = datetime.now()
    return dt + timedelta(hours=hours)


def add_minutes(dt=None, minutes=0):
    """Add minutes to datetime"""
    if dt is None:
        dt = datetime.now()
    return dt + timedelta(minutes=minutes)


def timestamp_to_datetime(timestamp, tz=None):
    """
    Convert Unix timestamp to datetime.

    Args:
        timestamp: Unix timestamp (seconds since epoch)
        tz: Timezone to attach. Default = Riyadh (RIYADH_TZ).
            Pass None for naive datetime in local system timezone.

    Returns:
        datetime (aware if tz given, naive otherwise)
    """
    if tz is None:
        tz = RIYADH_TZ
    return datetime.fromtimestamp(timestamp, tz=tz)


def datetime_to_timestamp(dt):
    """Convert datetime to Unix timestamp (handles both naive and aware)"""
    if dt.tzinfo is None:
        # naive datetime: assume local timezone
        return int(dt.timestamp())
    # aware datetime: convert to local for consistency
    return int(dt.timestamp())


def to_riyadh(dt):
    """
    Convert any datetime (naive or aware) to Riyadh timezone.

    - If naive: assume it's already in Riyadh local time
    - If aware: convert to Riyadh
    """
    if dt.tzinfo is None:
        return RIYADH_TZ.localize(dt)
    return dt.astimezone(RIYADH_TZ)


def is_naive(dt):
    """Check if datetime is naive (no timezone)"""
    return dt.tzinfo is None


def riyadh_time(hour: int, minute: int = 0):
    """
    وقت-aware بمنطقة الرياض (Asia/Riyadh) — للجدولة اليومية.
    PTB يفسّر الـ time النايف على أنه UTC افتراضياً → انحراف 3 ساعات؛
    الوقت الـ aware يُستخدم كما هو فيحترم توقيت الرياض.
    """
    return time(hour, minute, tzinfo=RIYADH_TZ)


# Re-export original classes for backward compatibility
__all__ = [
    'now',
    'now_riyadh',
    'now_aware',
    'now_naive',
    'now_timestamp',
    'format_datetime',
    'parse_datetime',
    'get_today',
    'get_now_time',
    'add_days',
    'add_hours',
    'add_minutes',
    'timestamp_to_datetime',
    'datetime_to_timestamp',
    'to_riyadh',
    'is_naive',
    'riyadh_time',
    'datetime',
    'timedelta',
    'date',
    'time',
    'RIYADH_TZ'
]