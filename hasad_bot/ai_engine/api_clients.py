import httpx
from typing import Optional
from loguru import logger
from hasad_bot.config import config
from hasad_bot.resilience import (
    resilient_call,
    CircuitBreakerError,
)
from hasad_bot.ai_engine.connection_pool import http_pool

try:
    from google import genai
    import PIL.Image
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


@resilient_call(
    name="groq_api",
    max_attempts=3,
    failure_threshold=5,
    timeout_seconds=30.0,
    initial_wait=1.0,
    max_wait=10.0,
    expected_exceptions=(httpx.HTTPError, ConnectionError, TimeoutError),
)
async def _call_groq_api(
    api_key: str,
    model: str,
    prompt: str,
    timeout: float = 15.0,
) -> Optional[str]:
    """
    استدعاء Groq API مع حماية resilience + HTTP Pool.
    يعيد الـ content من الـ response، أو None عند الفشل.
    """
    try:
        client = http_pool.get_groq_client()
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=timeout,
        )
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        elif response.status_code == 429:
            logger.warning(f"Groq rate limited (429), will retry")
            raise httpx.HTTPError(f"Rate limited: {response.status_code}")
        else:
            logger.warning(
                f"Groq API returned {response.status_code}: {response.text[:200]}"
            )
            return None
    except CircuitBreakerError:
        logger.error("Groq circuit breaker is OPEN - all calls blocked")
        return None
    except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
        logger.warning(f"Groq call failed (will retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Groq unexpected error: {e}")
        return None


@resilient_call(
    name="gemini_api",
    max_attempts=3,
    failure_threshold=5,
    timeout_seconds=30.0,
    initial_wait=1.0,
    max_wait=10.0,
    expected_exceptions=(httpx.HTTPError, ConnectionError, TimeoutError),
)
async def _call_gemini_api(
    api_key: str,
    prompt: str,
    timeout: float = 15.0,
) -> Optional[str]:
    """
    استدعاء Gemini API مع حماية resilience + HTTP Pool.
    يعيد الـ content من الـ response، أو None عند الفشل.
    """
    try:
        client = http_pool.get_gemini_client()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={api_key}"
        )
        response = await client.post(
            url,
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            },
            timeout=timeout,
        )
        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return content
            return None
        elif response.status_code == 429:
            logger.warning("Gemini rate limited (429), will retry")
            raise httpx.HTTPError(f"Rate limited: {response.status_code}")
        else:
            logger.warning(
                f"Gemini API returned {response.status_code}: {response.text[:200]}"
            )
            return None
    except CircuitBreakerError:
        logger.error("Gemini circuit breaker is OPEN - all calls blocked")
        return None
    except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
        logger.warning(f"Gemini call failed (will retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Gemini unexpected error: {e}")
        return None
