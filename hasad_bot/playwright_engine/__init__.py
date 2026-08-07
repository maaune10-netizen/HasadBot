"""
Modularized Playwright engine for HASAD Bot
Re-exports everything from the original playwright_engine module
"""
import os
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "_playwright_engine_original",
    os.path.join(os.path.dirname(__file__), "..", "playwright_engine.py")
)
_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)

__all__ = []
for _name in dir(_original):
    globals()[_name] = getattr(_original, _name)
    __all__.append(_name)
