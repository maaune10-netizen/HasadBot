from hasad_bot.ai_engine.selectors import BUTTON_KEYWORDS


def is_finish_button(button_text: str) -> bool:
    """تحديد إذا كان الزر هو زر إنهاء/تسليم"""
    return any(keyword.lower() in button_text.lower() for keyword in BUTTON_KEYWORDS.FINISH)


def is_next_button(button_text: str) -> bool:
    """تحديد إذا كان الزر هو زر التالي"""
    return any(keyword.lower() in button_text.lower() for keyword in BUTTON_KEYWORDS.NEXT)


def can_click_finish(solved_questions: int, total_questions: int) -> bool:
    """التحقق من إمكانية الضغط على زر الإنهاء"""
    return solved_questions >= total_questions and total_questions > 0
