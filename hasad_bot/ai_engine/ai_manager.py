import asyncio
import re
import os
from typing import Optional, List, Tuple
import httpx
from loguru import logger
from hasad_bot.config import config
from hasad_bot.utils import admin_trace
from hasad_bot.ai_engine.api_clients import GEMINI_AVAILABLE
from hasad_bot.ai_engine.connection_pool import http_pool

try:
    from google import genai
    import PIL.Image
except ImportError:
    genai = None
    PIL = None


class AIManager:

    @staticmethod
    async def get_qwen_answer(q_text: str, opts: List[str], user_id: int) -> Optional[int]:
        """استخدام Groq Qwen3-32B (آخر 5 مفاتيح)"""
        if not config.groq_keys or not q_text:
            return None

        groq_keys_qwen = config.groq_keys[5:10]

        if not groq_keys_qwen:
            return None

        client = http_pool.get_groq_client()

        for idx, key in enumerate(groq_keys_qwen, 6):
            try:
                admin_trace("QWEN_TRY", f"Trying Qwen key {idx}/10", user_id)

                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": "qwen/qwen3-32b",
                        "messages": [{
                            "role": "user",
                            "content": f"Analyze step by step, provide correct option number. Format: 'Answer: [number]'. Question: {q_text} Options: {opts}"
                        }],
                        "temperature": 0
                    },
                    timeout=20.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data['choices'][0]['message']['content']
                    ans_match = re.search(r'Answer:\s*(\d+)', content) or re.search(r'(\d+)', content)
                    if ans_match:
                        answer = int(ans_match.group(1))
                        if 1 <= answer <= len(opts):
                            admin_trace("QWEN_SUCCESS", f"Qwen key {idx} solved: {answer}", user_id)
                            return answer
                elif response.status_code == 429:
                    admin_trace("QWEN_RATE_LIMIT", f"Qwen key {idx} rate limited", user_id)
                    continue
            except:
                continue
        return None

    @staticmethod
    async def get_gemini_answer_text(q_text: str, opts: List[str], user_id: int) -> Optional[int]:
        """
        استخدام Gemini لحل الأسئلة الاختيارية (MCQ) النصية
        """
        if not GEMINI_AVAILABLE or not config.gemini_keys:
            return None

        for idx, key in enumerate(config.gemini_keys, 1):
            try:
                admin_trace("GEMINI_TEXT_TRY", f"Trying key {idx}/{len(config.gemini_keys)}", user_id)

                client = genai.Client(api_key=key)

                options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(opts)])
                prompt = f"""
أجب على السؤال التالي وأعطني رقم الإجابة الصحيحة فقط (1, 2, 3, ...).

السؤال: {q_text}
الخيارات:
{options_text}

الإجابة رقم:
"""
                response = await client.aio.models.generate_content(
                    model='gemini-3.1-flash-lite',
                    contents=prompt
                )

                ans_match = re.search(r'\d+', response.text)
                if ans_match:
                    answer = int(ans_match.group())
                    if 1 <= answer <= len(opts):
                        admin_trace("GEMINI_TEXT_SUCCESS", f"Key {idx} solved: {answer}", user_id)
                        return answer
                    else:
                        admin_trace("GEMINI_TEXT_INVALID", f"Key {idx} returned invalid answer: {answer}", user_id)

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower():
                    admin_trace("GEMINI_TEXT_RATE", f"Key {idx} rate limited", user_id)
                elif "API_KEY" in error_msg or "invalid" in error_msg.lower():
                    admin_trace("GEMINI_TEXT_INVALID_KEY", f"Key {idx} invalid", user_id)
                else:
                    admin_trace("GEMINI_TEXT_ERR", f"Key {idx} failed: {error_msg[:50]}", user_id)
                continue

        admin_trace("GEMINI_TEXT_ALL_FAIL", f"All {len(config.gemini_keys)} Gemini keys failed for MCQ", user_id)
        return None

    @staticmethod
    async def get_ensemble_answer(q_text: str, opts: List[str], img_src: str, user_id: int) -> Tuple[Optional[int], str]:
        """
        نظام تصويت ثلاثي: Gemini + Groq + Qwen
        يُنفّذ الثلاثة بالتوازي (أسرع 3x)
        إرجاع: (الإجابة, المصدر)
        """
        print("=" * 60)
        print("🎯 [ENSEMBLE] بدء نظام التصويت الذكي (متوازي)")
        print(f"📝 السؤال: {q_text[:100]}...")
        print(f"🔢 عدد الخيارات: {len(opts)}")
        print(f"🖼️ صورة: {'نعم' if img_src else 'لا'}")
        print("=" * 60)

        if img_src:
            print("🖼️ [ENSEMBLE] صورة detected → استخدام Gemini فقط")

            try:
                import aiohttp
                import aiofiles

                screenshots_dir = config.knowledge_dir / "question_screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)

                if 'FileStorage/' in img_src:
                    img_name = img_src.split('FileStorage/')[-1]
                else:
                    img_name = img_src.split('/')[-1] if '/' in img_src else img_src

                safe_name = re.sub(r'[<>:"/\\|?*]', '_', img_name)
                img_path = screenshots_dir / safe_name

                if not img_path.exists():
                    from hasad_bot.ai_engine.selectors import URLS as _URLS
                    if img_src.startswith('/'):
                        full_url = f"{_URLS.DEFAULT_BASE}{img_src}"
                    elif not img_src.startswith('http'):
                        full_url = f"{_URLS.DEFAULT_BASE}/{img_src}"
                    else:
                        full_url = img_src

                    async with aiohttp.ClientSession() as session:
                        async with session.get(full_url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                async with aiofiles.open(img_path, 'wb') as f:
                                    await f.write(data)
                                print(f"📸 [ENSEMBLE] تم تحميل الصورة: {img_path}")
                            else:
                                print(f"❌ [ENSEMBLE] فشل تحميل الصورة: {resp.status}")
                                return None, "none"
                else:
                    print(f"📸 [ENSEMBLE] الصورة موجودة مسبقاً: {img_path}")

            except Exception as e:
                print(f"❌ [ENSEMBLE] فشل حفظ الصورة: {e}")
                return None, "none"

            answer = await AIManager.get_gemini_answer(str(img_path), user_id)
            if answer:
                print(f"✅ [ENSEMBLE] Gemini (image) → {answer}")
                return answer, "gemini_image"
            else:
                print(f"❌ [ENSEMBLE] Gemini فشل في حل الصورة")
                return None, "none"

        # 🚀 تشغيل الثلاثة بالتوازي (أسرع 3x)
        print("🚀 [ENSEMBLE] استدعاء Gemini + Groq + Qwen بالتوازي...")
        
        results = await asyncio.gather(
            AIManager.get_gemini_answer_text(q_text, opts, user_id),
            AIManager.get_groq_answer(q_text, opts, user_id),
            AIManager.get_qwen_answer(q_text, opts, user_id),
            return_exceptions=True
        )
        
        gemini_ans = results[0] if not isinstance(results[0], Exception) else None
        groq_ans = results[1] if not isinstance(results[1], Exception) else None
        qwen_ans = results[2] if not isinstance(results[2], Exception) else None

        answers = {}
        if gemini_ans is not None:
            answers[gemini_ans] = answers.get(gemini_ans, 0) + 1
            print(f"   ✅ Gemini → {gemini_ans}")
        else:
            print("   ❌ Gemini → فشل")

        if groq_ans is not None:
            answers[groq_ans] = answers.get(groq_ans, 0) + 1
            print(f"   ✅ Groq (Llama) → {groq_ans}")
        else:
            print("   ❌ Groq (Llama) → فشل")

        if qwen_ans is not None:
            answers[qwen_ans] = answers.get(qwen_ans, 0) + 1
            print(f"   ✅ Qwen → {qwen_ans}")
        else:
            print("   ❌ Qwen → فشل")

        print("-" * 40)
        print(f"📊 [ENSEMBLE] الأصوات: {answers}")

        if not answers:
            print("❌ [ENSEMBLE] لا توجد إجابات من أي نموذج")
            return None, "none"

        max_votes = max(answers.values())
        winners = [ans for ans, votes in answers.items() if votes == max_votes]

        print(f"🏆 [ENSEMBLE] الإجابات الأكثر تكراراً ({max_votes} صوت): {winners}")

        if len(winners) == 1:
            best_answer = winners[0]
            print(f"✅ [ENSEMBLE] فوز واضح! الإجابة {best_answer} (أصوات: {answers})")
            return best_answer, "ensemble"
        else:
            print("⚠️ [ENSEMBLE] تعادل! استخدام Groq كحل أخير (Tiebreaker)")

            if groq_ans is not None:
                print(f"✅ [ENSEMBLE] Tiebreaker → Groq: {groq_ans}")
                return groq_ans, "tiebreaker_groq"
            elif gemini_ans is not None:
                print(f"✅ [ENSEMBLE] Tiebreaker → Gemini: {gemini_ans}")
                return gemini_ans, "tiebreaker_gemini"
            else:
                print("❌ [ENSEMBLE] جميع النماذج فشلت")
                return None, "none"

    @staticmethod
    async def get_groq_answer(q_text: str, opts: List[str], user_id: int) -> Optional[int]:
        """
        استخدام Groq مع دعم المفاتيح المتعددة (GROQ_KEY_1, GROQ_KEY_2, ...)
        """
        if not config.groq_keys or not q_text:
            admin_trace("GROQ_NO_KEYS", "No Groq keys available", user_id)
            return None

        client = http_pool.get_groq_client()

        for idx, key in enumerate(config.groq_keys, 1):
            try:
                admin_trace("GROQ_TRY", f"Trying key {idx}/{len(config.groq_keys)}", user_id)

                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{
                            "role": "user",
                            "content": f"Analyze step by step, provide correct option number. Format: 'Answer: [number]'. Question: {q_text} Options: {opts}"
                        }],
                        "temperature": 0
                    },
                    timeout=15.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data['choices'][0]['message']['content']
                    ans_match = re.search(r'Answer:\s*(\d+)', content) or re.search(r'(\d+)', content)
                    if ans_match:
                        answer = int(ans_match.group(1))
                        if 1 <= answer <= len(opts):
                            admin_trace("GROQ_SUCCESS", f"Key {idx} solved: {answer}", user_id)
                            return answer
                        else:
                            admin_trace("GROQ_INVALID_ANS", f"Key {idx} returned invalid answer: {answer}", user_id)

                elif response.status_code == 429:
                    admin_trace("GROQ_RATE_LIMIT", f"Key {idx} rate limited, trying next", user_id)
                    continue
                elif response.status_code == 401:
                    admin_trace("GROQ_INVALID_KEY", f"Key {idx} invalid, trying next", user_id)
                    continue
                else:
                    admin_trace("GROQ_HTTP_ERROR", f"Key {idx} returned {response.status_code}", user_id)
                    continue

            except httpx.TimeoutException:
                admin_trace("GROQ_TIMEOUT", f"Key {idx} timeout, trying next", user_id)
                continue
            except Exception as e:
                admin_trace("GROQ_FAIL", f"Key {idx} failed: {str(e)[:50]}", user_id)
                continue

        admin_trace("GROQ_ALL_FAIL", f"All {len(config.groq_keys)} Groq keys failed", user_id)
        return None

    @staticmethod
    async def get_gemini_answer_essay(question_text: str, user_id: int) -> Optional[str]:
        """
        استخدام Gemini لحل الأسئلة المقالية (Essay)
        """
        if not GEMINI_AVAILABLE or not config.gemini_keys:
            return None

        for idx, key in enumerate(config.gemini_keys, 1):
            try:
                admin_trace("GEMINI_ESSAY", f"Trying key {idx}/{len(config.gemini_keys)}", user_id)

                client = genai.Client(api_key=key)
                prompt = f"""
أنت مساعد تعليمي متخصص. أجب على السؤال التالي بإجابة مختصرة ومباشرة (جملة واحدة إلى جملتين كحد أقصى).

السؤال: {question_text}

الإجابة:
"""
                response = await client.aio.models.generate_content(
                    model='gemini-3.1-flash-lite',
                    contents=prompt
                )

                answer = response.text.strip()
                if answer and len(answer) > 5:
                    admin_trace("GEMINI_ESSAY_SUCCESS", f"Answer: {answer[:50]}...", user_id)
                    return answer

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower():
                    admin_trace("GEMINI_ESSAY_RATE", f"Key {idx} rate limited", user_id)
                elif "API_KEY" in error_msg or "invalid" in error_msg.lower():
                    admin_trace("GEMINI_ESSAY_INVALID_KEY", f"Key {idx} invalid", user_id)
                else:
                    admin_trace("GEMINI_ESSAY_ERR", f"Key {idx} failed: {error_msg[:50]}", user_id)
                continue

        admin_trace("GEMINI_ESSAY_ALL_FAIL", f"All {len(config.gemini_keys)} Gemini keys failed for essay", user_id)
        return None

    @staticmethod
    async def get_gemini_answer(img_path: str, user_id: int) -> Optional[int]:
        """
        استخدام Gemini مع دعم المفاتيح المتعددة (GEMINI_KEY_1, GEMINI_KEY_2, ...)
        """
        if not GEMINI_AVAILABLE or PIL is None or not config.gemini_keys or not os.path.exists(img_path):
            return None

        for idx, key in enumerate(config.gemini_keys, 1):
            try:
                admin_trace("GEMINI_TRY", f"Trying key {idx}/{len(config.gemini_keys)}", user_id)

                client = genai.Client(api_key=key)
                content = ["Give me the option digit ONLY (1,2,3,4).", PIL.Image.open(img_path)]
                response = await client.aio.models.generate_content(
                    model='gemini-3.1-flash-lite',
                    contents=content
                )
                ans_match = re.search(r'\d+', response.text)
                if ans_match:
                    answer = int(ans_match.group())
                    if 1 <= answer <= 4:
                        admin_trace("GEMINI_SUCCESS", f"Key {idx} solved: {answer}", user_id)
                        return answer

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower():
                    admin_trace("GEMINI_RATE_LIMIT", f"Key {idx} rate limited", user_id)
                elif "API_KEY" in error_msg or "invalid" in error_msg.lower():
                    admin_trace("GEMINI_INVALID_KEY", f"Key {idx} invalid", user_id)
                else:
                    admin_trace("GEMINI_FAIL", f"Key {idx} failed: {error_msg[:50]}", user_id)
                continue

        admin_trace("GEMINI_ALL_FAIL", f"All {len(config.gemini_keys)} Gemini keys failed", user_id)
        return None
