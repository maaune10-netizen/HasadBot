"""
tunnel.py - Cloudflare tunnel manager and admin commands.

The original bot_handlers.py contained a ``CloudflareTunnelManager``
class with admin commands (``/start_tunnel``, ``/TOP``/``/stop_tunnel``,
``/tunnel_status``). They live here.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Tuple

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, admin_trace
from hasad_bot.database import is_admin


# ==============================================================================
# إعدادات النفق
# ==============================================================================

TUNNEL_PORT = config.dashboard_port
TUNNEL_URL_PATTERN = r'https?://[a-zA-Z0-9\-]+\.trycloudflare\.com'
ADMIN_ID = 7606170063


# ==============================================================================
# كلاس إدارة النفق
# ==============================================================================

class CloudflareTunnelManager:
    """مدير تشغيل وإدارة نفق Cloudflare"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.tunnel_url: Optional[str] = None
        self.is_running: bool = False
        self.port = config.dashboard_port

    def check_cloudflared_installed(self) -> bool:
        """التحقق من وجود أداة cloudflared"""
        return shutil.which("cloudflared") is not None

    async def start_tunnel(self, bot, chat_id: int) -> Tuple[bool, str]:
        """
        بدء تشغيل النفق وإرسال الرابط للإدارة
        إرجاع: (نجاح, رسالة)
        """

        # 1. التحقق من وجود cloudflared
        if not self.check_cloudflared_installed():
            error_msg = "❌ أداة cloudflared غير مثبتة.\n\n📥 رابط التحميل: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
            logger.error(error_msg)
            return False, error_msg

        # 2. إذا كان النفق شغالاً، أرسل الرابط الموجود
        if self.is_running and self.tunnel_url:
            return True, f"✅ النفق شغال بالفعل\n\n🌐 الرابط: {self.tunnel_url}"

        # 3. تشغيل النفق
        try:
            logger.info("🚀 Starting Cloudflare tunnel...")
            admin_trace("TUNNEL", f"Starting tunnel on port {TUNNEL_PORT}")

            # تشغيل العملية (بـ CREATE_NO_WINDOW عشان ما يطلع نافذة cmd)
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0

            self.process = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", f"http://localhost:{TUNNEL_PORT}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                creationflags=creation_flags
            )

            self.is_running = True

            # 4. قراءة المخرجات للبحث عن الرابط
            url = await self._extract_url_from_output()

            if url:
                self.tunnel_url = url
                logger.success(f"✅ Tunnel started: {url}")
                admin_trace("TUNNEL", f"Tunnel URL: {url}")

                # ✅ إرسال الرابط للإدارة (باستخدام HTML مع رابط قابل للضغط)
                message = (
                    f"<b>🌐 Cloudflare Tunnel - HASAD Bot</b>\n\n"
                    f"<b>✅ تم تشغيل النفق بنجاح!</b>\n\n"
                    f"<b>🔗 رابط الداشبورد:</b>\n"
                    f"<b><a href='{url}'>⭐ اضغط هنا لفتح الداشبورد ⭐</a></b>\n\n"
                    f"<b>📅 التاريخ:</b> {now_hijri()}\n"
                    f"<b>⏱️ الوقت:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"<b>⚠️ الرابط صالح طالما النفق شغال.</b>\n"
                    f"<b>🛑 لإيقاف النفق استخدم أمر /TOP</b>"
                )

                await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
                return True, url

            else:
                error_msg = "⚠️ تم تشغيل النفق ولكن لم نتمكن من استخراج الرابط.\nقد يكون هناك خطأ في الاتصال."
                logger.warning(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"❌ فشل تشغيل النفق: {str(e)}"
            logger.error(error_msg)
            admin_trace("TUNNEL_ERR", error_msg)
            return False, error_msg

    async def _extract_url_from_output(self) -> Optional[str]:
        """
        قراءة مخرجات العملية واستخراج رابط النفق
        """
        if not self.process:
            return None

        loop = asyncio.get_event_loop()

        for _ in range(300):
            if self.process.stdout is None:
                break

            line = await loop.run_in_executor(None, self.process.stdout.readline)

            if not line:
                await asyncio.sleep(0.1)
                continue

            logger.debug(f"Tunnel output: {line.strip()}")

            match = re.search(TUNNEL_URL_PATTERN, line)
            if match:
                return match.group(0)

        return None

    async def stop_tunnel(self, bot, chat_id: int) -> Tuple[bool, str]:
        """
        إيقاف النفق
        إرجاع: (نجاح, رسالة)
        """
        if not self.is_running or not self.process:
            return False, "❌ النفق غير شغال حالياً."

        try:
            logger.info("🛑 Stopping Cloudflare tunnel...")
            admin_trace("TUNNEL", "Stopping tunnel")

            self.process.terminate()

            for _ in range(50):
                if self.process.poll() is not None:
                    break
                await asyncio.sleep(0.1)

            if self.process.poll() is None:
                self.process.kill()

            self.process = None
            self.is_running = False
            self.tunnel_url = None

            message = (
                f"<b>🛑 Cloudflare Tunnel - HASAD Bot</b>\n\n"
                f"<b>✅ تم إيقاف النفق بنجاح!</b>\n\n"
                f"<b>📅 التاريخ:</b> {now_hijri()}\n"
                f"<b>⏱️ الوقت:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<b>🔒 الرابط لم يعد متاحاً.</b>"
            )

            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True, "تم إيقاف النفق"

        except Exception as e:
            error_msg = f"❌ فشل إيقاف النفق: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def get_status(self) -> dict:
        """الحصول على حالة النفق"""
        return {
            "is_running": self.is_running,
            "tunnel_url": self.tunnel_url,
            "port": TUNNEL_PORT
        }


# ==============================================================================
# إنشاء نسخة عالمية من المدير
# ==============================================================================

tunnel_manager = CloudflareTunnelManager()


# ==============================================================================
# دوال التكامل مع البوت (للأدمنز فقط)
# ==============================================================================

async def cmd_start_tunnel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    أمر بدء تشغيل النفق (للمالك والأدمنز فقط - الباقي لا يرد)
    """
    uid = update.effective_user.id

    from hasad_bot.database import is_admin
    if not await is_admin(uid):
        return

    wait_msg = await update.message.reply_text(
        "🚀 **جاري تشغيل النفق...**\nالرجاء الانتظار قليلاً (قد يستغرق 10-20 ثانية)",
        parse_mode="HTML"
    )

    success, result = await tunnel_manager.start_tunnel(context.bot, uid)

    try:
        await wait_msg.delete()
    except:
        pass

    if not success:
        await update.message.reply_text(result, parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"<b>✅ تم تشغيل النفق بنجاح!</b>\n\n"
            f"🌐 <b>رابط الداشبورد:</b>\n"
            f"<b><a href='{result}'>⭐ اضغط هنا لفتح الداشبورد ⭐</a></b>\n\n"
            f"🛑 لإيقاف النفق: <code>/TOP</code>\n"
            f"<code>{tunnel_manager.tunnel_url}</code>\n\n"

            f"📊 للحالة: <code>/tunnel_status</code>",
            parse_mode="HTML"
        )


async def cmd_stop_tunnel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إيقاف النفق (للأدمنز فقط - الباقي لا يرد)
    """
    uid = update.effective_user.id

    from hasad_bot.database import is_admin
    if not await is_admin(uid):
        return

    success, message = await tunnel_manager.stop_tunnel(context.bot, uid)
    await update.message.reply_text(message, parse_mode="HTML")


async def cmd_tunnel_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    حالة النفق (للأدمنز فقط - الباقي لا يرد)
    """
    uid = update.effective_user.id

    from hasad_bot.database import is_admin
    if not await is_admin(uid):
        return

    status = tunnel_manager.get_status()

    if status["is_running"] and status["tunnel_url"]:
        text = (
            f"🌐 حالة النفق\n\n"
            f"✅ الحالة:** شغال\n"
            f"🔗 **الرابط:** <b><a href='{status['tunnel_url']}'>⭐ اضغط هنا ⭐</a></b>\n"
            f"🔌 **المنفذ:** {status['port']}\n"
            f"📅 {now_hijri()}"
        )
    else:
        text = (
            f"🌐 **حالة النفق**\n\n"
            f"❌ **الحالة:** متوقف\n"
            f"🔌 **المنفذ:** {status['port']}\n\n"
            f"🚀 للتشغيل: <code>/start_tunnel</code>\n"
            f"📅 {now_hijri()}"
        )

    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_dashboard_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض روابط الداشبورد (محلي + Tunnel) — أدمن فقط
    """
    uid = update.effective_user.id

    from hasad_bot.database import is_admin
    if not await is_admin(uid):
        return

    import socket
    from hasad_bot.web_dashboard import find_working_port

    # كشف المنفذ المحلي الفعلي
    candidate_ports = [config.dashboard_port, 8765, 9876, 9999, 15000]
    actual_port = None
    dashboard_running = False

    for port in candidate_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                actual_port = port
                dashboard_running = True
                break
        finally:
            sock.close()

    if not dashboard_running:
        actual_port = find_working_port(config.dashboard_port, fallbacks=[8765, 9876, 9999, 15000])

    local_url = f"http://127.0.0.1:{actual_port}" if actual_port else f"http://127.0.0.1:{config.dashboard_port}"

    # حالة الـ Tunnel
    t_status = tunnel_manager.get_status()
    t_url = t_status.get("tunnel_url")
    t_running = t_status.get("is_running", False)

    text = (
        "🌐 <b>روابط داشبورد HASAD</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📍 <b>المحلي (Local):</b>\n"
    )
    if dashboard_running and actual_port:
        text += f"   <b><a href='{local_url}'>⭐ {local_url} ⭐</a></b>\n"
        if actual_port != config.dashboard_port:
            text += f"   <i>ℹ️ المنفذ {config.dashboard_port} محجوز — استُخدم {actual_port}</i>\n"
    else:
        text += f"   <code>{local_url}</code> <i>(لم يبدأ بعد)</i>\n"

    text += "\n🌍 <b>الخارجي (Cloudflare Tunnel):</b>\n"
    if t_running and t_url:
        text += f"   <b><a href='{t_url}'>⭐ {t_url} ⭐</a></b>\n"
        text += "   ✅ <b>الحالة:</b> شغال\n"
    else:
        text += "   ⏸️ <b>الحالة:</b> متوقف\n"
        text += f"   💡 للتشغيل: <code>/start_tunnel</code>\n"

    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📅 {now_hijri()}\n\n"
    text += "<b>💡 أوامر سريعة:</b>\n"
    text += "• <code>/art</code> — بدء Tunnel\n"
    text += "• <code>/top</code> — إيقاف Tunnel\n"
    text += "• <code>/ts</code> — حالة Tunnel فقط\n"

    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
