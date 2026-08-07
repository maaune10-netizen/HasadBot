from enum import Enum
from hasad_bot.logger import log_event, update_user_stats
from hasad_bot.ai_engine.state import stats


class AnswerSource(str, Enum):
    DATABASE = "db"
    GROQ = "groq"
    GEMINI = "gemini"
    RANDOM = "random"


async def log_question_solved(user_id: int, subject: str, source, question_text: str = ""):
    """
    source يمكن أن يكون:
    - AnswerSource.DATABASE, GROQ, GEMINI, RANDOM (كائن Enum)
    - أو نص مثل "ensemble", "groq_tiebreaker", "qwen", "gemini_image"
    """

    if isinstance(source, AnswerSource):
        source_str = source.value
    else:
        source_str = str(source)

    await log_event(
        user_id=user_id,
        event_type='QUESTION_SOLVED',
        event_name=source_str.upper(),
        details={
            'subject': subject,
            'source': source_str,
            'question': question_text[:100]
        }
    )

    if source == AnswerSource.DATABASE or source_str == "db":
        await update_user_stats(user_id, 'DB_HIT')
        stats["db_hits"] += 1

    elif source == AnswerSource.GROQ or source_str in ["groq", "ensemble", "groq_tiebreaker"]:
        await update_user_stats(user_id, 'API_GROQ')
        stats["groq"] += 1

    elif source == AnswerSource.GEMINI or source_str in ["gemini", "gemini_image", "tiebreaker_gemini"]:
        await update_user_stats(user_id, 'API_GEMINI')
        stats["gemini"] += 1

    elif source == AnswerSource.RANDOM or source_str == "random":
        await update_user_stats(user_id, 'RANDOM')
        stats["random"] = stats.get("random", 0) + 1

    elif source_str == "qwen":
        stats["qwen"] = stats.get("qwen", 0) + 1

    else:
        await update_user_stats(user_id, 'API_GROQ')
        stats["groq"] += 1


async def log_homework_completed(user_id: int, subject: str, total_q: int, solved_q: int, mistakes: int):
    percentage = (solved_q / total_q * 100) if total_q > 0 else 0

    await log_event(
        user_id=user_id,
        event_type='HOMEWORK',
        event_name='COMPLETED',
        details={
            'subject': subject,
            'total_questions': total_q,
            'solved': solved_q,
            'mistakes': mistakes,
            'percentage': percentage
        }
    )
    stats["total_hw"] += 1


async def log_error_event(user_id: int, error_message: str, source: str = "ENGINE"):
    await log_event(
        user_id=user_id,
        event_type='ERROR',
        event_name=source,
        success=False,
        error=error_message[:200]
    )
    stats["errors"] += 1
