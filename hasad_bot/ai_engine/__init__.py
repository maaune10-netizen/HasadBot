from hasad_bot.ai_engine.state import stats, active_sessions
from hasad_bot.ai_engine.ui import get_engine_keyboard, UIManager


def __getattr__(name):
    """Lazy imports to avoid circular dependency (playwright_engine ↔ ai_engine)"""
    if name == "solve_exam_logic_async":
        from hasad_bot.ai_engine.exam_solver import solve_exam_logic_async
        return solve_exam_logic_async
    if name == "solve_homework_logic_async":
        from hasad_bot.ai_engine.homework_solver import solve_homework_logic_async
        return solve_homework_logic_async
    if name == "send_detailed_report":
        from hasad_bot.ai_engine.reports import send_detailed_report
        return send_detailed_report
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
