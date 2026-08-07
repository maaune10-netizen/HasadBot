# hasad_bot/__init__.py
"""
HASAD Bot - حل واجبات منصة درس 360 تلقائياً
"""

__version__ = "2.5.0"
__author__ = "HASAD Team"

from .config import config
from .database import db_init, db_get_user, db_set_user
from .utils import admin_trace, now_hijri

__all__ = [
    'config',
    'db_init',
    'db_get_user',
    'db_set_user',
    'admin_trace',
    'now_hijri',
]