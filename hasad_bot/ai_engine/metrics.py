def increment_correct_answer(source: str = "unknown"):
    """تحديث عداد الإجابات الصحيحة بطريقة ذرية"""
    from hasad_bot.ai_engine.state import stats
    stats["correct_answers"] = stats.get("correct_answers", 0) + 1

    if source in ["groq", "ensemble", "tiebreaker_groq", "qwen"]:
        stats["solved_by_ai"] = stats.get("solved_by_ai", 0) + 1


def increment_wrong_answer():
    """تحديث عداد الإجابات الخاطئة بطريقة ذرية"""
    from hasad_bot.ai_engine.state import stats
    stats["wrong_answers"] = stats.get("wrong_answers", 0) + 1


def increment_total_questions():
    """تحديث عداد إجمالي الأسئلة"""
    from hasad_bot.ai_engine.state import stats
    stats["total_questions"] = stats.get("total_questions", 0) + 1
