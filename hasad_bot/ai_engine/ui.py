import time
from hasad_bot.utils import admin_trace


def get_engine_keyboard(session=None):
    """كيبورد المحرك - 3 أزرار فقط (تقرير مفصل، إيقاف نهائي، رجوع)"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if not session or not session.is_running:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ بدء حل الواجبات", callback_data='engine_start')]
        ])

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تقرير مفصل", callback_data='engine_pdf_report')],
        [InlineKeyboardButton("🛑 إيقاف نهائي", callback_data='engine_stop')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='engine_back')]
    ])


class UIManager:

    @staticmethod
    async def safe_update(session, text: str, reply_markup=None) -> bool:
        try:
            if hasattr(session, 'last_ui_text') and session.last_ui_text == text:
                return True

            current_time = time.time()
            if hasattr(session, 'last_update_time') and current_time - session.last_update_time < 2.0:
                return True

            session.last_ui_text = text
            session.last_update_time = current_time

            await session.bot.edit_message_text(
                chat_id=session.chat_id,
                message_id=session.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return True

        except Exception as e:
            if "Message is not modified" not in str(e):
                admin_trace("UI_UPDATE_ERR", f"UI update failed: {e}", getattr(session, 'user_id', 'SYSTEM'))
            return False
