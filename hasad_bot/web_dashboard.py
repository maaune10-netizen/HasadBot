#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HASAD Bot - Super Admin Dashboard
لوحة تحكم احترافية متجاوبة مع جميع الأجهزة
نسخة مؤمنة: JWT + bcrypt + Rate Limiting + IP Whitelist
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import asyncio
import time
import json
import math
import secrets
import socket
from typing import List, Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from loguru import logger

from hasad_bot.datetime_utils import datetime, now
from typing import List, Dict
from hasad_bot.ai_engine import stats as ai_stats, active_sessions
from hasad_bot.config import config
from hasad_bot.database import _db_pool, db_get_user, db_all_users
from hasad_bot.utils import now_hijri, admin_trace

# نظام المصادقة الجديد
from hasad_bot.web_dashboard_auth import (
    get_auth_manager,
    require_auth,
    validate_dashboard_security,
    COOKIE_NAME,
    PasswordManager,
    JWTManager,
    RateLimiter,
    AuditLogger,
    IPWhitelist,
    AuthManager,
)


# ==============================================================================
# إعدادات التطبيق والمصادقة (مؤمنة)
# ==============================================================================

app = FastAPI(title="HASAD Bot Super Admin Panel")

# التحقق من الإعدادات قبل البدء (fail-fast)
_is_valid, _warnings = validate_dashboard_security()
if not _is_valid:
    print("\n" + "=" * 60)
    print("❌ CRITICAL: Dashboard security not configured!")
    print("=" * 60)
    for w in _warnings:
        print(f"  {w}")
    print("=" * 60)
    print("🛑 البوت لن يعمل حتى يتم إصلاح هذه الأخطاء!")
    print("💡 شغّل: python generate_dashboard_password.py")
    print("=" * 60 + "\n")
    sys.exit(1)

# تهيئة Auth Manager
auth_manager = get_auth_manager()


class LoginData(BaseModel):
    username: str
    password: str


# ==============================================================================
# Middleware (مؤمن - JWT-based بدلاً من referer)
# ==============================================================================

PUBLIC_PATHS = {"/", "/api/login", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/",)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware محصن - يتحقق من JWT cookie على كل request"""
    path = request.url.path

    # السماح بالمسارات العامة
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # WebSocket له معالج خاص
    if path == "/ws":
        return await call_next(request)

    # Webhook endpoints (إذا وُجدت)
    if path.startswith("/webhook/"):
        return await call_next(request)

    # التحقق من JWT cookie
    payload = await auth_manager.verify_session(request)
    if not payload:
        # إذا كان API، نرجع JSON
        if path.startswith("/api/"):
            return JSONResponse(
                {"error": "غير مصرح - يرجى تسجيل الدخول", "redirect": "/"},
                status_code=401
            )
        # إذا كان صفحة، نعمل redirect
        return RedirectResponse(url="/", status_code=303)

    # إضافة payload للـ request state
    request.state.user = payload.get("sub")
    return await call_next(request)


# ==============================================================================
# قالب تسجيل الدخول
# ==============================================================================

LOGIN_PAGE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HASAD Bot - تسجيل الدخول</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{min-height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#0f172a 100%);display:flex;justify-content:center;align-items:center;padding:16px;font-family:'Segoe UI',Tahoma,sans-serif;overflow:hidden}
        body::before{content:'';position:fixed;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 50%,rgba(59,130,246,0.08) 0%,transparent 50%),radial-gradient(circle at 70% 50%,rgba(168,85,247,0.06) 0%,transparent 50%);animation:float 20s ease-in-out infinite}
        @keyframes float{0%,100%{transform:translate(0,0)}50%{transform:translate(-2%,2%)}}
        .login-container{width:100%;max-width:420px;position:relative;z-index:1}
        .login-card{background:rgba(255,255,255,0.97);border-radius:24px;box-shadow:0 25px 60px rgba(0,0,0,0.4),0 0 0 1px rgba(255,255,255,0.1);overflow:hidden;backdrop-filter:blur(20px)}
        .login-header{background:linear-gradient(135deg,#1e3c72,#2a5298);padding:40px 30px 30px;text-align:center;color:white;position:relative}
        .login-header::after{content:'';position:absolute;bottom:-20px;left:50%;transform:translateX(-50%);width:40px;height:40px;background:white;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 15px rgba(0,0,0,0.1)}
        .login-header h1{font-size:2em;margin-bottom:6px;text-shadow:0 2px 10px rgba(0,0,0,0.2)}
        .login-header p{opacity:0.85;font-size:0.95em}
        .login-body{padding:40px 30px 30px}
        .input-group{margin-bottom:22px}
        .input-group label{display:block;margin-bottom:8px;color:#374151;font-weight:600;font-size:0.9em}
        .input-group input{width:100%;padding:14px 16px;border:2px solid #e5e7eb;border-radius:14px;font-size:1em;background:#f9fafb;transition:all 0.3s}
        .input-group input:focus{outline:none;border-color:#3b82f6;background:white;box-shadow:0 0 0 3px rgba(59,130,246,0.15)}
        .login-btn{width:100%;padding:15px;background:linear-gradient(135deg,#1e3c72,#3b82f6);border:none;border-radius:14px;color:white;font-size:1.05em;font-weight:bold;cursor:pointer;transition:all 0.3s;box-shadow:0 4px 15px rgba(30,60,114,0.3)}
        .login-btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(30,60,114,0.4)}
        .login-btn:active{transform:translateY(0)}
        .error-message{background:#fef2f2;color:#dc2626;padding:12px;border-radius:12px;margin-bottom:18px;text-align:center;display:none;font-size:0.9em;border:1px solid #fecaca}
        .error-message.show{display:block;animation:shake 0.4s}
        @keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-8px)}75%{transform:translateX(8px)}}
        .footer{text-align:center;padding:18px;background:#f8fafc;border-top:1px solid #e5e7eb;font-size:0.8em;color:#9ca3af}

        /* ===== Mobile Responsiveness (≤640px) ===== */
        @media (max-width: 640px) {
            .login-container { max-width: 100%; }
            .login-card { border-radius: 18px; }
            .login-header { padding: 28px 20px 24px; }
            .login-header h1 { font-size: 1.7em; }
            .login-body { padding: 28px 20px 24px; }
            .input-group input { min-height: 48px; }
            .login-btn { min-height: 48px; }
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-card">
            <div class="login-header">
                <h1>🤖 حصاد</h1>
                <p>لوحة التحكم — HASAD Bot</p>
            </div>
            <div class="login-body">
                <div class="error-message" id="errorMsg">⚠️ اسم المستخدم أو كلمة المرور غير صحيحة</div>
                <form id="loginForm">
                    <div class="input-group">
                        <label>👤 اسم المستخدم</label>
                        <input type="text" id="username" placeholder="أدخل اسم المستخدم" autocomplete="username">
                    </div>
                    <div class="input-group">
                        <label>🔒 كلمة المرور</label>
                        <input type="password" id="password" placeholder="أدخل كلمة المرور" autocomplete="current-password">
                    </div>
                    <button type="submit" class="login-btn">🚪 تسجيل الدخول</button>
                </form>
            </div>
            <div class="footer">© 2025 HASAD Bot — جميع الحقوق محفوظة</div>
        </div>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            if (!username || !password) {
                document.getElementById('errorMsg').classList.add('show');
                return;
            }
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ username, password })
                });
                const data = await response.json();
                if (data.success) {
                    // ✅ الـ token محفوظ في HttpOnly cookie - لا حاجة لـ localStorage
                    // (هذا يحمي من XSS attacks)
                    window.location.href = '/dashboard';
                } else if (data.rate_limited) {
                    document.getElementById('errorMsg').textContent = '⏳ ' + (data.message || 'تم تجاوز عدد المحاولات. حاول لاحقاً.');
                    document.getElementById('errorMsg').classList.add('show');
                } else {
                    document.getElementById('errorMsg').textContent = '❌ ' + (data.message || 'اسم المستخدم أو كلمة المرور غير صحيحة');
                    document.getElementById('errorMsg').classList.add('show');
                    setTimeout(() => document.getElementById('errorMsg').classList.remove('show'), 3000);
                }
            } catch (err) {
                document.getElementById('errorMsg').textContent = '⚠️ خطأ في الاتصال بالخادم';
                document.getElementById('errorMsg').classList.add('show');
            }
        });
    </script>
</body>
</html>
"""


# ==============================================================================
# قالب الداشبورد الرئيسي
# ==============================================================================

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HASAD Bot — لوحة التحكم</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
    <style>
        /* ===== CSS Variables ===== */
        :root {
            --primary: #1e3c72;
            --primary-light: #3b82f6;
            --primary-dark: #0f172a;
            --accent: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #06b6d4;
            --bg: #f1f5f9;
            --surface: #ffffff;
            --surface-hover: #f8fafc;
            --text: #1e293b;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --border: #e2e8f0;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
            --shadow: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 10px 30px rgba(0,0,0,0.12);
            --radius: 16px;
            --radius-sm: 10px;
            --transition: 0.25s cubic-bezier(0.4,0,0.2,1);
        }

        /* ===== Reset & Base ===== */
        * { margin:0; padding:0; box-sizing:border-box; }
        html { scroll-behavior: smooth; }
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Tahoma, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }

        /* ===== Layout ===== */
        .app { min-height: 100vh; display: flex; flex-direction: column; }
        .container { max-width: 1440px; margin: 0 auto; padding: 16px; width: 100%; }
        @media(min-width:768px) { .container { padding: 24px; } }

        /* ===== Header ===== */
        .header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            border-radius: var(--radius);
            padding: 20px 24px;
            margin-bottom: 20px;
            color: white;
            box-shadow: var(--shadow-lg);
            position: relative;
            overflow: hidden;
        }
        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -20%;
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
            pointer-events: none;
        }
        .header-top { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; }
        .header h1 { font-size: 1.5em; font-weight: 700; }
        @media(min-width:768px) { .header h1 { font-size: 2em; } }
        .header-meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .header-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255,255,255,0.15);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.82em;
            backdrop-filter: blur(10px);
            white-space: nowrap;
        }
        .header-time { font-size: 0.85em; opacity: 0.85; margin-top: 6px; }

        /* ===== Stats Grid ===== */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        @media(min-width:640px) { .stats-grid { grid-template-columns: repeat(3, 1fr); } }
        @media(min-width:1024px) { .stats-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; } }

        .stat-card {
            background: var(--surface);
            border-radius: var(--radius-sm);
            padding: 16px;
            box-shadow: var(--shadow-sm);
            transition: var(--transition);
            cursor: pointer;
            border: 1px solid var(--border);
            position: relative;
            overflow: hidden;
        }
        .stat-card::after {
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 4px;
            height: 100%;
            background: var(--primary-light);
            opacity: 0;
            transition: var(--transition);
        }
        .stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow); }
        .stat-card:hover::after { opacity: 1; }
        .stat-card .title {
            color: var(--text-secondary);
            font-size: 0.78em;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 5px;
            font-weight: 500;
        }
        .stat-card .value {
            color: var(--primary);
            font-size: 1.6em;
            font-weight: 700;
            line-height: 1.2;
        }
        @media(min-width:768px) { .stat-card .value { font-size: 2em; } }
        .stat-card .subtitle { color: var(--success); font-size: 0.78em; margin-top: 4px; font-weight: 500; }

        /* ===== Charts ===== */
        .charts-row {
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
            margin-bottom: 20px;
        }
        @media(min-width:768px) { .charts-row { grid-template-columns: 2fr 1fr; } }
        .chart-container {
            background: var(--surface);
            border-radius: var(--radius);
            padding: 20px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border);
        }
        .chart-container h3 {
            color: var(--text);
            margin-bottom: 16px;
            font-size: 1em;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
        }
        .chart-wrap { position: relative; width: 100%; }

        /* ===== Tabs ===== */
        .tabs {
            background: var(--surface);
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border);
        }
        .tab-header {
            display: flex;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
            background: #f8fafc;
            border-bottom: 2px solid var(--border);
            gap: 0;
        }
        .tab-header::-webkit-scrollbar { display: none; }
        .tab-btn {
            padding: 14px 18px;
            background: none;
            border: none;
            cursor: pointer;
            font-size: 0.88em;
            color: var(--text-secondary);
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
            font-weight: 500;
            border-bottom: 3px solid transparent;
            position: relative;
            flex-shrink: 0;
        }
        .tab-btn:hover { background: rgba(59,130,246,0.05); color: var(--primary); }
        .tab-btn.active {
            color: var(--primary);
            border-bottom-color: var(--primary-light);
            font-weight: 600;
            background: rgba(59,130,246,0.05);
        }
        .tab-btn .tab-count {
            background: var(--primary-light);
            color: white;
            padding: 1px 7px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 600;
        }
        .tab-content { padding: 16px; }
        @media(min-width:768px) { .tab-content { padding: 24px; } }
        .tab-pane { display: none; animation: fadeIn 0.3s ease; }
        .tab-pane.active { display: block; }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }

        /* ===== Tables ===== */
        .table-container { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; font-size: 0.88em; }
        th {
            background: var(--primary);
            color: white;
            padding: 12px 10px;
            text-align: center;
            font-weight: 600;
            font-size: 0.9em;
            white-space: nowrap;
            position: sticky;
            top: 0;
        }
        td {
            padding: 10px;
            border-bottom: 1px solid var(--border);
            text-align: center;
            vertical-align: middle;
        }
        tr:hover td { background: var(--surface-hover); }
        .user-row { cursor: pointer; transition: var(--transition); }
        .user-row:hover td { background: #eff6ff !important; }

        /* ===== Cards (mobile-friendly list) ===== */
        .card-list { display: flex; flex-direction: column; gap: 12px; }
        .card-item {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 16px;
            transition: var(--transition);
        }
        .card-item:hover { box-shadow: var(--shadow); border-color: var(--primary-light); }
        .card-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .card-item-title { font-weight: 600; color: var(--text); }
        .card-item-body { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 0.85em; }
        .card-item-body .label { color: var(--text-muted); }
        .card-item-body .val { color: var(--text); font-weight: 500; text-align: left; }

        /* ===== Badges ===== */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.78em;
            font-weight: 600;
            white-space: nowrap;
        }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-info { background: #cffafe; color: #155e75; }
        .badge-primary { background: #dbeafe; color: #1e40af; }
        .badge-outline { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }

        /* ===== Status ===== */
        .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-left: 6px; }
        .status-online { background: var(--success); box-shadow: 0 0 6px rgba(16,185,129,0.4); }
        .status-offline { background: var(--text-muted); }

        /* ===== Modal ===== */
        .modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15,23,42,0.6);
            z-index: 1000;
            backdrop-filter: blur(4px);
            animation: fadeIn 0.2s;
        }
        .modal-overlay.show { display: flex; justify-content: center; align-items: flex-start; padding: 20px; }
        .modal-box {
            background: var(--surface);
            width: 100%;
            max-width: 680px;
            border-radius: var(--radius);
            box-shadow: var(--shadow-lg);
            max-height: 85vh;
            overflow-y: auto;
            margin-top: 40px;
            animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            background: var(--surface);
            z-index: 1;
            border-radius: var(--radius) var(--radius) 0 0;
        }
        .modal-header h2 { color: var(--primary); font-size: 1.15em; }
        .modal-close {
            width: 36px; height: 36px;
            background: #f1f5f9;
            border: none;
            border-radius: 50%;
            font-size: 1.3em;
            cursor: pointer;
            color: var(--text-secondary);
            transition: var(--transition);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .modal-close:hover { background: #fee2e2; color: var(--danger); }
        .modal-body { padding: 20px 24px; }

        /* ===== Info Grid (modal) ===== */
        .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
        .info-item { padding: 12px; background: #f8fafc; border-radius: var(--radius-sm); border: 1px solid var(--border); }
        .info-item .label { color: var(--text-muted); font-size: 0.78em; margin-bottom: 4px; }
        .info-item .value { color: var(--text); font-size: 1em; font-weight: 600; word-break: break-all; }
        .password-field { font-family: 'Courier New', monospace; background: #1e293b; color: #4ade80; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; display: inline-block; }

        /* ===== Activity Feed ===== */
        .activity-feed { max-height: 400px; overflow-y: auto; }
        .activity-item {
            padding: 12px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 12px;
            transition: var(--transition);
        }
        .activity-item:hover { background: var(--surface-hover); }
        .activity-time { color: var(--text-muted); font-size: 0.78em; min-width: 70px; }
        .activity-icon {
            width: 32px; height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85em;
            flex-shrink: 0;
        }
        .icon-success { background: #d1fae5; color: #065f46; }
        .icon-error { background: #fee2e2; color: #991b1b; }
        .icon-info { background: #cffafe; color: #155e75; }

        /* ===== Filters ===== */
        .filter-bar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
        .filter-input, .filter-select {
            padding: 10px 14px;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            font-size: 0.9em;
            background: var(--surface);
            transition: var(--transition);
            min-width: 0;
        }
        .filter-input { flex: 1; min-width: 180px; }
        .filter-input:focus, .filter-select:focus { outline: none; border-color: var(--primary-light); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }

        /* ===== Questions ===== */
        .question-item {
            padding: 14px;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            margin-bottom: 10px;
            transition: var(--transition);
        }
        .question-item:hover { border-color: var(--primary-light); box-shadow: var(--shadow-sm); }
        .question-text { font-weight: 600; margin-bottom: 8px; color: var(--text); }
        .question-meta { display: flex; gap: 12px; font-size: 0.82em; color: var(--text-secondary); flex-wrap: wrap; }
        .question-source {
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .source-db { background: #d1fae5; color: #065f46; }
        .source-groq { background: #dbeafe; color: #1e40af; }
        .source-gemini { background: #fef3c7; color: #92400e; }
        .source-random { background: #fee2e2; color: #991b1b; }

        /* ===== Detail Modal Styles ===== */
        .table-wrap { overflow-x: auto; margin: 0 -4px; }
        .table-wrap table { width: 100%; border-collapse: collapse; min-width: 500px; }
        .q-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
        .q-text { font-weight: 600; color: var(--text); font-size: 0.92em; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
        .q-meta { display: flex; gap: 14px; font-size: 0.8em; color: var(--text-secondary); flex-wrap: wrap; }
        .q-meta span { display: flex; align-items: center; gap: 4px; }
        .source-tag { padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; white-space: nowrap; }

        /* ===== Section Headers ===== */
        .section-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
            font-size: 1.05em;
            font-weight: 600;
            color: var(--text);
        }

        /* ===== Empty State ===== */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }
        .empty-state .icon { font-size: 2.5em; margin-bottom: 12px; }
        .empty-state .text { font-size: 0.95em; }

        /* ===== API Cards ===== */
        .api-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        @media(min-width:640px) { .api-grid { grid-template-columns: repeat(4, 1fr); } }
        .api-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 16px;
            text-align: center;
            transition: var(--transition);
        }
        .api-card:hover { transform: translateY(-2px); box-shadow: var(--shadow); }
        .api-card .api-icon { font-size: 1.8em; margin-bottom: 8px; }
        .api-card .api-value { font-size: 1.8em; font-weight: 700; color: var(--primary); }
        .api-card .api-percent { font-size: 0.82em; color: var(--success); margin-top: 4px; }
        .api-card .api-label { font-size: 0.82em; color: var(--text-secondary); margin-top: 6px; }

        /* ===== Admin Actions ===== */
        .user-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .action-btn {
            padding: 8px 14px;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            font-size: 0.85em;
            font-weight: 600;
            cursor: pointer;
            background: var(--surface);
            color: var(--text);
            transition: var(--transition);
        }
        .action-btn:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
        .action-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .action-btn-primary { background: #dbeafe; border-color: #93c5fd; color: #1e40af; }
        .action-btn-danger { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }
        .action-btn-warning { background: #fef3c7; border-color: #fcd34d; color: #92400e; }
        .action-btn-info { background: #cffafe; border-color: #67e8f9; color: #155e75; }
        .action-btn-ghost { background: transparent; border-color: var(--border); color: var(--text-secondary); }

        /* ===== Action Panels & Messages ===== */
        .action-msg { padding: 10px 14px; border-radius: var(--radius-sm); font-size: 0.85em; font-weight: 600; margin-bottom: 12px; }
        .action-msg-success { background: #d1fae5; color: #065f46; }
        .action-msg-error { background: #fee2e2; color: #991b1b; }
        .action-panel {
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 14px;
            margin-bottom: 12px;
        }
        .action-panel-danger { background: #fff7f7; border-color: #fecaca; }
        .action-panel-title { font-weight: 600; margin-bottom: 10px; color: var(--text); font-size: 0.9em; }
        .action-panel-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
        .action-panel-row label { font-size: 0.85em; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
        .action-panel-btns { display: flex; gap: 8px; margin-top: 10px; }
        .day-choices { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .day-choice {
            padding: 6px 14px;
            border: 1px solid var(--border);
            border-radius: 20px;
            background: var(--surface);
            cursor: pointer;
            font-size: 0.82em;
            font-weight: 600;
            color: var(--text-secondary);
            transition: var(--transition);
        }
        .day-choice:hover { border-color: var(--primary-light); }
        .day-choice.active { background: var(--primary); border-color: var(--primary); color: white; }
        .day-custom {
            padding: 8px 12px;
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            font-size: 0.85em;
            width: 130px;
            background: var(--surface);
        }
        .day-custom:focus { outline: none; border-color: var(--primary-light); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .delete-warning {
            background: #fee2e2;
            border: 1px solid #fca5a5;
            color: #991b1b;
            padding: 10px 14px;
            border-radius: var(--radius-sm);
            font-size: 0.85em;
            margin-bottom: 10px;
        }
        .payment-done { opacity: 0.55; }

        /* ===== Toast ===== */
        .toast {
            position: fixed;
            bottom: 60px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 2000;
            padding: 12px 24px;
            border-radius: 10px;
            font-size: 0.9em;
            font-weight: 600;
            color: white;
            box-shadow: var(--shadow-lg);
            max-width: 90vw;
            text-align: center;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .toast-success { background: #065f46; }
        .toast-error { background: #991b1b; }

        /* ===== Scrollbar ===== */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        /* ===== Connection Status ===== */
        .ws-status {
            position: fixed;
            bottom: 16px;
            left: 16px;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.78em;
            font-weight: 600;
            z-index: 999;
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .ws-connected { background: #d1fae5; color: #065f46; }
        .ws-disconnected { background: #fee2e2; color: #991b1b; animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }

        /* ===== Responsive Helpers ===== */
        .hide-mobile { display: none; }
        @media(min-width:768px) { .hide-mobile { display: table-cell; } }
        .hide-desktop { display: table-cell; }
        @media(min-width:768px) { .hide-desktop { display: none; } }

        /* ===== Loading Skeleton ===== */
        .skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 6px;
        }
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }

        /* ===== Mobile Responsiveness (≤640px) ===== */
        @media (max-width: 640px) {
            /* Layout */
            .container { padding: 12px; }
            .header h1 { font-size: 1.2em; }
            .header-meta { gap: 6px; }

            /* Sticky tabs stay reachable while scrolling */
            .tab-header { position: sticky; top: 0; z-index: 30; padding: 6px 4px; }

            /* Filters stack full-width */
            .filter-bar { flex-wrap: wrap; }
            .filter-input, .filter-select { flex: 1 1 100%; min-width: 0; }

            /* Tables scroll horizontally */
            .table-container th, .table-container td { white-space: nowrap; }
            .table-container table { font-size: 0.82em; }

            /* Modals → bottom-sheet feel */
            .modal-overlay.show { padding: 10px; align-items: flex-end; padding-bottom: max(10px, env(safe-area-inset-bottom)); }
            .modal-box { max-width: 100%; max-height: 92vh; border-radius: 16px 16px 0 0; }
            .modal-body { padding: 14px 16px; overflow-y: auto; }
            .info-grid { grid-template-columns: 1fr; }

            /* Action panels — full-width touch-friendly buttons */
            .action-panel-btns { flex-wrap: wrap; }
            .action-panel-btns .action-btn { flex: 1 1 100%; min-height: 46px; }
            .day-choice { min-height: 44px; padding: 10px 14px; }

            /* Log box */
            #logs-body { font-size: 0.78em; max-height: 50vh; }

            /* Touch targets */
            .action-btn, .tab-btn, .day-choice { min-height: 44px; }

            /* Safe area */
            body { padding-bottom: env(safe-area-inset-bottom); }
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div class="header-top">
                    <h1>🤖 حصاد — لوحة التحكم</h1>
                    <div class="header-meta">
                        <span class="header-badge">🟢 النظام شغال</span>
                        <span class="header-badge" id="uptime">⏱️ 0s</span>
                    </div>
                </div>
                <div class="header-time" id="current-time"></div>
            </div>

            <!-- Stats Grid -->
            <div class="stats-grid" id="stats-grid">
                <div class="stat-card skeleton" style="height:90px"></div>
                <div class="stat-card skeleton" style="height:90px"></div>
                <div class="stat-card skeleton" style="height:90px"></div>
                <div class="stat-card skeleton" style="height:90px"></div>
            </div>

            <!-- Charts -->
            <div class="charts-row">
                <div class="chart-container">
                    <h3>📊 مصادر الحلول</h3>
                    <div class="chart-wrap"><canvas id="sourcesChart"></canvas></div>
                </div>
                <div class="chart-container">
                    <h3>⏰ نشاط آخر 24 ساعة</h3>
                    <div class="chart-wrap"><canvas id="activityChart"></canvas></div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="tabs">
                <div class="tab-header" id="tab-header">
                    <button class="tab-btn active" data-tab="users" onclick="showTab('users',this)">
                        <span>👥</span><span class="hide-mobile">المستخدمين</span>
                    </button>
                    <button class="tab-btn" data-tab="active" onclick="showTab('active',this)">
                        <span>🟢</span><span class="hide-mobile">النشطين</span>
                    </button>
                    <button class="tab-btn" data-tab="questions" onclick="showTab('questions',this)">
                        <span>📝</span><span class="hide-mobile">الأسئلة</span>
                    </button>
                    <button class="tab-btn" data-tab="errors" onclick="showTab('errors',this)">
                        <span>❌</span><span class="hide-mobile">الأخطاء</span>
                    </button>
                    <button class="tab-btn" data-tab="subscriptions" onclick="showTab('subscriptions',this)">
                        <span>💎</span><span class="hide-mobile">المشتركين</span>
                    </button>
                    <button class="tab-btn" data-tab="api" onclick="showTab('api',this)">
                        <span>🔌</span><span class="hide-mobile">APIs</span>
                    </button>
                    <button class="tab-btn" data-tab="payments" onclick="showTab('payments',this)">
                        <span>💳</span><span class="hide-mobile">طلبات الدفع</span>
                    </button>
                    <button class="tab-btn" data-tab="settings" onclick="showTab('settings',this)">
                        <span>💳</span><span class="hide-mobile">الإعدادات</span>
                    </button>
                    <button class="tab-btn" data-tab="messaging" onclick="showTab('messaging',this)">
                        <span>📢</span><span class="hide-mobile">البث والإعلانات</span>
                    </button>
                    <button class="tab-btn" data-tab="support" onclick="showTab('support',this)">
                        <span>🛟</span><span class="hide-mobile">الدعم</span>
                    </button>
                    <button class="tab-btn" data-tab="logs" onclick="showTab('logs',this)">
                        <span>📜</span><span class="hide-mobile">السجلات</span>
                    </button>
                    <button class="tab-btn" data-tab="backups" onclick="showTab('backups',this)">
                        <span>💾</span><span class="hide-mobile">النسخ الاحتياطية</span>
                    </button>
                    <button class="tab-btn" data-tab="control" onclick="showTab('control',this)">
                        <span>⚙️</span><span class="hide-mobile">التحكم</span>
                    </button>
                    <button class="tab-btn" data-tab="admins" onclick="showTab('admins',this)">
                        <span>👑</span><span class="hide-mobile">الأدمنز</span>
                    </button>
                    <button class="tab-btn" data-tab="resellers" onclick="showTab('resellers',this)">
                        <span>🏪</span><span class="hide-mobile">الموزعون</span>
                    </button>
                </div>

                <div class="tab-content">
                    <!-- Users Tab -->
                    <div class="tab-pane active" id="tab-users">
                        <div class="filter-bar">
                            <input type="text" class="filter-input" placeholder="🔍 بحث عن مستخدم..." id="userSearch" oninput="filterUsers()">
                            <select class="filter-select" id="userFilter" onchange="filterUsers()">
                                <option value="all">الكل</option>
                                <option value="active">نشطين</option>
                                <option value="vip">مشتركين</option>
                            </select>
                        </div>
                        <div class="table-container">
                            <table id="usersTable">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>الاسم</th>
                                        <th class="hide-mobile">يوزر المنصة</th>
                                        <th>الاشتراك</th>
                                        <th class="hide-mobile">آخر نشاط</th>
                                        <th class="hide-mobile">الواجبات</th>
                                        <th>الحالة</th>
                                    </tr>
                                </thead>
                                <tbody id="users-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Active Tab -->
                    <div class="tab-pane" id="tab-active">
                        <div class="section-header">🟢 المستخدمين النشطين الآن</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>المستخدم</th>
                                        <th>الحالة</th>
                                        <th class="hide-mobile">النشاط</th>
                                        <th>التفاصيل</th>
                                    </tr>
                                </thead>
                                <tbody id="active-users-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Questions Tab -->
                    <div class="tab-pane" id="tab-questions">
                        <div class="section-header">📝 آخر الأسئلة المحلولة</div>
                        <div class="filter-bar">
                            <select class="filter-select" id="questionFilter" onchange="filterQuestions()">
                                <option value="all">كل الأسئلة</option>
                                <option value="db">قاعدة البيانات</option>
                                <option value="groq">Groq</option>
                                <option value="gemini">Gemini</option>
                                <option value="random">عشوائي</option>
                            </select>
                        </div>
                        <div id="questions-list" class="card-list"></div>
                    </div>

                    <!-- Errors Tab -->
                    <div class="tab-pane" id="tab-errors">
                        <div class="section-header">❌ سجل الأخطاء</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>الوقت</th>
                                        <th>المستخدم</th>
                                        <th class="hide-mobile">الحدث</th>
                                        <th>الخطأ</th>
                                    </tr>
                                </thead>
                                <tbody id="errors-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Subscriptions Tab -->
                    <div class="tab-pane" id="tab-subscriptions">
                        <div class="section-header">💎 المشتركين النشطين</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>المستخدم</th>
                                        <th>تاريخ الانتهاء</th>
                                        <th>الأيام المتبقية</th>
                                        <th class="hide-mobile">الواجبات</th>
                                    </tr>
                                </thead>
                                <tbody id="subscriptions-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- API Tab -->
                    <div class="tab-pane" id="tab-api">
                        <div class="section-header">🔌 إحصائيات APIs</div>
                        <div class="api-grid">
                            <div class="api-card">
                                <div class="api-icon">🦙</div>
                                <div class="api-value" id="groq-value">0</div>
                                <div class="api-percent" id="groq-percent">0%</div>
                                <div class="api-label">Groq</div>
                            </div>
                            <div class="api-card">
                                <div class="api-icon">✨</div>
                                <div class="api-value" id="gemini-value">0</div>
                                <div class="api-percent" id="gemini-percent">0%</div>
                                <div class="api-label">Gemini</div>
                            </div>
                            <div class="api-card">
                                <div class="api-icon">💾</div>
                                <div class="api-value" id="db-value">0</div>
                                <div class="api-percent" id="db-percent">0%</div>
                                <div class="api-label">قاعدة البيانات</div>
                            </div>
                            <div class="api-card">
                                <div class="api-icon">🎲</div>
                                <div class="api-value" id="random-value">0</div>
                                <div class="api-percent" id="random-percent">0%</div>
                                <div class="api-label">عشوائي</div>
                            </div>
                        </div>
                    </div>

                    <!-- Payments Tab -->
                    <div class="tab-pane" id="tab-payments">
                        <div class="section-header">💳 طلبات الدفع</div>
                        <div id="payments-msg" class="action-msg" style="display:none"></div>
                        <div id="payments-panel"></div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>الاسم</th>
                                        <th>الخطة</th>
                                        <th>السعر</th>
                                        <th>طريقة الدفع</th>
                                        <th>الملاحظة</th>
                                        <th>الوقت</th>
                                        <th>الحالة</th>
                                        <th>إجراءات</th>
                                    </tr>
                                </thead>
                                <tbody id="payments-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Messaging Tab -->
                    <div class="tab-pane" id="tab-messaging">
                        <div class="section-header">📢 البث والإعلانات</div>
                        <div id="messaging-msg" class="action-msg" style="display:none"></div>

                        <!-- Broadcast Section -->
                        <div class="action-panel">
                            <div class="action-panel-title">📤 إرسال بث جماعي</div>
                            <div class="action-panel-row">
                                <label for="broadcast-target">الفئة المستهدفة:</label>
                                <select id="broadcast-target" class="filter-select" onchange="loadBroadcastPreview()">
                                    <option value="all">🌍 الكل</option>
                                    <option value="subscribed">💎 المشتركين</option>
                                    <option value="not_subscribed">❌ غير المشتركين</option>
                                    <option value="linked">🔗 مرتبط المنصة</option>
                                    <option value="not_linked">🚫 غير مرتبط</option>
                                </select>
                            </div>
                            <div id="broadcast-preview" style="margin-bottom:10px"></div>
                            <textarea id="broadcast-text" class="day-custom" style="width:100%;min-height:110px;box-sizing:border-box" placeholder="اكتب رسالة البث هنا... (يدعم HTML)"></textarea>
                            <div class="action-panel-btns">
                                <button class="action-btn action-btn-info" onclick="previewBroadcastMessage()">👁️ معاينة</button>
                                <button class="action-btn action-btn-primary" onclick="confirmBroadcastSend()">📤 إرسال البث</button>
                            </div>
                            <div id="broadcast-preview-box" style="display:none"></div>
                        </div>
                        <div id="broadcast-progress" style="display:none"></div>

                        <!-- Announcements Section -->
                        <div class="section-header">📣 الإعلانات المبرمجة</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>النوع</th>
                                        <th>الفلتر</th>
                                        <th>الموعد</th>
                                        <th>الحالة</th>
                                        <th>إجراءات</th>
                                    </tr>
                                </thead>
                                <tbody id="announcements-body"></tbody>
                            </table>
                        </div>
                        <div id="announcements-progress" style="display:none"></div>
                    </div>

                    <!-- Support Tab -->
                    <div class="tab-pane" id="tab-support">
                        <div class="section-header">🛟 الدعم</div>
                        <div id="support-msg" class="action-msg" style="display:none"></div>
                        <div class="filter-bar">
                            <input type="text" class="filter-input" placeholder="🔍 بحث بالاسم أو المعرف..." id="supportSearch" oninput="filterSupportConversations()">
                            <select class="filter-select" id="supportStatus" onchange="loadSupportConversations()">
                                <option value="all">الكل</option>
                                <option value="open">مفتوحة</option>
                                <option value="closed">مغلقة</option>
                            </select>
                        </div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>الاسم</th>
                                        <th>المعرف</th>
                                        <th class="hide-mobile">آخر نشاط</th>
                                        <th class="hide-mobile">اتجاه آخر</th>
                                        <th class="hide-mobile">عدد الرسائل</th>
                                        <th>الحالة</th>
                                    </tr>
                                </thead>
                                <tbody id="support-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Logs Tab -->
                    <div class="tab-pane" id="tab-logs">
                        <div class="section-header">📜 السجلات</div>
                        <div id="logs-msg" class="action-msg" style="display:none"></div>
                        <div class="filter-bar">
                            <select class="filter-select" id="logsFileSelect" onchange="switchLogFile()">
                                <option value="">— اختر ملف السجل —</option>
                            </select>
                            <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85em;color:var(--text-secondary)">
                                <input type="checkbox" id="logsAutoRefresh" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer" onchange="logsAutoRefresh()">
                                تحديث تلقائي (5 ثوانٍ)
                            </label>
                            <select class="filter-select" id="logsLimitSelect" onchange="loadLogFile()">
                                <option value="100">100 سطر</option>
                                <option value="500">500 سطر</option>
                            </select>
                        </div>
                        <pre id="logs-body" style="background:#0f172a;color:#e2e8f0;padding:14px;border-radius:8px;max-height:460px;overflow:auto;font-family:Consolas,Menlo,monospace;font-size:0.78em;line-height:1.6;direction:ltr;text-align:left;white-space:pre-wrap;word-break:break-all;margin:0"></pre>

                        <div class="section-header" style="margin-top:24px">سجل مستخدم</div>
                        <div class="filter-bar">
                            <input type="text" class="filter-input" placeholder="🆔 معرف المستخدم..." id="userLogUid">
                            <button class="action-btn action-btn-primary" onclick="loadUserLog()">عرض</button>
                        </div>
                        <div id="userlog-table-wrap" class="table-container" style="display:none">
                            <table>
                                <thead>
                                    <tr>
                                        <th>الوقت</th>
                                        <th>الخطوة</th>
                                        <th>التفاصيل</th>
                                    </tr>
                                </thead>
                                <tbody id="userlog-body"></tbody>
                            </table>
                        </div>

                        <div class="section-header" style="margin-top:24px">سجل التدقيق</div>
                        <div class="filter-bar">
                            <input type="text" class="filter-input" placeholder="🔍 البحث في الإجراء (action)..." id="auditActionInput">
                            <select class="filter-select" id="auditLimitSelect">
                                <option value="50">50 سطر</option>
                                <option value="100" selected>100 سطر</option>
                                <option value="500">500 سطر</option>
                            </select>
                            <button class="action-btn action-btn-primary" onclick="loadAuditLog()">عرض</button>
                        </div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>المشرف</th>
                                        <th>الإجراء</th>
                                        <th class="hide-mobile">التفاصيل</th>
                                        <th>الوقت</th>
                                    </tr>
                                </thead>
                                <tbody id="audit-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Backups Tab -->
                    <div class="tab-pane" id="tab-backups">
                        <div class="section-header">💾 النسخ الاحتياطية</div>
                        <div id="backups-msg" class="action-msg" style="display:none"></div>
                        <div class="api-grid">
                            <div class="api-card">
                                <div class="api-icon">📦</div>
                                <div class="api-label">نسخة قاعدة البيانات</div>
                                <button class="action-btn action-btn-primary backup-btn" style="margin-top:8px" onclick="confirmBackup('db')">إنشاء نسخة</button>
                            </div>
                            <div class="api-card">
                                <div class="api-icon">📊</div>
                                <div class="api-label">تصدير بيانات الطلاب</div>
                                <button class="action-btn action-btn-primary backup-btn" style="margin-top:8px" onclick="confirmBackup('cv')">إنشاء نسخة</button>
                            </div>
                            <div class="api-card">
                                <div class="api-icon">📜</div>
                                <div class="api-label">تصدير سجلات الإدارة</div>
                                <button class="action-btn action-btn-primary backup-btn" style="margin-top:8px" onclick="confirmBackup('admin_logs')">إنشاء نسخة</button>
                            </div>
                        </div>
                    </div>

                    <!-- Control Tab -->
                    <div class="tab-pane" id="tab-control">
                        <div class="section-header">⚙️ التحكم في البوت</div>
                        <div id="control-msg" class="action-msg" style="display:none"></div>
                        <div class="filter-bar" style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
                            <span style="font-size:0.9em;color:var(--text-secondary)">حالة التجميد:</span>
                            <span class="badge" id="control-frozen-badge">—</span>
                            <span style="font-size:0.9em;color:var(--text-secondary)">الوضع:</span>
                            <span class="badge" id="control-mode-badge">—</span>
                            <span style="font-size:0.9em;color:var(--text-secondary)">البوت:</span>
                            <span class="badge" id="control-alive-badge">—</span>
                            <span style="font-size:0.9em;color:var(--text-secondary)">آخر إحصائيات:</span>
                            <span class="badge badge-outline" id="control-last-ts">—</span>
                        </div>
                        <div class="action-panel">
                            <div class="action-panel-title">⚙️ تغيير الحالة</div>
                            <div class="action-panel-btns" id="control-actions">
                                <button class="action-btn action-btn-danger" id="btn-freeze" onclick="confirmFreezeToggle(true)" style="display:none">❄️ تجميد البوت</button>
                                <button class="action-btn action-btn-primary" id="btn-unfreeze" onclick="confirmFreezeToggle(false)" style="display:none">▶️ إلغاء التجميد</button>
                                <button class="action-btn action-btn-info" id="btn-public" onclick="confirmModeToggle(true)" style="display:none">🌍 وضع عام</button>
                                <button class="action-btn action-btn-warning" id="btn-private" onclick="confirmModeToggle(false)" style="display:none">🔐 وضع خاص</button>
                            </div>
                        </div>
                    </div>

                    <!-- Admins Tab -->
                    <div class="tab-pane" id="tab-admins">
                        <div class="section-header">👑 الأدمنز</div>
                        <div id="admins-msg" class="action-msg" style="display:none"></div>
                        <div class="action-panel">
                            <div class="action-panel-title">➕ إضافة أدمن</div>
                            <div class="action-panel-row">
                                <label for="admin-add-uid">معرف المستخدم (Telegram ID):
                                    <input type="number" id="admin-add-uid" class="day-custom" placeholder="مثال: 123456789" style="width:180px">
                                </label>
                            </div>
                            <div class="action-panel-btns">
                                <button class="action-btn action-btn-primary" id="admin-add-btn" onclick="addAdmin()">➕ إضافة</button>
                            </div>
                        </div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>المعرف</th>
                                        <th>الاسم</th>
                                        <th>اليوزر</th>
                                        <th>النوع</th>
                                        <th>عدد الموزعين الفرعيين</th>
                                        <th>إجراءات</th>
                                    </tr>
                                </thead>
                                <tbody id="admins-body"></tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Resellers Tab -->
                    <div class="tab-pane" id="tab-resellers">
                        <div class="section-header">🏪 الموزعون</div>
                        <div id="resellers-msg" class="action-msg" style="display:none"></div>
                        <div class="api-grid" id="resellers-stats-grid"></div>
                        <div class="action-panel">
                            <div class="action-panel-title">➕ إضافة موزع</div>
                            <div class="action-panel-row">
                                <label for="reseller-add-uid">معرف المستخدم (Telegram ID):
                                    <input type="number" id="reseller-add-uid" class="day-custom" placeholder="مثال: 123456789" style="width:180px">
                                </label>
                            </div>
                            <div class="action-panel-btns">
                                <button class="action-btn action-btn-primary" id="reseller-add-btn" onclick="addReseller()">➕ إضافة</button>
                            </div>
                        </div>
                        <div class="action-panel">
                            <div class="action-panel-title">⚙️ أسعار الموزعين</div>
                            <div class="action-panel-row">
                                <label for="price-weekly">أسبوعي:
                                    <input type="number" id="price-weekly" class="day-custom" min="0" step="0.01" placeholder="0" style="width:110px">
                                </label>
                                <label for="price-monthly">شهري:
                                    <input type="number" id="price-monthly" class="day-custom" min="0" step="0.01" placeholder="0" style="width:110px">
                                </label>
                                <label for="price-semester">ترم:
                                    <input type="number" id="price-semester" class="day-custom" min="0" step="0.01" placeholder="0" style="width:110px">
                                </label>
                            </div>
                            <div class="action-panel-btns">
                                <button class="action-btn action-btn-primary" id="prices-save-btn" onclick="saveResellerPrices()">💾 حفظ الأسعار</button>
                            </div>
                        </div>
                        <div class="action-panel">
                            <div class="action-panel-title">🚫 Ban عميل موزع</div>
                            <div class="action-panel-row">
                                <label for="ban-customer-uid">معرف العميل:
                                    <input type="number" id="ban-customer-uid" class="day-custom" placeholder="مثال: 123456789" style="width:180px">
                                </label>
                                <label for="ban-customer-action">الإجراء:
                                    <select id="ban-customer-action" class="filter-select">
                                        <option value="ban">🚫 Ban (حظر نهائي)</option>
                                        <option value="stop">⏸️ Stop (إيقاف مؤقت)</option>
                                    </select>
                                </label>
                            </div>
                            <div class="action-panel-btns">
                                <button class="action-btn action-btn-danger" id="ban-customer-btn" onclick="confirmBanCustomer()">🚫 تنفيذ</button>
                            </div>
                        </div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>المعرف</th>
                                        <th>الاسم</th>
                                        <th>الرصيد</th>
                                        <th>عدد العملاء</th>
                                        <th>إجراءات</th>
                                    </tr>
                                </thead>
                                <tbody id="resellers-body"></tbody>
                            </table>
                        </div>
                    </div>
                    <!-- Settings Tab -->
                    <div class="tab-pane" id="tab-settings">
                        <div class="section-header">💳 إعدادات الدفع</div>
                        <div id="settings-msg" class="action-msg" style="display:none"></div>
                        <div class="section-header" style="margin-top:18px">📦 الخطط</div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px" id="settings-plans-grid"></div>
                        <div class="action-panel">
                            <div class="action-panel-title">🏦 بيانات البنك</div>
                            <div class="action-panel-row">
                                <label for="ps-bank_name">اسم البنك: <input type="text" id="ps-bank_name" class="day-custom" style="width:180px" maxlength="200"></label>
                                <label for="ps-bank_account_name">اسم المستفيد: <input type="text" id="ps-bank_account_name" class="day-custom" style="width:180px" maxlength="200"></label>
                            </div>
                            <div class="action-panel-row">
                                <label for="ps-bank_account_number">رقم الحساب: <input type="text" id="ps-bank_account_number" class="day-custom" style="width:180px" maxlength="200"></label>
                                <label for="ps-bank_iban">الآيبان: <input type="text" id="ps-bank_iban" class="day-custom" style="width:220px" maxlength="200"></label>
                            </div>
                        </div>
                        <div class="action-panel">
                            <div class="action-panel-title">📱 بيانات STC Pay</div>
                            <div class="action-panel-row">
                                <label for="ps-stc_phone">رقم الجوال: <input type="text" id="ps-stc_phone" class="day-custom" style="width:180px" maxlength="200"></label>
                                <label for="ps-stc_notes">ملاحظات: <input type="text" id="ps-stc_notes" class="day-custom" style="width:220px" maxlength="200"></label>
                            </div>
                        </div>
                        <div class="action-panel">
                            <div class="action-panel-title">💳 طرق الدفع</div>
                            <div class="action-panel-row">
                                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85em"><input type="checkbox" id="ps-method-bank" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer"> تحويل بنكي</label>
                                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85em"><input type="checkbox" id="ps-method-stc" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer"> STC Pay</label>
                                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85em"><input type="checkbox" id="ps-method-stars" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer"> دفع بالنجوم</label>
                            </div>
                        </div>
                        <div class="action-panel-btns">
                            <button class="action-btn action-btn-primary" id="pay-settings-save-btn" onclick="confirmSavePaymentSettings()">💾 حفظ الإعدادات</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modal -->
        <div class="modal-overlay" id="modalOverlay">
            <div class="modal-box">
                <div class="modal-header">
                    <h2 id="modal-title">تفاصيل</h2>
                    <button class="modal-close" onclick="closeModal()">&times;</button>
                </div>
                <div class="modal-body" id="modal-body"></div>
            </div>
        </div>

        <!-- WebSocket Status -->
        <div class="ws-status ws-connected" id="ws-status">
            <span class="status-dot status-online"></span> متصل
        </div>
    </div>

    <script>
    /* ===== Global State ===== */
    let sourcesChart = null, activityChart = null;
    let allUsers = [], allQuestions = [];
    let ws = null, wsRetries = 0;
    let wsGotData = false;
    const MAX_RETRIES = 10;
    const startTime = Date.now();

    /* ===== Escape HTML (XSS protection) ===== */
    function esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    }

    /* ===== WebSocket ===== */
    let restPollTimer = null;
    let restFallbackStarted = false;

    function startRestFallback() {
        if (restFallbackStarted) return;
        restFallbackStarted = true;
        const tick = async () => {
            try {
                const res = await fetch('/api/live');
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.stats) updateDashboard(data);
                    const st = document.getElementById('ws-status');
                    if (st) { st.className = 'ws-status ws-connected'; st.innerHTML = '<span class="status-dot status-online"></span> متصل (REST)'; }
                }
            } catch(err) { /* أعد المحاولة في الدورة القادمة */ }
        };
        tick();
        restPollTimer = setInterval(tick, 3000);
    }

    function stopRestFallback() {
        if (restPollTimer) { clearInterval(restPollTimer); restPollTimer = null; }
    }

    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${proto}//${location.host}/ws`);
        // إذا لم تصل بيانات ws خلال 6 ثوانٍ → نبدأ الـ REST fallback
        const fallbackTimer = setTimeout(() => { if (!wsGotData) startRestFallback(); }, 6000);

        ws.onopen = () => {
            wsRetries = 0;
            document.getElementById('ws-status').className = 'ws-status ws-connected';
            document.getElementById('ws-status').innerHTML = '<span class="status-dot status-online"></span> متصل';
        };

        ws.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                wsGotData = true;
                clearTimeout(fallbackTimer);
                stopRestFallback();
                updateDashboard(data);
            } catch(err) { console.error('Parse error:', err); }
        };

        ws.onerror = () => {
            document.getElementById('ws-status').className = 'ws-status ws-disconnected';
            document.getElementById('ws-status').innerHTML = '<span class="status-dot status-offline"></span> انقطع الاتصال';
        };

        ws.onclose = (ev) => {
            document.getElementById('ws-status').className = 'ws-status ws-disconnected';
            if (ev && ev.code === 1008) {
                // الجلسة غير صالحة — لا نعيد المحاولة
                wsRetries = MAX_RETRIES;
                document.getElementById('ws-status').innerHTML = '<span class="status-dot status-offline"></span> انتهت الجلسة — أعد تسجيل الدخول';
                setTimeout(() => { location.href = '/'; }, 1500);
                return;
            }
            document.getElementById('ws-status').innerHTML = '<span class="status-dot status-offline"></span> إعادة الاتصال...';
            if (wsRetries < MAX_RETRIES) {
                wsRetries++;
                setTimeout(connectWS, Math.min(1000 * Math.pow(2, wsRetries), 30000));
            }
        };
    }
    connectWS();

    /* ===== Dashboard Update ===== */
    function updateDashboard(data) {
        updateStats(data.stats);
        updateCharts(data);
        updateUsersTable(data.users);
        updateActiveUsers(data.active_users);
        updateQuestions(data.recent_questions);
        updateErrors(data.recent_errors);
        updateSubscriptions(data.subscriptions);
        updateAPIStats(data.api_stats);
    }

    /* ===== Stats Cards ===== */
    function updateStats(stats) {
        const grid = document.getElementById('stats-grid');
        const cards = [
            { t:'👥 إجمالي المستخدمين', v:stats.total_users, c:'#3b82f6', d:'all-users' },
            { t:'🟢 نشطين الآن', v:stats.active_now, c:'#10b981', d:'active-now' },
            { t:'📅 نشطين اليوم', v:stats.active_today, c:'#06b6d4', d:'active-today' },
            { t:'💎 المشتركين', v:stats.subscribers, c:'#8b5cf6', d:'subscribers' },
            { t:'🎟️ خلصت مجانيهم', v:stats.finished_free, c:'#ef4444', d:'finished-free' },
            { t:'🎁 لسه مجاني', v:stats.remaining_free, c:'#f59e0b', d:'remaining-free' },
            { t:'📚 إجمالي الواجبات', v:stats.total_hw, c:'#6366f1', d:'total-hw' },
            { t:'📝 إجمالي الأسئلة', v:stats.total_questions, c:'#0ea5e9', d:'total-questions' },
            { t:'✅ إجابات صحيحة', v:stats.total_correct, c:'#10b981', d:'correct' },
            { t:'❌ إجابات خاطئة', v:stats.total_wrong, c:'#ef4444', d:'wrong' },
            { t:'💾 ضربات DB', v:stats.db_hits, c:'#059669', d:'db' },
            { t:'🦙 Groq', v:stats.groq, c:'#0ea5e9', d:'groq' },
            { t:'✨ Gemini', v:stats.gemini, c:'#f59e0b', d:'gemini' },
            { t:'🎲 عشوائي', v:stats.random, c:'#6b7280', d:'random' },
            { t:'❌ الأخطاء', v:stats.total_errors, c:'#ef4444', d:'errors' },
            { t:'💻 CPU', v:stats.cpu+'%', c:'#6366f1', d:'system' },
            { t:'📀 الذاكرة', v:stats.memory+'%', c:'#8b5cf6', d:'system' }
        ];

        grid.innerHTML = cards.map(c => `
            <div class="stat-card" onclick="openStatDetail('${c.d}')" style="border-top:3px solid ${c.c};cursor:pointer">
                <div class="title">${esc(c.t)}</div>
                <div class="value">${esc(String(c.v))}</div>
            </div>
        `).join('');

        // Uptime
        const up = Math.floor((Date.now() - startTime) / 1000);
        const h = Math.floor(up/3600), m = Math.floor((up%3600)/60), s = up%60;
        document.getElementById('uptime').textContent = `⏱️ ${h}h ${m}m ${s}s`;
    }

    /* ===== Charts ===== */
    function updateCharts(data) {
        const s = data.stats;
        const colors = ['#059669','#0ea5e9','#f59e0b','#6b7280'];

        if (!sourcesChart) {
            sourcesChart = new Chart(document.getElementById('sourcesChart'), {
                type: 'doughnut',
                data: {
                    labels: ['قاعدة البيانات','Groq','Gemini','عشوائي'],
                    datasets: [{ data:[s.db_hits,s.groq,s.gemini,s.random], backgroundColor:colors, borderWidth:0, hoverOffset:8 }]
                },
                options: {
                    responsive:true,
                    cutout:'65%',
                    plugins:{ legend:{ position:'bottom', labels:{ padding:16, usePointStyle:true, font:{size:12} } } }
                }
            });
        } else {
            sourcesChart.data.datasets[0].data = [s.db_hits,s.groq,s.gemini,s.random];
            sourcesChart.update('none');
        }

        if (!activityChart) {
            activityChart = new Chart(document.getElementById('activityChart'), {
                type: 'line',
                data: {
                    labels: data.activity_labels||[],
                    datasets: [{
                        label:'المستخدمين النشطين',
                        data: data.activity_data||[],
                        borderColor:'#3b82f6',
                        backgroundColor:'rgba(59,130,246,0.08)',
                        tension:0.4,
                        fill:true,
                        pointRadius:3,
                        pointHoverRadius:6
                    }]
                },
                options: {
                    responsive:true,
                    plugins:{ legend:{display:false} },
                    scales:{ y:{beginAtZero:true, grid:{color:'#f1f5f9'}}, x:{grid:{display:false}} }
                }
            });
        } else {
            activityChart.data.labels = data.activity_labels;
            activityChart.data.datasets[0].data = data.activity_data;
            activityChart.update('none');
        }
    }

    /* ===== Users Table ===== */
    function updateUsersTable(users) {
        allUsers = users || [];
        renderUsers(allUsers);
    }

    function renderUsers(users) {
        const body = document.getElementById('users-body');
        if (!users.length) {
            body.innerHTML = '<tr><td colspan="7"><div class="empty-state"><div class="icon">👥</div><div class="text">لا يوجد مستخدمين</div></div></td></tr>';
            return;
        }
        body.innerHTML = users.map(u => `
            <tr class="user-row" onclick="showUserDetails(${u.id})">
                <td><code>${esc(String(u.id))}</code></td>
                <td style="font-weight:500">${esc(u.name)}</td>
                <td class="hide-mobile"><code>${esc(u.platform_user||'—')}</code></td>
                <td><span class="badge ${u.is_subscribed?'badge-success':'badge-danger'}">${u.is_subscribed?'مشترك':'غير مشترك'}</span></td>
                <td class="hide-mobile">${esc(u.last_active||'—')}</td>
                <td class="hide-mobile">${u.total_hw||0}</td>
                <td>${u.is_online?'<span class="badge badge-success">🟢 نشيط</span>':'<span class="badge badge-outline">⚫ غير نشيط</span>'}</td>
            </tr>
        `).join('');
    }

    function filterUsers() {
        const search = document.getElementById('userSearch').value.toLowerCase();
        const filter = document.getElementById('userFilter').value;
        let filtered = allUsers;

        if (search) {
            filtered = filtered.filter(u =>
                (u.name||'').toLowerCase().includes(search) ||
                String(u.id).includes(search) ||
                (u.platform_user||'').toLowerCase().includes(search)
            );
        }
        if (filter === 'active') filtered = filtered.filter(u => u.is_online);
        if (filter === 'vip') filtered = filtered.filter(u => u.is_subscribed);

        renderUsers(filtered);
    }

    /* ===== Active Users ===== */
    function updateActiveUsers(users) {
        const body = document.getElementById('active-users-body');
        if (!users || !users.length) {
            body.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">😴</div><div class="text">لا يوجد مستخدمين نشطين</div></div></td></tr>';
            return;
        }
        body.innerHTML = users.map(u => `
            <tr>
                <td><b>${esc(u.name)}</b> <code>${esc(String(u.id))}</code></td>
                <td><span class="badge badge-${u.status_class==='success'?'success':u.status_class==='warning'?'warning':'info'}">${esc(u.status)}</span></td>
                <td class="hide-mobile">${esc(u.current_action)}</td>
                <td><button onclick="showUserDetails(${u.id})" class="badge badge-primary" style="cursor:pointer">عرض</button></td>
            </tr>
        `).join('');
    }

    /* ===== Questions ===== */
    function updateQuestions(questions) {
        allQuestions = questions || [];
        renderQuestions(allQuestions);
    }

    function renderQuestions(questions) {
        const list = document.getElementById('questions-list');
        if (!questions.length) {
            list.innerHTML = '<div class="empty-state"><div class="icon">📝</div><div class="text">لا توجد أسئلة</div></div>';
            return;
        }
        list.innerHTML = questions.map(q => {
            let sc='', st='';
            switch(q.source){
                case 'db': sc='source-db'; st='💾 قاعدة البيانات'; break;
                case 'groq': sc='source-groq'; st='🦙 Groq'; break;
                case 'gemini': sc='source-gemini'; st='✨ Gemini'; break;
                default: sc='source-random'; st='🎲 عشوائي';
            }
            return `
                <div class="card-item">
                    <div class="card-item-header">
                        <div class="card-item-title">${esc(q.text)}</div>
                        <span class="question-source ${sc}">${st}</span>
                    </div>
                    <div class="card-item-body">
                        <div><span class="label">👤 المستخدم:</span></div><div class="val">${esc(q.user)}</div>
                        <div><span class="label">📚 المادة:</span></div><div class="val">${esc(q.subject)}</div>
                        <div><span class="label">⏱️ الوقت:</span></div><div class="val">${esc(q.time)}</div>
                    </div>
                </div>
            `;
        }).join('');
    }

    function filterQuestions() {
        const filter = document.getElementById('questionFilter').value;
        if (filter === 'all') { renderQuestions(allQuestions); return; }
        renderQuestions(allQuestions.filter(q => q.source === filter));
    }

    /* ===== Errors ===== */
    function updateErrors(errors) {
        const body = document.getElementById('errors-body');
        if (!errors || !errors.length) {
            body.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">✅</div><div class="text">لا توجد أخطاء — كل شيء يعمل!</div></div></td></tr>';
            return;
        }
        body.innerHTML = errors.map(e => `
            <tr>
                <td>${esc(e.time)}</td>
                <td><code>${esc(String(e.user_id))}</code></td>
                <td class="hide-mobile">${esc(e.event)}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(e.message)}">${esc(e.message)}</td>
            </tr>
        `).join('');
    }

    /* ===== Subscriptions ===== */
    function updateSubscriptions(subs) {
        const body = document.getElementById('subscriptions-body');
        if (!subs || !subs.length) {
            body.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">💎</div><div class="text">لا يوجد مشتركين</div></div></td></tr>';
            return;
        }
        body.innerHTML = subs.map(s => `
            <tr>
                <td><b>${esc(s.name)}</b> <code>${esc(String(s.id))}</code></td>
                <td>${esc(s.expiry)}</td>
                <td><span class="badge ${s.days_left>7?'badge-success':s.days_left>3?'badge-warning':'badge-danger'}">${s.days_left} يوم</span></td>
                <td class="hide-mobile">${s.total_hw}</td>
            </tr>
        `).join('');
    }

    /* ===== API Stats ===== */
    function updateAPIStats(stats) {
        const ids = ['groq','gemini','db','random'];
        const vals = [stats.groq, stats.gemini, stats.db_hits, stats.random];
        const total = vals.reduce((a,b)=>a+b,0) || 1;
        ids.forEach((id,i) => {
            document.getElementById(id+'-value').textContent = vals[i];
            document.getElementById(id+'-percent').textContent = Math.round(vals[i]/total*100)+'%';
        });
    }

    /* ===== Tabs ===== */
    function showTab(name, btn) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        else document.querySelector(`[data-tab="${name}"]`)?.classList.add('active');
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        document.getElementById('tab-'+name)?.classList.add('active');
        if (name === 'payments') loadPaymentRequests();
        if (name === 'settings') loadPaymentSettings();
        if (name === 'messaging') loadMessaging();
        if (name === 'support') loadSupportConversations();
        if (name === 'control') loadControlStatus();
        if (name === 'admins') loadAdmins();
        if (name === 'resellers') loadResellers();
        if (name === 'logs') {
            loadLogFiles(); loadLogFile();
            const chk = document.getElementById('logsAutoRefresh');
            if (chk && chk.checked) startLogsPoll();
        }
        if (name !== 'logs') stopLogsPoll();
    }

    /* ===== Modal ===== */
    function openModal(title, html) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = html;
        document.getElementById('modalOverlay').classList.add('show');
    }
    function closeModal() {
        document.getElementById('modalOverlay').classList.remove('show');
    }
    document.getElementById('modalOverlay').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

    /* ===== Stat Card Detail — كل بطاقة قابلة للضغط ===== */
    async function openStatDetail(type) {
        // db و groq لهم عرض خاص
        if (type === 'db') return showDBDetails();
        if (type === 'groq') return showGroqDetails();

        try {
            const res = await fetch(`/api/detail/${type}`);
            const data = await res.json();
            if (data.error) { showToast('⚠️ ' + data.error, 'error'); return; }
            renderDetailModal(data);
        } catch(err) {
            showToast('⚠️ خطأ في تحميل البيانات', 'error');
        }
    }

    function renderDetailModal(data) {
        const items = Array.isArray(data.data) ? data.data : [];
        let html = `<div style="margin-bottom:16px;color:var(--text-muted);font-size:0.9em">العدد: <b style="color:var(--text)">${data.count}</b></div>`;

        // نظام المعلومات
        if (data.type === 'system' && !Array.isArray(data.data)) {
            const s = data.data;
            html = `<div class="info-grid">
                <div class="info-item"><div class="label">المعالج</div><div class="value">${s.cpu_percent||0}%</div></div>
                <div class="info-item"><div class="label">أنوية</div><div class="value">${s.cpu_cores||'—'}</div></div>
                <div class="info-item"><div class="label">الذاكرة</div><div class="value">${s.mem_percent||0}%</div></div>
                <div class="info-item"><div class="label">ذاكرة مستخدمة</div><div class="value">${s.mem_used_gb||0} / ${s.mem_total_gb||0} GB</div></div>
                <div class="info-item"><div class="label">القرص</div><div class="value">${s.disk_percent||0}%</div></div>
                <div class="info-item"><div class="label">قرص مستخدم</div><div class="value">${s.disk_used_gb||0} / ${s.disk_total_gb||0} GB</div></div>
                <div class="info-item"><div class="label">جلسات نشطة</div><div class="value">${s.active_sessions||0}</div></div>
            </div>`;
            openModal(data.title, html);
            return;
        }

        if (items.length === 0) {
            html += '<div class="empty-state"><div class="icon">📭</div><div class="text">لا توجد بيانات</div></div>';
            openModal(data.title, html);
            return;
        }

        // جدول المستخدمين (all-users)
        if (data.type === 'users') {
            html += '<div class="table-wrap"><table><thead><tr><th>ID</th><th>الاسم</th><th>المنصة</th><th>الاشتراك</th><th>مجاني</th><th>واجبات</th><th>آخر نشاط</th></tr></thead><tbody>';
            items.forEach(u => {
                html += `<tr class="user-row" onclick="closeModal();showUserDetails(${u.id})">
                    <td><code>${u.id}</code></td><td style="font-weight:600">${esc(u.name)}</td>
                    <td><code>${esc(u.platform)}</code></td>
                    <td><span class="badge ${u.subscribed?'badge-success':'badge-danger'}">${u.subscribed?'مشترك':'غير مشترك'}</span></td>
                    <td>${u.free}</td><td>${u.hw}</td><td>${esc(u.last_active||'—')}</td>
                </tr>`;
            });
            html += '</tbody></table></div>';
        }

        // جدول المشتركين
        else if (data.type === 'subscribers') {
            html += '<div class="table-wrap"><table><thead><tr><th>ID</th><th>الاسم</th><th>الانتهاء</th><th>الأيام</th><th>واجبات</th></tr></thead><tbody>';
            items.forEach(s => {
                const cls = s.days_left <= 3 ? 'badge-danger' : s.days_left <= 7 ? 'badge-warning' : 'badge-success';
                html += `<tr><td><code>${s.id}</code></td><td style="font-weight:600">${esc(s.name)}</td>
                    <td>${esc(s.expiry)}</td><td><span class="badge ${cls}">${s.days_left} يوم</span></td><td>${s.hw}</td></tr>`;
            });
            html += '</tbody></table></div>';
        }

        // جدول الواجبات
        else if (data.type === 'homeworks') {
            html += '<div class="table-wrap"><table><thead><tr><th>المستخدم</th><th>المادة</th><th>الأسئلة</th><th>صحيح</th><th>خطأ</th><th>النسبة</th><th>المدة</th></tr></thead><tbody>';
            items.forEach(h => {
                const cls = h.pct >= 80 ? 'badge-success' : h.pct >= 50 ? 'badge-warning' : 'badge-danger';
                html += `<tr><td style="font-weight:600">${esc(h.user)}</td><td>${esc(h.subject)}</td>
                    <td>${h.total}</td><td style="color:var(--success)">${h.correct}</td>
                    <td style="color:var(--error)">${h.wrong}</td>
                    <td><span class="badge ${cls}">${h.pct}%</span></td><td>${esc(h.duration||'—')}</td></tr>`;
            });
            html += '</tbody></table></div>';
        }

        // الأسئلة (questions, total-questions, correct, wrong, gemini, random)
        else if (data.type === 'questions') {
            const sourceMap = {db:{cls:'source-db',t:'💾 DB'},groq:{cls:'source-groq',t:'🦙 Groq'},gemini:{cls:'source-gemini',t:'✨ Gemini'},random:{cls:'source-random',t:'🎲 عشوائي'}};
            html += '<div class="card-list">';
            items.forEach(q => {
                const src = sourceMap[q.source] || sourceMap.db;
                html += `<div class="question-item">
                    <div class="q-header"><span class="q-text">${esc(q.question||q.text||'—')}</span>
                    ${q.source?`<span class="source-tag ${src.cls}">${src.t}</span>`:''}</div>
                    <div class="q-meta"><span>👤 ${esc(q.user)}</span><span>📚 ${esc(q.subject)}</span>${q.time?`<span>⏱️ ${esc(q.time)}</span>`:''}</div>
                </div>`;
            });
            html += '</div>';
        }

        // الأخطاء
        else if (data.type === 'errors') {
            html += '<div class="table-wrap"><table><thead><tr><th>الوقت</th><th>المستخدم</th><th>الحدث</th><th>الخطأ</th></tr></thead><tbody>';
            items.forEach(e => {
                html += `<tr><td style="font-family:monospace;font-size:0.82em">${esc(e.time)}</td>
                    <td><code>${e.user_id}</code></td><td>${esc(e.event)}</td>
                    <td style="color:var(--error)">${esc(e.message)}</td></tr>`;
            });
            html += '</tbody></table></div>';
        }

        // جدول عام (active-now, active-today, finished-free, remaining-free, correct, wrong)
        else {
            const cols = Object.keys(items[0]||{});
            const labels = {id:'ID',name:'الاسم',username:'اليوزر',last_active:'آخر نشاط',in_session:'الجلسة',free:'مجاني',hw:'واجبات',subject:'المادة',correct:'صحيح',wrong:'خطأ',total:'الأسئلة',subscribed:'مشترك',days_left:'الأيام',expiry:'الانتهاء'};
            html += '<div class="table-wrap"><table><thead><tr>';
            cols.forEach(c => { html += `<th>${labels[c]||c}</th>`; });
            html += '</tr></thead><tbody>';
            items.forEach(row => {
                html += '<tr>';
                cols.forEach(c => {
                    let v = row[c];
                    if (c==='id') v = `<code>${v}</code>`;
                    else if (c==='name') v = `<span style="font-weight:600">${esc(String(v))}</span>`;
                    else if (c==='in_session') v = v ? '<span class="badge badge-success">في جلسة</span>' : '<span class="badge badge-info">متصل</span>';
                    else if (c==='subscribed') v = v ? '<span class="badge badge-success">نعم</span>' : '<span class="badge badge-danger">لا</span>';
                    html += `<td>${v??'—'}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table></div>';
        }

        openModal(data.title, html);
    }

    /* ===== User Details Modal ===== */
    async function showUserDetails(userId) {
        try {
            const res = await fetch(`/api/user/${userId}`);
            if (!res.ok) throw new Error('Failed');
            const u = await res.json();
            currentUserDetail = u;

            const html = `
                <div class="info-grid">
                    <div class="info-item"><div class="label">المعرف</div><div class="value"><code>${esc(String(u.id))}</code></div></div>
                    <div class="info-item"><div class="label">الاسم</div><div class="value">${esc(u.name)}</div></div>
                    <div class="info-item"><div class="label">يوزر المنصة</div><div class="value"><code>${esc(u.platform_user||'—')}</code></div></div>
                    <div class="info-item"><div class="label">كلمة المرور</div><div class="value"><span class="password-field">${u.has_password?'🔒 مخفية':'—'}</span></div></div>
                    <div class="info-item"><div class="label">الاشتراك</div><div class="value"><span class="badge ${u.is_subscribed?'badge-success':'badge-danger'}">${u.is_subscribed?'✅ مشترك':'❌ غير مشترك'}</span></div></div>
                    <div class="info-item"><div class="label">تاريخ الانتهاء</div><div class="value">${esc(u.expiry||'—')}</div></div>
                    <div class="info-item"><div class="label">المحاولات المجانية</div><div class="value">${u.attempts||0}</div></div>
                    <div class="info-item"><div class="label">الواجبات المحلولة</div><div class="value">${u.total_hw||0}</div></div>
                    <div class="info-item"><div class="label">الأسئلة</div><div class="value">${u.total_questions||0}</div></div>
                    <div class="info-item"><div class="label">آخر نشاط</div><div class="value">${esc(u.last_active||'—')}</div></div>
                </div>
                <h3 style="margin-bottom:12px;font-size:1em;color:var(--text)">🛠️ إجراءات</h3>
                <div class="user-actions" id="user-action-btns">
                    <button class="action-btn action-btn-primary" data-act="renew" onclick="showRenewPanel()">➕ تجديد</button>
                    <button class="action-btn action-btn-danger" data-act="revoke" onclick="revokeUser()">🚫 إلغاء الاشتراك</button>
                    <button class="action-btn action-btn-warning" data-act="unlock" onclick="unlockUser()">🔓 فك القفل</button>
                    <button class="action-btn action-btn-info" data-act="homework" onclick="showHomeworkPanel()">📝 إضافة واجبات</button>
                    <button class="action-btn action-btn-danger" data-act="delete" onclick="showDeleteUserConfirm()">🗑️ حذف المستخدم</button>
                </div>
                <div id="user-action-msg"></div>
                <div id="user-action-panel"></div>
                <h3 style="margin-bottom:12px;font-size:1em;color:var(--text)">📋 آخر النشاطات</h3>
                <div class="activity-feed">
                    ${(u.recent_activities||[]).map(a => `
                        <div class="activity-item">
                            <div class="activity-time">${esc(a.time)}</div>
                            <div class="activity-icon icon-${a.type}">${a.icon}</div>
                            <div>${esc(a.description)}</div>
                        </div>
                    `).join('') || '<div class="empty-state"><div class="text">لا توجد نشاطات</div></div>'}
                </div>
            `;
            openModal(`تفاصيل المستخدم — ${esc(u.name)}`, html);
        } catch(err) {
            openModal('خطأ', '<div class="empty-state"><div class="icon">⚠️</div><div class="text">فشل جلب البيانات</div></div>');
        }
    }

    /* ===== DB Details Modal ===== */
    async function showDBDetails() {
        try {
            const res = await fetch('/api/db-questions');
            const qs = await res.json();
            let html = '';
            if (!qs.length) {
                html = '<div class="empty-state"><div class="icon">💾</div><div class="text">لا توجد أسئلة من قاعدة البيانات</div></div>';
            } else {
                html = '<div class="card-list">' + qs.map(q => `
                    <div class="card-item" style="border-right:4px solid #059669">
                        <div class="card-item-header">
                            <div class="card-item-title">👤 ${esc(q.user)}</div>
                            <span class="badge badge-success">📚 ${esc(q.subject)}</span>
                        </div>
                        <div style="background:#f8fafc;padding:10px;border-radius:8px;margin-bottom:8px;font-size:0.9em">${esc(q.question)}</div>
                        <div style="color:var(--text-muted);font-size:0.78em">🆔 ${esc(String(q.user_id))} · ⏱️ ${esc(q.time)}</div>
                    </div>
                `).join('') + '</div>';
            }
            openModal(`💾 ضربات قاعدة البيانات (${qs.length})`, html);
        } catch(err) {
            openModal('خطأ', '<div class="empty-state"><div class="text">فشل جلب البيانات</div></div>');
        }
    }

    /* ===== Groq Details Modal ===== */
    async function showGroqDetails() {
        try {
            const res = await fetch('/api/groq-questions');
            const qs = await res.json();
            let html = '';
            if (!qs.length) {
                html = '<div class="empty-state"><div class="icon">🦙</div><div class="text">لا توجد أسئلة من Groq</div></div>';
            } else {
                html = '<div class="card-list">' + qs.map(q => `
                    <div class="card-item" style="border-right:4px solid #0ea5e9">
                        <div class="card-item-header">
                            <div class="card-item-title">👤 ${esc(q.user)}</div>
                            <span class="badge badge-info">📚 ${esc(q.subject)}</span>
                        </div>
                        <div style="background:#f8fafc;padding:10px;border-radius:8px;margin-bottom:8px;font-size:0.9em">${esc(q.question)}</div>
                        <div style="color:var(--text-muted);font-size:0.78em">🆔 ${esc(String(q.user_id))} · ⏱️ ${esc(q.time)}</div>
                    </div>
                `).join('') + '</div>';
            }
            openModal(`🦙 أسئلة Groq (${qs.length})`, html);
        } catch(err) {
            openModal('خطأ', '<div class="empty-state"><div class="text">فشل جلب البيانات</div></div>');
        }
    }

    /* ===== Toast ===== */
    function showToast(text, type) {
        let toast = document.getElementById('global-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'global-toast';
            document.body.appendChild(toast);
        }
        toast.className = 'toast ' + (type === 'error' ? 'toast-error' : 'toast-success');
        toast.textContent = text;
        toast.style.opacity = '1';
        clearTimeout(toast._t);
        toast._t = setTimeout(() => { toast.style.opacity = '0'; }, 3500);
    }

    /* ===== Payment Requests ===== */
    async function loadPaymentRequests() {
        setPaymentsMsg('⏳ جاري تحميل طلبات الدفع...', false);
        try {
            const res = await fetch('/api/admin/payment-requests');
            const data = await res.json();
            if (data.error || data.message) {
                setPaymentsMsg('⚠️ ' + (data.message || data.error), true);
                document.getElementById('payments-body').innerHTML = '';
                return;
            }
            renderPaymentRequests(data.requests || []);
            if ((data.requests || []).length) setPaymentsMsg('', false);
        } catch(err) {
            setPaymentsMsg('⚠️ فشل تحميل طلبات الدفع', true);
            document.getElementById('payments-body').innerHTML = '';
        }
    }

    function setPaymentsMsg(text, isError) {
        const el = document.getElementById('payments-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    function renderPaymentRequests(requests) {
        const body = document.getElementById('payments-body');
        if (!requests.length) {
            body.innerHTML = '<tr><td colspan="8"><div class="empty-state"><div class="icon">💳</div><div class="text">لا توجد طلبات دفع</div></div></td></tr>';
            return;
        }
        // الأحدث أولاً
        const sorted = requests.slice().sort((a, b) => (b.id || 0) - (a.id || 0));
        body.innerHTML = sorted.map(r => {
            const pending = r.status === 'pending';
            const statusCls = r.status === 'approved' ? 'badge-success' : r.status === 'rejected' ? 'badge-danger' : 'badge-warning';
            const statusTxt = r.status === 'approved' ? '✅ مفعل' : r.status === 'rejected' ? '❌ مرفوض' : '⏳ قيد الانتظار';
            return `
                <tr class="${pending ? '' : 'payment-done'}">
                    <td style="font-weight:600">${esc(r.user_name)}</td>
                    <td>${esc(r.plan_name||'—')}</td>
                    <td>${esc(r.price||'—')}</td>
                    <td>${esc(r.payment_method||'—')}</td>
                    <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.note||'')}">${esc(r.note||'—')}</td>
                    <td>${esc(r.created_at||'—')}</td>
                    <td><span class="badge ${statusCls}">${statusTxt}</span></td>
                    <td>${pending ? `
                        <button class="action-btn action-btn-primary" onclick="showActivatePanel(${r.id})">تفعيل</button>
                        <button class="action-btn action-btn-danger" onclick="showRejectPanel(${r.id})">رفض</button>` : `<span style="color:var(--text-muted);font-size:0.8em">${esc(r.processed_at||'—')}</span>`}
                    </td>
                </tr>`;
        }).join('');
    }

    let paymentTarget = null;
    let activateDaysVal = 7;

    function showActivatePanel(rid) {
        paymentTarget = rid;
        const p = document.getElementById('payments-panel');
        p.innerHTML = `
            <div class="action-panel">
                <div class="action-panel-title">✅ تفعيل الطلب #${rid} — اختر مدة الاشتراك</div>
                <div class="day-choices">
                    <button class="day-choice active" onclick="pickActivateDays(this,7)">7 أيام</button>
                    <button class="day-choice" onclick="pickActivateDays(this,30)">30 يوم</button>
                    <button class="day-choice" onclick="pickActivateDays(this,90)">90 يوم</button>
                    <button class="day-choice" onclick="pickActivateDays(this,0)">مخصص</button>
                    <input type="number" id="activate-custom-days" class="day-custom" min="1" placeholder="عدد الأيام" style="display:none">
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="activate-confirm-btn" onclick="confirmActivatePayment()">تأكيد التفعيل</button>
                    <button class="action-btn action-btn-ghost" onclick="closePaymentPanel()">إلغاء</button>
                </div>
            </div>`;
        p.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function pickActivateDays(btn, days) {
        document.querySelectorAll('#payments-panel .day-choice').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const custom = document.getElementById('activate-custom-days');
        if (days === 0) {
            custom.style.display = '';
            activateDaysVal = null;
        } else {
            custom.style.display = 'none';
            activateDaysVal = days;
        }
    }

    async function confirmActivatePayment() {
        let days = activateDaysVal;
        if (days === null) {
            days = parseInt(document.getElementById('activate-custom-days').value, 10);
            if (!days || days <= 0) { setPaymentsMsg('⚠️ أدخل عدد أيام صالح', true); return; }
        }
        const btn = document.getElementById('activate-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch(`/api/admin/payment-requests/${paymentTarget}/activate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ days })
            });
            const data = await res.json();
            if (data.success === false) {
                setPaymentsMsg('⚠️ ' + (data.message || 'فشل التفعيل'), true);
                btn.disabled = false;
                btn.textContent = 'تأكيد التفعيل';
                return;
            }
            setPaymentsMsg('✅ ' + (data.message || 'تم تفعيل الطلب'), false);
            closePaymentPanel();
            loadPaymentRequests();
        } catch(err) {
            setPaymentsMsg('⚠️ فشل الاتصال بالخادم', true);
            btn.disabled = false;
            btn.textContent = 'تأكيد التفعيل';
        }
    }

    let rejectReasonVal = null;

    function showRejectPanel(rid) {
        paymentTarget = rid;
        const p = document.getElementById('payments-panel');
        p.innerHTML = `
            <div class="action-panel action-panel-danger">
                <div class="action-panel-title">⛔ رفض الطلب #${rid} — اختر السبب</div>
                <div class="day-choices">
                    <button class="day-choice" onclick="pickRejectReason(this,'بيانات غير صحيحة')">بيانات غير صحيحة</button>
                    <button class="day-choice" onclick="pickRejectReason(this,'مبلغ غير مطابق')">مبلغ غير مطابق</button>
                    <button class="day-choice" onclick="pickRejectReason(this,'الطلب مكرر')">الطلب مكرر</button>
                    <button class="day-choice" onclick="pickRejectReason(this,'')">مخصص</button>
                    <input type="text" id="reject-custom-reason" class="day-custom" placeholder="اكتب السبب..." style="display:none">
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="reject-confirm-btn" onclick="confirmRejectPayment()">تأكيد الرفض</button>
                    <button class="action-btn action-btn-ghost" onclick="closePaymentPanel()">إلغاء</button>
                </div>
            </div>`;
        p.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function pickRejectReason(btn, reason) {
        document.querySelectorAll('#payments-panel .day-choice').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const custom = document.getElementById('reject-custom-reason');
        if (reason === '') {
            custom.style.display = '';
            rejectReasonVal = null;
        } else {
            custom.style.display = 'none';
            rejectReasonVal = reason;
        }
    }

    async function confirmRejectPayment() {
        let reason = rejectReasonVal;
        if (reason === null) {
            reason = document.getElementById('reject-custom-reason').value.trim();
            if (!reason) { setPaymentsMsg('⚠️ اكتب سبب الرفض', true); return; }
        }
        const btn = document.getElementById('reject-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch(`/api/admin/payment-requests/${paymentTarget}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            const data = await res.json();
            if (data.success === false) {
                setPaymentsMsg('⚠️ ' + (data.message || 'فشل الرفض'), true);
                btn.disabled = false;
                btn.textContent = 'تأكيد الرفض';
                return;
            }
            setPaymentsMsg('✅ ' + (data.message || 'تم رفض الطلب'), false);
            closePaymentPanel();
            loadPaymentRequests();
        } catch(err) {
            setPaymentsMsg('⚠️ فشل الاتصال بالخادم', true);
            btn.disabled = false;
            btn.textContent = 'تأكيد الرفض';
        }
    }

    function closePaymentPanel() {
        document.getElementById('payments-panel').innerHTML = '';
    }

    /* ===== Messaging: Broadcast + Announcements ===== */
    let broadcastCount = 0;
    let announcementsData = [];
    const messagingPollTimers = {};

    function setMessagingMsg(text, isError) {
        const el = document.getElementById('messaging-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    function loadMessaging() {
        loadBroadcastPreview();
        loadAnnouncements();
    }

    async function loadBroadcastPreview() {
        const v = document.getElementById('broadcast-target').value;
        const box = document.getElementById('broadcast-preview');
        box.innerHTML = '<span style="color:var(--text-muted);font-size:0.85em">⏳ جاري حساب المستهدفين...</span>';
        try {
            const res = await fetch('/api/admin/broadcast/preview?target=' + encodeURIComponent(v));
            const data = await res.json();
            if (data.success === false || data.error) {
                box.innerHTML = '<span class="action-msg action-msg-error" style="display:inline-block">⚠️ ' + esc(data.message || data.error) + '</span>';
                broadcastCount = 0;
                return;
            }
            broadcastCount = data.count || 0;
            const names = (data.sample || []).map(n => esc(n)).join('، ');
            box.innerHTML = '<div style="font-weight:600;margin-bottom:4px">👥 عدد المستهدفين: <b>' + broadcastCount + '</b></div>' +
                (names ? '<div style="color:var(--text-muted);font-size:0.82em">' + names + '</div>' : '');
        } catch(err) {
            box.innerHTML = '<span style="color:var(--text-muted);font-size:0.85em">⚠️ تعذر حساب المستهدفين</span>';
        }
    }

    function previewBroadcastMessage() {
        const text = document.getElementById('broadcast-text').value.trim();
        const box = document.getElementById('broadcast-preview-box');
        if (!text) { setMessagingMsg('⚠️ اكتب رسالة البث أولاً', true); return; }
        box.style.display = '';
        box.innerHTML = '<div class="action-panel">' +
            '<div class="action-panel-title">👁️ معاينة الرسالة (ستُرسل كما هي)</div>' +
            '<div style="background:var(--surface);border:1px dashed var(--primary-light);border-radius:var(--radius-sm);padding:12px">' + text + '</div>' +
            '</div>';
    }

    async function confirmBroadcastSend() {
        const text = document.getElementById('broadcast-text').value.trim();
        if (!text) { setMessagingMsg('⚠️ اكتب رسالة البث أولاً', true); return; }
        const sel = document.getElementById('broadcast-target');
        const targetName = sel.options[sel.selectedIndex].text;
        openModal('⏳ جاري التحضير...', '<div class="empty-state"><div class="text">جاري حساب عدد المستهدفين...</div></div>');
        await loadBroadcastPreview();
        openModal('📤 تأكيد إرسال البث', `
            <div class="action-panel">
                <div class="action-panel-title">📌 الفئة: ${esc(targetName)}</div>
                <div>👥 عدد المستهدفين: <b>${broadcastCount}</b></div>
            </div>
            <div class="action-panel">
                <div class="action-panel-title">💬 نص الرسالة</div>
                <div style="background:var(--surface);border:1px dashed var(--primary-light);border-radius:var(--radius-sm);padding:12px">${text}</div>
            </div>
            <div class="action-panel-btns">
                <button class="action-btn action-btn-primary" id="broadcast-confirm-btn" onclick="sendBroadcast()">تأكيد الإرسال</button>
                <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
            </div>
        `);
    }

    async function sendBroadcast() {
        const btn = document.getElementById('broadcast-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري الإرسال...';
        try {
            const res = await fetch('/api/admin/broadcast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: document.getElementById('broadcast-target').value, text: document.getElementById('broadcast-text').value.trim(), confirm: true })
            });
            const data = await res.json();
            if (data.success === false || data.error) {
                setMessagingMsg('⚠️ ' + (data.message || data.error || 'فشل إرسال البث'), true);
                btn.disabled = false;
                btn.textContent = 'تأكيد الإرسال';
                return;
            }
            closeModal();
            showBroadcastProgress(data.job_id);
        } catch(err) {
            setMessagingMsg('⚠️ فشل الاتصال بالخادم', true);
            btn.disabled = false;
            btn.textContent = 'تأكيد الإرسال';
        }
    }

    /* ===== Announcements ===== */
    async function loadAnnouncements() {
        const body = document.getElementById('announcements-body');
        if (!body) return;
        body.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="text">⏳ جاري تحميل الإعلانات...</div></div></td></tr>';
        try {
            const res = await fetch('/api/admin/announcements');
            const data = await res.json();
            if (data.success === false || data.error) {
                setMessagingMsg('⚠️ ' + (data.message || data.error), true);
                body.innerHTML = '';
                return;
            }
            announcementsData = data.templates || [];
            renderAnnouncements();
        } catch(err) {
            setMessagingMsg('⚠️ فشل تحميل الإعلانات', true);
            body.innerHTML = '';
        }
    }

    function renderAnnouncements() {
        const body = document.getElementById('announcements-body');
        if (!announcementsData.length) {
            body.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="icon">📣</div><div class="text">لا توجد إعلانات</div></div></td></tr>';
            return;
        }
        body.innerHTML = announcementsData.map(t => `
            <tr>
                <td style="font-weight:600">${esc(t.name_ar)}</td>
                <td>${esc(t.target_filter || '—')}</td>
                <td>${esc(t.schedule_time || '—')}</td>
                <td><label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85em"><input type="checkbox" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer" ${t.enabled ? 'checked' : ''} onchange="toggleAnnouncement('${esc(String(t.type))}', this.checked)"><span class="badge ${t.enabled ? 'badge-success' : 'badge-danger'}">${t.enabled ? 'مفعل' : 'معطل'}</span></label></td>
                <td>
                    <button class="action-btn action-btn-info" onclick="previewAnnouncement('${esc(String(t.type))}')">👁️ معاينة</button>
                    <button class="action-btn action-btn-warning" onclick="editAnnouncement('${esc(String(t.type))}')">✏️ تعديل</button>
                    ${t.enabled
                        ? `<button class="action-btn action-btn-primary" onclick="confirmAnnouncementSend('${esc(String(t.type))}')">📤 إرسال الآن</button>`
                        : `<button class="action-btn action-btn-primary" disabled title="فعّل القالب أولاً">📤 إرسال الآن</button>`}
                </td>
            </tr>
        `).join('');
    }

    async function toggleAnnouncement(atype, enabled) {
        try {
            const res = await fetch('/api/admin/announcements/' + encodeURIComponent(atype) + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            const data = await res.json();
            if (data.success === false || data.error) {
                setMessagingMsg('⚠️ ' + (data.message || data.error || 'فشل تحديث الحالة'), true);
            } else {
                setMessagingMsg('✅ تم تحديث الحالة', false);
            }
            loadAnnouncements();
        } catch(err) {
            setMessagingMsg('⚠️ فشل الاتصال بالخادم', true);
            loadAnnouncements();
        }
    }

    async function previewAnnouncement(atype) {
        openModal('⏳ معاينة الإعلان...', '<div class="empty-state"><div class="text">جاري التحضير...</div></div>');
        try {
            const res = await fetch('/api/admin/announcements/' + encodeURIComponent(atype) + '/preview', { method: 'POST' });
            const data = await res.json();
            if (data.success === false || data.error) {
                openModal('👁️ معاينة الإعلان', '<div class="action-msg action-msg-error" style="display:block">⚠️ ' + esc(data.message || data.error) + '</div>');
                return;
            }
            const count = data.count != null ? data.count : 0;
            const html = `
                <div class="action-panel">
                    <div class="action-panel-title">📣 ${esc(data.name_ar || atype)}</div>
                    <div>👥 عدد المستهدفين: <b>${count}</b></div>
                </div>
                <div class="action-panel">
                    <div class="action-panel-title">👁️ عينة من الرسالة (${esc(data.sample_user_name || '—')})</div>
                    <div style="background:var(--surface);border:1px dashed var(--primary-light);border-radius:var(--radius-sm);padding:12px">${esc(data.sample_rendered) || '<span style="color:var(--text-muted)">لا توجد عينة</span>'}</div>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إغلاق</button>
                </div>`;
            openModal('👁️ معاينة الإعلان', html);
        } catch(err) {
            openModal('👁️ معاينة الإعلان', '<div class="empty-state"><div class="text">فشل جلب المعاينة</div></div>');
        }
    }

    function editAnnouncement(atype) {
        const t = (announcementsData || []).find(x => String(x.type) === String(atype));
        const text = t ? (t.template_text || '') : '';
        openModal('✏️ تعديل نص الإعلان', `
            <div class="action-panel">
                <div class="action-panel-title">📣 ${esc(t ? t.name_ar : atype)}</div>
                <textarea id="announcement-edit-text" class="day-custom" style="width:100%;min-height:140px;box-sizing:border-box">${esc(text)}</textarea>
            </div>
            <div class="action-panel-btns">
                <button class="action-btn action-btn-primary" id="announcement-edit-btn" onclick="saveAnnouncementText('${esc(String(atype))}')">حفظ التعديل</button>
                <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
            </div>
        `);
    }

    async function saveAnnouncementText(atype) {
        const text = document.getElementById('announcement-edit-text').value.trim();
        if (!text) { setMessagingMsg('⚠️ اكتب نص الإعلان', true); return; }
        const btn = document.getElementById('announcement-edit-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري الحفظ...';
        try {
            const res = await fetch('/api/admin/announcements/' + encodeURIComponent(atype) + '/text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await res.json();
            if (data.success === false || data.error) {
                setMessagingMsg('⚠️ ' + (data.message || data.error || 'فشل حفظ النص'), true);
                btn.disabled = false;
                btn.textContent = 'حفظ التعديل';
                return;
            }
            setMessagingMsg('✅ تم حفظ النص', false);
            closeModal();
            loadAnnouncements();
        } catch(err) {
            setMessagingMsg('⚠️ فشل الاتصال بالخادم', true);
            btn.disabled = false;
            btn.textContent = 'حفظ التعديل';
        }
    }

    async function confirmAnnouncementSend(atype) {
        openModal('⏳ جاري التحضير...', '<div class="empty-state"><div class="text">جاري حساب المستهدفين...</div></div>');
        let count = 0;
        let nameAr = atype;
        try {
            const res = await fetch('/api/admin/announcements/' + encodeURIComponent(atype) + '/preview', { method: 'POST' });
            const data = await res.json();
            if (data.success === false || data.error) {
                openModal('📤 إرسال الإعلان', '<div class="action-msg action-msg-error" style="display:block">⚠️ ' + esc(data.message || data.error) + '</div>');
                return;
            }
            count = data.count != null ? data.count : 0;
            nameAr = data.name_ar || atype;
        } catch(err) {
            // نكمل بدون العدد
        }
        openModal('📤 تأكيد إرسال الإعلان', `
            <div class="action-panel">
                <div class="action-panel-title">📣 ${esc(nameAr)}</div>
                <div>👥 عدد المستهدفين: <b>${count}</b></div>
            </div>
            <div style="color:var(--text-muted);font-size:0.85em;margin-bottom:10px">سيتم إرسال الإعلان الآن لكل المستهدفين.</div>
            <div class="action-panel-btns">
                <button class="action-btn action-btn-primary" id="announcement-send-btn" onclick="sendAnnouncementNow('${esc(String(atype))}')">تأكيد الإرسال</button>
                <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
            </div>
        `);
    }

    async function sendAnnouncementNow(atype) {
        const btn = document.getElementById('announcement-send-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري الإرسال...';
        try {
            const res = await fetch('/api/admin/announcements/' + encodeURIComponent(atype) + '/send', { method: 'POST' });
            const data = await res.json();
            if (data.success === false || data.error) {
                setMessagingMsg('⚠️ ' + (data.message || data.error || 'فشل إرسال الإعلان'), true);
                btn.disabled = false;
                btn.textContent = 'تأكيد الإرسال';
                return;
            }
            closeModal();
            showAnnouncementProgress(data.job_id);
        } catch(err) {
            setMessagingMsg('⚠️ فشل الاتصال بالخادم', true);
            btn.disabled = false;
            btn.textContent = 'تأكيد الإرسال';
        }
    }

    /* ===== Send Job Progress (shared: broadcast + announcements) ===== */
    function pollSendJob(jobId, onProgress, onDone) {
        if (messagingPollTimers[jobId]) clearInterval(messagingPollTimers[jobId]);
        const stop = () => {
            if (messagingPollTimers[jobId]) {
                clearInterval(messagingPollTimers[jobId]);
                delete messagingPollTimers[jobId];
            }
        };
        const tick = async () => {
            let gone = false;
            try {
                const res = await fetch('/api/admin/broadcast/jobs/' + encodeURIComponent(jobId));
                if (res.status === 404) {
                    gone = true;
                } else {
                    const data = await res.json();
                    if (data && (data.success === false || data.error)) {
                        stop();
                        if (typeof onDone === 'function') onDone({ error: data.message || data.error });
                        return;
                    }
                    if (typeof onProgress === 'function') onProgress(data);
                    if (data && data.status === 'done') {
                        stop();
                        if (typeof onDone === 'function') onDone(data);
                    }
                }
                if (gone) {
                    stop();
                    if (typeof onDone === 'function') onDone({ gone: true });
                }
            } catch(err) {
                // تعثر شبكة مؤقت — نعيد المحاولة في الدورة القادمة
            }
        };
        messagingPollTimers[jobId] = setInterval(tick, 1500);
        tick();
    }

    function progressBarHtml(pct, color) {
        return '<div style="background:var(--border);border-radius:10px;height:10px;overflow:hidden;margin-bottom:8px">' +
            '<div style="background:' + (color || 'var(--primary)') + ';height:100%;width:' + pct + '%;transition:width .3s"></div></div>';
    }

    function renderJobProgress(job, box) {
        const total = job.total || 0;
        const done = (job.sent || 0) + (job.failed || 0) + (job.skipped || 0);
        const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
        box.innerHTML = '<div class="action-panel">' +
            '<div class="action-panel-title">⏳ جاري الإرسال... (' + pct + '%)</div>' +
            progressBarHtml(pct) +
            '<div style="font-size:0.85em;color:var(--text-secondary)">✅ تم: ' + (job.sent || 0) + ' · ❌ فشل: ' + (job.failed || 0) + ' · ⏭️ تم تجاوزه: ' + (job.skipped || 0) + ' · المجموع: ' + total + '</div>' +
            '</div>';
    }

    function renderJobFinal(box, job) {
        if (!job) return;
        if (job.gone) {
            box.innerHTML = '<div class="action-msg action-msg-error" style="display:block">⚠️ المهمة غير موجودة أو انتهت صلاحيتها</div>';
            return;
        }
        if (job.error) {
            box.innerHTML = '<div class="action-msg action-msg-error" style="display:block">⚠️ ' + esc(job.error) + '</div>';
            return;
        }
        const total = job.total || 0;
        const done = (job.sent || 0) + (job.failed || 0) + (job.skipped || 0);
        const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 100;
        const errs = Array.isArray(job.errors) ? job.errors : [];
        box.innerHTML = '<div class="action-panel">' +
            '<div class="action-panel-title">✅ اكتمل الإرسال</div>' +
            progressBarHtml(pct, '#10b981') +
            '<div style="font-weight:600;margin-bottom:8px">✅ نجح: ' + (job.sent || 0) + ' · ❌ فشل: ' + (job.failed || 0) + ' · ⏭️ تم تجاوزه: ' + (job.skipped || 0) + '</div>' +
            (errs.length ? '<details style="font-size:0.82em;color:var(--text-secondary)"><summary style="cursor:pointer">❌ الأخطاء (' + errs.length + ')</summary><ul style="margin:8px 0 0;padding-right:20px">' +
                errs.slice(0, 10).map(e => '<li style="margin-bottom:4px">' + esc(String(e)) + '</li>').join('') +
                (errs.length > 10 ? '<li style="color:var(--text-muted)">... و' + (errs.length - 10) + ' خطأ آخر</li>' : '') +
                '</ul></details>' : '') +
            '</div>';
    }

    function showBroadcastProgress(jobId) {
        const box = document.getElementById('broadcast-progress');
        box.style.display = '';
        box.innerHTML = '<div class="action-panel"><div class="action-panel-title">⏳ جاري إرسال البث...</div></div>';
        pollSendJob(jobId,
            (job) => renderJobProgress(job, box),
            (job) => renderJobFinal(box, job)
        );
    }

    function showAnnouncementProgress(jobId) {
        const box = document.getElementById('announcements-progress');
        box.style.display = '';
        box.innerHTML = '<div class="action-panel"><div class="action-panel-title">⏳ جاري إرسال الإعلان...</div></div>';
        pollSendJob(jobId,
            (job) => renderJobProgress(job, box),
            (job) => renderJobFinal(box, job)
        );
    }

    /* ===== User Admin Actions ===== */
    let currentUserDetail = null;

    function showUserActionMsg(text, isError) {
        const el = document.getElementById('user-action-msg');
        if (!el) return;
        el.textContent = text;
        el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
    }

    function clearUserActionPanel() {
        const p = document.getElementById('user-action-panel');
        if (p) p.innerHTML = '';
    }

    async function adminUserAction(url, payload, btn) {
        let old = '';
        if (btn) { old = btn.textContent; btn.disabled = true; btn.textContent = '⏳ جاري...'; }
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload || {})
            });
            const data = await res.json();
            if (data.success === false) {
                showUserActionMsg('⚠️ ' + (data.message || 'حدث خطأ'), true);
                showToast('⚠️ ' + (data.message || 'حدث خطأ'), 'error');
                if (btn) { btn.disabled = false; btn.textContent = old; }
                return null;
            }
            showUserActionMsg('✅ ' + (data.message || 'تم بنجاح'), false);
            showToast('✅ ' + (data.message || 'تم بنجاح'), 'success');
            return data;
        } catch(err) {
            showUserActionMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            if (btn) { btn.disabled = false; btn.textContent = old; }
            return null;
        }
    }

    let renewDaysVal = 7;

    function showRenewPanel() {
        const p = document.getElementById('user-action-panel');
        p.innerHTML = `
            <div class="action-panel">
                <div class="action-panel-title">➕ تجديد الاشتراك — ${esc(currentUserDetail.name)}</div>
                <div class="day-choices">
                    <button class="day-choice active" onclick="pickRenewDays(this,7)">7 أيام</button>
                    <button class="day-choice" onclick="pickRenewDays(this,30)">30 يوم</button>
                    <button class="day-choice" onclick="pickRenewDays(this,90)">90 يوم</button>
                    <button class="day-choice" onclick="pickRenewDays(this,0)">مخصص</button>
                    <input type="number" id="renew-custom-days" class="day-custom" min="1" placeholder="عدد الأيام" style="display:none">
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="renew-confirm-btn" onclick="confirmRenew()">تأكيد</button>
                    <button class="action-btn action-btn-ghost" onclick="clearUserActionPanel()">إلغاء</button>
                </div>
            </div>`;
    }

    function pickRenewDays(btn, days) {
        document.querySelectorAll('#user-action-panel .day-choice').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const custom = document.getElementById('renew-custom-days');
        if (days === 0) {
            custom.style.display = '';
            renewDaysVal = null;
        } else {
            custom.style.display = 'none';
            renewDaysVal = days;
        }
    }

    async function confirmRenew() {
        let days = renewDaysVal;
        if (days === null) {
            days = parseInt(document.getElementById('renew-custom-days').value, 10);
            if (!days || days <= 0) { showUserActionMsg('⚠️ أدخل عدد أيام صالح', true); return; }
        }
        const data = await adminUserAction(`/api/admin/users/${currentUserDetail.id}/renew`, { days }, document.getElementById('renew-confirm-btn'));
        if (data) { clearUserActionPanel(); closeModal(); }
    }

    async function revokeUser() {
        if (!window.confirm(`هل أنت متأكد من إلغاء اشتراك ${currentUserDetail.name}؟`)) return;
        const data = await adminUserAction(`/api/admin/users/${currentUserDetail.id}/revoke`, {}, document.querySelector('#user-action-btns [data-act="revoke"]'));
        if (data) { clearUserActionPanel(); closeModal(); }
    }

    async function unlockUser() {
        const data = await adminUserAction(`/api/admin/users/${currentUserDetail.id}/unlock`, {}, document.querySelector('#user-action-btns [data-act="unlock"]'));
        if (data) { clearUserActionPanel(); closeModal(); }
    }

    function showHomeworkPanel() {
        const p = document.getElementById('user-action-panel');
        p.innerHTML = `
            <div class="action-panel">
                <div class="action-panel-title">📝 إضافة واجبات — ${esc(currentUserDetail.name)}</div>
                <div class="action-panel-row">
                    <label>العدد: <input type="number" id="hw-count" class="day-custom" min="1" value="1"></label>
                    <label>النوع:
                        <select id="hw-kind" class="filter-select" style="padding:8px 12px">
                            <option value="free">مجاني</option>
                            <option value="sub">اشتراك</option>
                        </select>
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="hw-confirm-btn" onclick="confirmHomework()">تأكيد</button>
                    <button class="action-btn action-btn-ghost" onclick="clearUserActionPanel()">إلغاء</button>
                </div>
            </div>`;
    }

    async function confirmHomework() {
        const count = parseInt(document.getElementById('hw-count').value, 10);
        if (!count || count <= 0) { showUserActionMsg('⚠️ أدخل عدداً صحيحاً', true); return; }
        const kind = document.getElementById('hw-kind').value;
        const data = await adminUserAction(`/api/admin/users/${currentUserDetail.id}/homework`, { count, kind }, document.getElementById('hw-confirm-btn'));
        if (data) { clearUserActionPanel(); closeModal(); }
    }

    function showDeleteUserConfirm() {
        const p = document.getElementById('user-action-panel');
        p.innerHTML = `
            <div class="action-panel action-panel-danger">
                <div class="action-panel-title">🗑️ حذف المستخدم</div>
                <div class="delete-warning">⚠️ تحذير: سيتم حذف المستخدم <b>${esc(currentUserDetail.name)}</b> نهائياً مع جميع بياناته، ولا يمكن التراجع عن هذا الإجراء.</div>
                <div class="action-panel-row">
                    <label>اكتب <b>DELETE</b> لتأكيد الحذف:
                        <input type="text" id="delete-confirm-input" class="day-custom" placeholder="DELETE" oninput="toggleDeleteConfirm(this.value)">
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="delete-confirm-btn" onclick="confirmDeleteUser()" disabled>حذف نهائي</button>
                    <button class="action-btn action-btn-ghost" onclick="clearUserActionPanel()">إلغاء</button>
                </div>
            </div>`;
    }

    function toggleDeleteConfirm(val) {
        document.getElementById('delete-confirm-btn').disabled = (val !== 'DELETE');
    }

    async function confirmDeleteUser() {
        const btn = document.getElementById('delete-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch(`/api/admin/users/${currentUserDetail.id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: 'DELETE' })
            });
            const data = await res.json();
            if (data.success === false) {
                showUserActionMsg('⚠️ ' + (data.message || 'فشل الحذف'), true);
                showToast('⚠️ ' + (data.message || 'فشل الحذف'), 'error');
                btn.disabled = false;
                btn.textContent = 'حذف نهائي';
                return;
            }
            showUserActionMsg('✅ ' + (data.message || 'تم حذف المستخدم'), false);
            showToast('✅ ' + (data.message || 'تم حذف المستخدم'), 'success');
            closeModal();
        } catch(err) {
            showUserActionMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'حذف نهائي';
        }
    }

    /* ===== Support Tab ===== */
    let supportConversations = [];

    function setSupportMsg(text, isError) {
        const el = document.getElementById('support-msg');
        if (!el) return;
        if (!text) { el.style.display = 'none'; return; }
        el.style.display = 'block';
        el.textContent = text;
        el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
    }

    function fmtEpoch(ts) {
        if (ts === null || ts === undefined || ts === '') return '—';
        const n = Number(ts);
        if (Number.isFinite(n) && n > 1e8) {
            try {
                return new Date(n * 1000).toLocaleString('ar-EG', { timeZone: 'Asia/Riyadh', dateStyle: 'short', timeStyle: 'short' });
            } catch (e) { /* fallthrough */ }
        }
        return String(ts);
    }

    async function loadSupportConversations() {
        const status = document.getElementById('supportStatus').value;
        setSupportMsg('⏳ جاري تحميل المحادثات...', false);
        try {
            const res = await fetch('/api/admin/support?status=' + encodeURIComponent(status));
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                setSupportMsg('⚠️ ' + esc(data.message || data.error || 'حدث خطأ'), true);
                supportConversations = [];
                renderSupportTable();
                return;
            }
            supportConversations = data.conversations || [];
            setSupportMsg('', false);
            renderSupportTable();
        } catch (err) {
            setSupportMsg('⚠️ فشل الاتصال بالخادم', true);
            supportConversations = [];
            renderSupportTable();
        }
    }

    function filterSupportConversations() {
        renderSupportTable();
    }

    function renderSupportTable() {
        const q = (document.getElementById('supportSearch').value || '').trim().toLowerCase();
        const rows = supportConversations.filter(c => {
            if (!q) return true;
            return String(c.name || '').toLowerCase().includes(q) || String(c.user_id || '').toLowerCase().includes(q);
        });
        const tbody = document.getElementById('support-body');
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="icon">📭</div><div class="text">لا توجد محادثات</div></div></td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(c => {
            const open = c.status === 'open';
            const dir = c.last_direction === 'admin' ? '🛡️ إدارة' : '👤 مستخدم';
            const msgs = (c.msg_count || 0) + (c.reply_count || 0);
            return `
            <tr class="user-row" onclick="showSupportConversation(${esc(String(c.user_id))})">
                <td style="font-weight:600">${esc(c.name || '—')}</td>
                <td><code>${esc(String(c.user_id))}</code></td>
                <td class="hide-mobile">${esc(fmtEpoch(c.last_activity_ts))}</td>
                <td class="hide-mobile">${dir}</td>
                <td class="hide-mobile">${esc(String(msgs))}</td>
                <td><span class="badge ${open ? 'badge-warning' : 'badge-success'}">${open ? 'مفتوحة' : 'مغلقة'}</span></td>
            </tr>`;
        }).join('');
    }

    let currentSupportUserId = null;

    async function showSupportConversation(userId) {
        currentSupportUserId = userId;
        openModal('🛟 محادثة الدعم', '<div class="empty-state"><div class="icon">⏳</div><div class="text">جاري التحميل...</div></div>');
        try {
            const res = await fetch('/api/admin/support/' + encodeURIComponent(userId));
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                openModal('🛟 محادثة الدعم', '<div class="action-msg action-msg-error" style="display:block">⚠️ ' + esc(data.message || data.error || 'حدث خطأ') + '</div>');
                return;
            }
            renderSupportModal(data.user || {}, data.history || []);
        } catch (err) {
            openModal('🛟 محادثة الدعم', '<div class="empty-state"><div class="icon">⚠️</div><div class="text">فشل جلب البيانات</div></div>');
        }
    }

    function renderSupportModal(user, history) {
        const infoHtml = `
            <div class="info-grid">
                <div class="info-item"><div class="label">المعرف</div><div class="value"><code>${esc(String(user.id != null ? user.id : '—'))}</code></div></div>
                <div class="info-item"><div class="label">الاسم</div><div class="value">${esc(user.name || '—')}</div></div>
                <div class="info-item"><div class="label">يوزر المنصة</div><div class="value"><code>${esc(user.platform_user || '—')}</code></div></div>
                <div class="info-item"><div class="label">الاشتراك</div><div class="value"><span class="badge ${user.is_subscribed ? 'badge-success' : 'badge-danger'}">${user.is_subscribed ? '✅ مشترك' : '❌ غير مشترك'}</span></div></div>
                <div class="info-item"><div class="label">تاريخ الانتهاء</div><div class="value">${esc(user.expiry_hijri || '—')}</div></div>
                <div class="info-item"><div class="label">الواجبات المحلولة</div><div class="value">${esc(String(user.total_hw_solved || 0))}</div></div>
                <div class="info-item"><div class="label">آخر نشاط</div><div class="value">${esc(user.last_active || '—')}</div></div>
                <div class="info-item"><div class="label">الدور</div><div class="value">${user.is_admin ? '🛡️ أدمن' : (user.is_reseller ? '💠 موزع' : '👤 مستخدم')}</div></div>
            </div>`;
        const historyHtml = history.length
            ? `<div class="activity-feed" id="support-history">` + history.map(h => {
                const fromUser = h.direction === 'user';
                return `<div class="activity-item">
                    <div class="activity-time">${esc(fmtEpoch(h.ts))}</div>
                    <div class="activity-icon icon-${fromUser ? 'user' : 'admin'}">${fromUser ? '👤' : '🛡️'}</div>
                    <div>${esc(h.detail || '')}</div>
                </div>`;
            }).join('') + `</div>`
            : '<div class="empty-state"><div class="icon">📭</div><div class="text">لا توجد رسائل في هذه المحادثة</div></div>';
        const replyHtml = `
            <div class="action-panel">
                <div class="action-panel-title">✍️ إرسال رد</div>
                <textarea id="support-reply-text" class="day-custom" style="width:100%;min-height:100px;box-sizing:border-box" placeholder="اكتب الرد هنا..."></textarea>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="support-reply-btn" onclick="sendSupportReply()">إرسال الرد</button>
                </div>
            </div>`;
        openModal(`🛟 محادثة الدعم — ${esc(user.name || user.id || '')}`, infoHtml + historyHtml + replyHtml);
    }

    async function sendSupportReply() {
        const btn = document.getElementById('support-reply-btn');
        const textEl = document.getElementById('support-reply-text');
        const text = (textEl.value || '').trim();
        if (!text) { showToast('⚠️ اكتب نص الرد أولاً', 'error'); return; }
        btn.disabled = true;
        btn.textContent = '⏳ جاري الإرسال...';
        try {
            const res = await fetch('/api/admin/support/' + encodeURIComponent(currentSupportUserId) + '/reply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            const data = await res.json();
            if (!res.ok || data.success === false) {
                btn.disabled = false;
                btn.textContent = 'إرسال الرد';
                showToast('⚠️ ' + esc(data.message || 'حدث خطأ'), 'error');
                return;
            }
            showToast('✅ ' + esc(data.message || 'تم إرسال الرد'), 'success');
            const d = await (await fetch('/api/admin/support/' + encodeURIComponent(currentSupportUserId))).json();
            renderSupportModal(d.user || {}, d.history || []);
            loadSupportConversations();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'إرسال الرد';
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
        }
    }

    /* ===== Logs Tab ===== */
    let logsPollTimer = null;

    function setLogsMsg(text, isError) {
        const el = document.getElementById('logs-msg');
        if (!el) return;
        if (!text) { el.style.display = 'none'; return; }
        el.style.display = 'block';
        el.textContent = text;
        el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
    }

    async function loadLogFiles() {
        try {
            const res = await fetch('/api/admin/logs');
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                setLogsMsg('⚠️ ' + esc(data.message || data.error || 'حدث خطأ'), true);
                return;
            }
            const sel = document.getElementById('logsFileSelect');
            const current = sel.value;
            sel.innerHTML = '<option value="">— اختر ملف السجل —</option>' +
                (data.files || []).map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('');
            if (current && (data.files || []).indexOf(current) !== -1) sel.value = current;
        } catch (err) {
            setLogsMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    function switchLogFile() {
        stopLogsPoll();
        loadLogFile();
        const chk = document.getElementById('logsAutoRefresh');
        if (chk && chk.checked) startLogsPoll();
    }

    function logsAutoRefresh() {
        const chk = document.getElementById('logsAutoRefresh');
        if (chk && chk.checked) {
            startLogsPoll();
        } else {
            stopLogsPoll();
        }
    }

    function startLogsPoll() {
        stopLogsPoll();
        logsPollTimer = setInterval(() => { loadLogFile(true); }, 5000);
    }

    function stopLogsPoll() {
        if (logsPollTimer) {
            clearInterval(logsPollTimer);
            logsPollTimer = null;
        }
    }

    async function loadLogFile(silent) {
        const sel = document.getElementById('logsFileSelect');
        const name = sel.value;
        const limit = document.getElementById('logsLimitSelect').value;
        const box = document.getElementById('logs-body');
        if (!name) { box.textContent = ''; return; }
        if (!silent) setLogsMsg('⏳ جاري تحميل السجل...', false);
        try {
            const res = await fetch('/api/admin/logs/' + encodeURIComponent(name) + '?tail=true&limit=' + encodeURIComponent(limit));
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                setLogsMsg('⚠️ ' + esc(data.message || data.error || 'حدث خطأ'), true);
                return;
            }
            setLogsMsg('', false);
            const lines = data.lines || [];
            box.innerHTML = (lines.length ? lines.map(l => esc(l)).join('\\n') : esc('(سجل فارغ)'));
            box.scrollTop = box.scrollHeight;
        } catch (err) {
            if (!silent) setLogsMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    async function loadUserLog() {
        const uid = document.getElementById('userLogUid').value.trim();
        if (!uid) { showToast('⚠️ أدخل معرف المستخدم', 'error'); return; }
        setLogsMsg('⏳ جاري تحميل سجل المستخدم...', false);
        try {
            const res = await fetch('/api/admin/logs/user/' + encodeURIComponent(uid) + '?limit=100');
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                setLogsMsg('⚠️ ' + esc(data.message || data.error || 'حدث خطأ'), true);
                return;
            }
            setLogsMsg('', false);
            const entries = data.entries || [];
            const wrap = document.getElementById('userlog-table-wrap');
            const tbody = document.getElementById('userlog-body');
            wrap.style.display = 'block';
            if (!entries.length) {
                tbody.innerHTML = '<tr><td colspan="3"><div class="empty-state"><div class="icon">📭</div><div class="text">لا توجد أحداث لهذا المستخدم</div></div></td></tr>';
                return;
            }
            tbody.innerHTML = entries.map(e => `
                <tr>
                    <td style="white-space:nowrap">${esc(e.ts || '—')}</td>
                    <td><code>${esc(e.step || '—')}</code></td>
                    <td style="max-width:420px;overflow:hidden;text-overflow:ellipsis" title="${esc(e.detail || '')}">${esc(e.detail || '—')}</td>
                </tr>`).join('');
        } catch (err) {
            setLogsMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    async function loadAuditLog() {
        const action = document.getElementById('auditActionInput').value.trim();
        const limit = document.getElementById('auditLimitSelect').value;
        setLogsMsg('⏳ جاري تحميل سجل التدقيق...', false);
        try {
            let url = '/api/admin/logs/audit?limit=' + encodeURIComponent(limit);
            if (action) url += '&action=' + encodeURIComponent(action);
            const res = await fetch(url);
            const data = await res.json();
            if (!res.ok || data.success === false || data.error) {
                setLogsMsg('⚠️ ' + esc(data.message || data.error || 'حدث خطأ'), true);
                return;
            }
            setLogsMsg('', false);
            const entries = data.entries || [];
            const tbody = document.getElementById('audit-body');
            if (!entries.length) {
                tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">📭</div><div class="text">لا توجد إدخالات</div></div></td></tr>';
                return;
            }
            tbody.innerHTML = entries.map(e => `
                <tr>
                    <td style="font-weight:600">${esc(e.admin_name || '—')}</td>
                    <td><code>${esc(e.action_type || '—')}</code></td>
                    <td class="hide-mobile" style="max-width:320px;overflow:hidden;text-overflow:ellipsis" title="${esc(e.details || '')}">${esc(e.details || '—')}</td>
                    <td style="white-space:nowrap">${esc(fmtEpoch(e.created_at))}</td>
                </tr>`).join('');
        } catch (err) {
            setLogsMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    /* ===== Backups Tab ===== */
    function setBackupsMsg(text, isError) {
        const el = document.getElementById('backups-msg');
        if (!el) return;
        if (!text) { el.style.display = 'none'; return; }
        el.style.display = 'block';
        el.textContent = text;
        el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
    }

    function setBackupButtonsDisabled(disabled) {
        document.querySelectorAll('#tab-backups .backup-btn').forEach(b => { b.disabled = disabled; });
    }

    function confirmBackup(kind) {
        const labels = { db: '📦 نسخة قاعدة البيانات', cv: '📊 تصدير بيانات الطلاب', admin_logs: '📜 تصدير سجلات الإدارة' };
        openModal('💾 تأكيد النسخة الاحتياطية', `
            <div class="action-panel">
                <div class="action-panel-title">${labels[kind] || esc(kind)}</div>
                <div style="color:var(--text-secondary);font-size:0.9em">سيتم إنشاء نسخة وإرسالها إلى قناة النسخ الاحتياطي — متابعة؟</div>
            </div>
            <div class="action-panel-btns">
                <button class="action-btn action-btn-primary" id="backup-confirm-btn" onclick="runBackup('${esc(kind)}')">متابعة</button>
                <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
            </div>
        `);
    }

    async function runBackup(kind) {
        const btn = document.getElementById('backup-confirm-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ جاري...'; }
        setBackupButtonsDisabled(true);
        closeModal();
        setBackupsMsg('⏳ جاري إنشاء النسخة الاحتياطية...', false);
        try {
            const res = await fetch('/api/admin/backup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind: kind })
            });
            const data = await res.json();
            const msg = data.message || (data.success === false ? 'فشل إنشاء النسخة' : 'تم إنشاء النسخة وإرسالها');
            if (data.success === false) {
                setBackupsMsg('⚠️ ' + esc(msg), true);
                showToast('⚠️ ' + esc(msg), 'error');
            } else {
                setBackupsMsg('✅ ' + esc(msg), false);
                showToast('✅ ' + esc(msg), 'success');
            }
        } catch (err) {
            setBackupsMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
        } finally {
            setBackupButtonsDisabled(false);
        }
    }

    /* ===== Control Tab (التحكم) ===== */
    let controlStatus = null;
    let freezeTarget = null;
    let modeTarget = null;

    function setControlMsg(text, isError) {
        const el = document.getElementById('control-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    async function loadControlStatus() {
        setControlMsg('⏳ جاري تحميل حالة البوت...', false);
        try {
            const res = await fetch('/api/admin/status');
            const data = await res.json();
            if (data.error || data.success === false) {
                setControlMsg('⚠️ ' + (data.message || data.error || 'فشل تحميل الحالة'), true);
                return;
            }
            controlStatus = data;
            renderControlStatus();
            setControlMsg('', false);
        } catch (err) {
            setControlMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    function renderControlStatus() {
        const s = controlStatus || {};
        const frozenBadge = document.getElementById('control-frozen-badge');
        frozenBadge.textContent = s.frozen ? '🧊 مجمّد' : '🟢 شغال';
        frozenBadge.className = 'badge ' + (s.frozen ? 'badge-danger' : 'badge-success');
        const modeBadge = document.getElementById('control-mode-badge');
        modeBadge.textContent = s.public_mode ? '🌍 عام' : '🔐 خاص';
        modeBadge.className = 'badge ' + (s.public_mode ? 'badge-info' : 'badge-warning');
        const aliveBadge = document.getElementById('control-alive-badge');
        aliveBadge.textContent = s.bot_alive ? '💓 حي' : '💀 ميت';
        aliveBadge.className = 'badge ' + (s.bot_alive ? 'badge-success' : 'badge-danger');
        document.getElementById('control-last-ts').textContent = fmtEpoch(s.last_stats_ts);
        // أزرار التبديل — نعرض الزر المناسب للحالة الحالية
        document.getElementById('btn-freeze').style.display = s.frozen ? 'none' : '';
        document.getElementById('btn-unfreeze').style.display = s.frozen ? '' : 'none';
        document.getElementById('btn-public').style.display = s.public_mode ? 'none' : '';
        document.getElementById('btn-private').style.display = s.public_mode ? '' : 'none';
    }

    function confirmFreezeToggle(frozen) {
        freezeTarget = frozen;
        openModal(frozen ? '❄️ تأكيد التجميد' : '▶️ تأكيد إلغاء التجميد', `
            <div class="action-panel">
                <div class="action-panel-title">${frozen ? '❄️ تجميد البوت' : '▶️ إلغاء التجميد'}</div>
                <div class="delete-warning">⚠️ ${frozen ? 'سيتم تجميد البوت ولن يستجيب للرسائل حتى إلغاء التجميد.' : 'سيتم إلغاء تجميد البوت وعودته للعمل بشكل طبيعي.'}</div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="freeze-confirm-btn" onclick="doFreezeToggle()">تأكيد</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function doFreezeToggle() {
        const btn = document.getElementById('freeze-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/system/freeze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frozen: freezeTarget })
            });
            const data = await res.json();
            if (data.success === false) {
                setControlMsg('⚠️ ' + (data.message || 'فشلت العملية'), true);
                showToast('⚠️ ' + (data.message || 'فشلت العملية'), 'error');
                btn.disabled = false;
                btn.textContent = 'تأكيد';
                return;
            }
            closeModal();
            setControlMsg('✅ ' + (data.message || 'تم بنجاح'), false);
            showToast('✅ ' + (data.message || 'تم بنجاح'), 'success');
            await loadControlStatus();
        } catch (err) {
            setControlMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'تأكيد';
        }
    }

    function confirmModeToggle(publicMode) {
        modeTarget = publicMode;
        openModal(publicMode ? '🌍 تأكيد الوضع العام' : '🔐 تأكيد الوضع الخاص', `
            <div class="action-panel">
                <div class="action-panel-title">${publicMode ? '🌍 تفعيل الوضع العام' : '🔐 تفعيل الوضع الخاص'}</div>
                <div class="delete-warning">⚠️ ${publicMode ? 'سيتم فتح البوت للاستخدام العام.' : 'سيتم تقييد البوت على المستخدمين المرتبطين فقط.'}</div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-info" id="mode-confirm-btn" onclick="doModeToggle()">تأكيد</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function doModeToggle() {
        const btn = document.getElementById('mode-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/system/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ public: modeTarget })
            });
            const data = await res.json();
            if (data.success === false) {
                setControlMsg('⚠️ ' + (data.message || 'فشلت العملية'), true);
                showToast('⚠️ ' + (data.message || 'فشلت العملية'), 'error');
                btn.disabled = false;
                btn.textContent = 'تأكيد';
                return;
            }
            closeModal();
            setControlMsg('✅ ' + (data.message || 'تم بنجاح'), false);
            showToast('✅ ' + (data.message || 'تم بنجاح'), 'success');
            await loadControlStatus();
        } catch (err) {
            setControlMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'تأكيد';
        }
    }

    /* ===== Admins Tab (الأدمنز) ===== */
    let adminsData = [];
    let adminDeleteTarget = null;
    let adminChargeTarget = null;

    function setAdminsMsg(text, isError) {
        const el = document.getElementById('admins-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    function adminName(uid) {
        const a = (adminsData || []).find(x => String(x.uid) === String(uid));
        return a ? (a.name || String(uid)) : String(uid);
    }

    async function loadAdmins() {
        setAdminsMsg('⏳ جاري تحميل الأدمنز...', false);
        try {
            const res = await fetch('/api/admin/admins');
            const data = await res.json();
            if (data.success === false) {
                setAdminsMsg('⚠️ ' + (data.message || 'فشل تحميل الأدمنز'), true);
                document.getElementById('admins-body').innerHTML = '';
                return;
            }
            adminsData = data.admins || [];
            renderAdmins();
            setAdminsMsg('', false);
        } catch (err) {
            setAdminsMsg('⚠️ فشل الاتصال بالخادم', true);
            document.getElementById('admins-body').innerHTML = '';
        }
    }

    function renderAdmins() {
        const body = document.getElementById('admins-body');
        if (!adminsData.length) {
            body.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="icon">👑</div><div class="text">لا يوجد أدمنز</div></div></td></tr>';
            return;
        }
        body.innerHTML = adminsData.map(a => {
            const isOwner = !!a.is_owner;
            let typeBadge;
            if (isOwner) typeBadge = '<span class="badge badge-danger">المالك</span>';
            else if (a.full_admin) typeBadge = '<span class="badge badge-primary">أدمن كامل</span>';
            else typeBadge = '<span class="badge badge-info">موزع رئيسي</span>';
            const actions = isOwner
                ? '<span class="badge badge-outline">المالك — بدون إجراءات</span>'
                : '<button class="action-btn action-btn-info" onclick="showChargeAdminPanel(' + a.uid + ')">💳 شحن رصيد</button>' +
                  '<button class="action-btn action-btn-danger" onclick="showDeleteAdminConfirm(' + a.uid + ')">🗑️ حذف</button>';
            return '<tr>' +
                '<td><code>' + esc(a.uid) + '</code></td>' +
                '<td style="font-weight:600">' + esc(a.name || '—') + '</td>' +
                '<td>' + esc(a.tg_username || '—') + '</td>' +
                '<td>' + typeBadge + '</td>' +
                '<td>' + esc(a.sub_resellers_count != null ? a.sub_resellers_count : 0) + '</td>' +
                '<td>' + actions + '</td>' +
            '</tr>';
        }).join('');
    }

    async function addAdmin() {
        const input = document.getElementById('admin-add-uid');
        const uid = parseInt(input.value, 10);
        if (!uid || uid <= 0) { setAdminsMsg('⚠️ أدخل معرف المستخدم أولاً', true); return; }
        const btn = document.getElementById('admin-add-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/admins', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid })
            });
            const data = await res.json();
            if (data.success === false) {
                setAdminsMsg('⚠️ ' + (data.message || 'فشلت الإضافة'), true);
                showToast('⚠️ ' + (data.message || 'فشلت الإضافة'), 'error');
                btn.disabled = false;
                btn.textContent = '➕ إضافة';
                return;
            }
            input.value = '';
            setAdminsMsg('✅ ' + (data.message || 'تمت الإضافة'), false);
            showToast('✅ ' + (data.message || 'تمت الإضافة'), 'success');
            await loadAdmins();
            btn.disabled = false;
            btn.textContent = '➕ إضافة';
        } catch (err) {
            setAdminsMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = '➕ إضافة';
        }
    }

    function showChargeAdminPanel(uid) {
        adminChargeTarget = uid;
        openModal('💳 شحن رصيد أدمن', `
            <div class="action-panel">
                <div class="action-panel-title">💳 شحن رصيد — ${esc(adminName(uid))}</div>
                <div class="action-panel-row">
                    <label for="admin-charge-amount">المبلغ:
                        <input type="number" id="admin-charge-amount" class="day-custom" min="0" step="0.01" placeholder="0" style="width:160px">
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="admin-charge-btn" onclick="confirmChargeAdmin()">شحن</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function confirmChargeAdmin() {
        const amount = parseFloat(document.getElementById('admin-charge-amount').value);
        if (!(amount >= 0)) { showToast('⚠️ أدخل مبلغاً صحيحاً', 'error'); return; }
        const btn = document.getElementById('admin-charge-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/admins/' + adminChargeTarget + '/credit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amount })
            });
            const data = await res.json();
            if (data.success === false) {
                setAdminsMsg('⚠️ ' + (data.message || 'فشل الشحن'), true);
                showToast('⚠️ ' + (data.message || 'فشل الشحن'), 'error');
                btn.disabled = false;
                btn.textContent = 'شحن';
                return;
            }
            closeModal();
            setAdminsMsg('✅ ' + (data.message || 'تم الشحن'), false);
            showToast('✅ ' + (data.message || 'تم الشحن'), 'success');
            await loadAdmins();
        } catch (err) {
            setAdminsMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'شحن';
        }
    }

    function showDeleteAdminConfirm(uid) {
        adminDeleteTarget = uid;
        openModal('🗑️ حذف أدمن', `
            <div class="action-panel action-panel-danger">
                <div class="action-panel-title">🗑️ حذف الأدمن</div>
                <div class="delete-warning">⚠️ تحذير: سيتم حذف الأدمن <b>${esc(adminName(uid))}</b> وإلغاء صلاحياته نهائياً، ولا يمكن التراجع عن هذا الإجراء.</div>
                <div class="action-panel-row">
                    <label>اكتب <b>DELETE</b> لتأكيد الحذف:
                        <input type="text" id="admin-delete-confirm-input" class="day-custom" placeholder="DELETE" oninput="toggleAdminDeleteConfirm(this.value)">
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="admin-delete-confirm-btn" onclick="confirmDeleteAdmin()" disabled>حذف نهائي</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    function toggleAdminDeleteConfirm(val) {
        document.getElementById('admin-delete-confirm-btn').disabled = (val !== 'DELETE');
    }

    async function confirmDeleteAdmin() {
        const btn = document.getElementById('admin-delete-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/admins/' + adminDeleteTarget, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: 'DELETE' })
            });
            const data = await res.json();
            if (data.success === false) {
                setAdminsMsg('⚠️ ' + (data.message || 'فشل الحذف'), true);
                showToast('⚠️ ' + (data.message || 'فشل الحذف'), 'error');
                btn.disabled = false;
                btn.textContent = 'حذف نهائي';
                return;
            }
            closeModal();
            setAdminsMsg('✅ ' + (data.message || 'تم حذف الأدمن'), false);
            showToast('✅ ' + (data.message || 'تم حذف الأدمن'), 'success');
            await loadAdmins();
        } catch (err) {
            setAdminsMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'حذف نهائي';
        }
    }

    /* ===== Resellers Tab (الموزعون) ===== */
    let resellersData = [];
    let resellerDeleteTarget = null;
    let resellerChargeTarget = null;

    const RESELLER_STATS_LABELS = {
        total: 'عدد الموزعين',
        total_credit: 'إجمالي الرصيد',
        total_keys: 'إجمالي المفاتيح',
        total_used: 'المفاتيح المستخدمة',
        total_customers: 'عدد العملاء'
    };

    function setResellersMsg(text, isError) {
        const el = document.getElementById('resellers-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    function resellerName(uid) {
        const r = (resellersData || []).find(x => String(x.uid) === String(uid));
        return r ? (r.name || String(uid)) : String(uid);
    }

    function renderResellerStats(stats) {
        const grid = document.getElementById('resellers-stats-grid');
        const entries = Object.entries(stats || {});
        if (!entries.length) { grid.innerHTML = ''; return; }
        grid.innerHTML = entries.map(pair => {
            const label = RESELLER_STATS_LABELS[pair[0]] || pair[0];
            return '<div class="api-card"><div class="api-label">' + esc(label) + '</div><div class="api-value">' + esc(pair[1]) + '</div></div>';
        }).join('');
    }

    function prefillResellerPrices(stats) {
        if (!stats) return;
        const map = { weekly: 'price-weekly', monthly: 'price-monthly', semester: 'price-semester' };
        for (const key in map) {
            const el = document.getElementById(map[key]);
            if (el && stats[key] !== undefined && stats[key] !== null) el.value = stats[key];
        }
    }

    async function loadResellers() {
        setResellersMsg('⏳ جاري تحميل الموزعين...', false);
        try {
            const statsRes = await fetch('/api/admin/resellers/stats');
            const listRes = await fetch('/api/admin/resellers');
            const statsData = await statsRes.json();
            const listData = await listRes.json();
            if (statsData.success === false) {
                setResellersMsg('⚠️ ' + (statsData.message || 'فشل تحميل الإحصائيات'), true);
            }
            renderResellerStats(statsData.stats || {});
            prefillResellerPrices(statsData.stats || {});
            resellersData = listData.resellers || [];
            renderResellers();
            if (statsData.success !== false) setResellersMsg('', false);
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            document.getElementById('resellers-body').innerHTML = '';
        }
    }

    function renderResellers() {
        const body = document.getElementById('resellers-body');
        if (!resellersData.length) {
            body.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="icon">🏪</div><div class="text">لا يوجد موزعون</div></div></td></tr>';
            return;
        }
        body.innerHTML = resellersData.map(r => {
            return '<tr>' +
                '<td><code>' + esc(r.uid) + '</code></td>' +
                '<td style="font-weight:600">' + esc(r.name || '—') + '</td>' +
                '<td>' + esc(r.credit != null ? r.credit : 0) + '</td>' +
                '<td>' + esc(r.customers_count != null ? r.customers_count : 0) + '</td>' +
                '<td>' +
                    '<button class="action-btn action-btn-info" onclick="showChargeResellerPanel(' + r.uid + ')">💳 شحن</button>' +
                    '<button class="action-btn action-btn-danger" onclick="showDeleteResellerConfirm(' + r.uid + ')">🗑️ حذف</button>' +
                '</td>' +
            '</tr>';
        }).join('');
    }

    async function addReseller() {
        const input = document.getElementById('reseller-add-uid');
        const uid = parseInt(input.value, 10);
        if (!uid || uid <= 0) { setResellersMsg('⚠️ أدخل معرف المستخدم أولاً', true); return; }
        const btn = document.getElementById('reseller-add-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/resellers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid })
            });
            const data = await res.json();
            if (data.success === false) {
                setResellersMsg('⚠️ ' + (data.message || 'فشلت الإضافة'), true);
                showToast('⚠️ ' + (data.message || 'فشلت الإضافة'), 'error');
                btn.disabled = false;
                btn.textContent = '➕ إضافة';
                return;
            }
            input.value = '';
            setResellersMsg('✅ ' + (data.message || 'تمت الإضافة'), false);
            showToast('✅ ' + (data.message || 'تمت الإضافة'), 'success');
            await loadResellers();
            btn.disabled = false;
            btn.textContent = '➕ إضافة';
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = '➕ إضافة';
        }
    }

    function showChargeResellerPanel(uid) {
        resellerChargeTarget = uid;
        openModal('💳 شحن رصيد موزع', `
            <div class="action-panel">
                <div class="action-panel-title">💳 شحن رصيد — ${esc(resellerName(uid))}</div>
                <div class="action-panel-row">
                    <label for="reseller-charge-amount">المبلغ:
                        <input type="number" id="reseller-charge-amount" class="day-custom" min="0" step="0.01" placeholder="0" style="width:160px">
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="reseller-charge-btn" onclick="confirmChargeReseller()">شحن</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function confirmChargeReseller() {
        const amount = parseFloat(document.getElementById('reseller-charge-amount').value);
        if (!(amount >= 0)) { showToast('⚠️ أدخل مبلغاً صحيحاً', 'error'); return; }
        const btn = document.getElementById('reseller-charge-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/resellers/' + resellerChargeTarget + '/credit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amount })
            });
            const data = await res.json();
            if (data.success === false) {
                setResellersMsg('⚠️ ' + (data.message || 'فشل الشحن'), true);
                showToast('⚠️ ' + (data.message || 'فشل الشحن'), 'error');
                btn.disabled = false;
                btn.textContent = 'شحن';
                return;
            }
            closeModal();
            setResellersMsg('✅ ' + (data.message || 'تم الشحن'), false);
            showToast('✅ ' + (data.message || 'تم الشحن'), 'success');
            await loadResellers();
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'شحن';
        }
    }

    function showDeleteResellerConfirm(uid) {
        resellerDeleteTarget = uid;
        openModal('🗑️ حذف موزع', `
            <div class="action-panel action-panel-danger">
                <div class="action-panel-title">🗑️ حذف الموزع</div>
                <div class="delete-warning">⚠️ تحذير: سيتم حذف الموزع <b>${esc(resellerName(uid))}</b> نهائياً مع بياناته، ولا يمكن التراجع عن هذا الإجراء.</div>
                <div class="action-panel-row">
                    <label>اكتب <b>DELETE</b> لتأكيد الحذف:
                        <input type="text" id="reseller-delete-confirm-input" class="day-custom" placeholder="DELETE" oninput="toggleResellerDeleteConfirm(this.value)">
                    </label>
                </div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="reseller-delete-confirm-btn" onclick="confirmDeleteReseller()" disabled>حذف نهائي</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    function toggleResellerDeleteConfirm(val) {
        document.getElementById('reseller-delete-confirm-btn').disabled = (val !== 'DELETE');
    }

    async function confirmDeleteReseller() {
        const btn = document.getElementById('reseller-delete-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/resellers/' + resellerDeleteTarget, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: 'DELETE' })
            });
            const data = await res.json();
            if (data.success === false) {
                setResellersMsg('⚠️ ' + (data.message || 'فشل الحذف'), true);
                showToast('⚠️ ' + (data.message || 'فشل الحذف'), 'error');
                btn.disabled = false;
                btn.textContent = 'حذف نهائي';
                return;
            }
            closeModal();
            setResellersMsg('✅ ' + (data.message || 'تم حذف الموزع'), false);
            showToast('✅ ' + (data.message || 'تم حذف الموزع'), 'success');
            await loadResellers();
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'حذف نهائي';
        }
    }

    async function saveResellerPrices() {
        const weekly = parseFloat(document.getElementById('price-weekly').value);
        const monthly = parseFloat(document.getElementById('price-monthly').value);
        const semester = parseFloat(document.getElementById('price-semester').value);
        if (!(weekly >= 0) || !(monthly >= 0) || !(semester >= 0)) {
            setResellersMsg('⚠️ أدخل الأسعار الثلاثة بشكل صحيح', true);
            return;
        }
        const btn = document.getElementById('prices-save-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري الحفظ...';
        try {
            const res = await fetch('/api/admin/resellers/prices', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ weekly: weekly, monthly: monthly, semester: semester })
            });
            const data = await res.json();
            if (data.success === false) {
                setResellersMsg('⚠️ ' + (data.message || 'فشل حفظ الأسعار'), true);
                showToast('⚠️ ' + (data.message || 'فشل حفظ الأسعار'), 'error');
                btn.disabled = false;
                btn.textContent = '💾 حفظ الأسعار';
                return;
            }
            setResellersMsg('✅ ' + (data.message || 'تم حفظ الأسعار'), false);
            showToast('✅ ' + (data.message || 'تم حفظ الأسعار'), 'success');
            btn.disabled = false;
            btn.textContent = '💾 حفظ الأسعار';
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = '💾 حفظ الأسعار';
        }
    }

    function confirmBanCustomer() {
        const input = document.getElementById('ban-customer-uid');
        const uid = parseInt(input.value, 10);
        if (!uid || uid <= 0) { setResellersMsg('⚠️ أدخل معرف العميل أولاً', true); return; }
        const action = document.getElementById('ban-customer-action').value;
        const actionTxt = (action === 'ban') ? '🚫 Ban (حظر نهائي)' : '⏸️ Stop (إيقاف مؤقت)';
        openModal('🚫 تأكيد إجراء على عميل', `
            <div class="action-panel action-panel-danger">
                <div class="action-panel-title">${actionTxt}</div>
                <div class="delete-warning">⚠️ تحذير: سيتم تطبيق <b>${actionTxt}</b> على العميل <b><code>${uid}</code></b>، ولا يمكن التراجع عن هذا الإجراء.</div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-danger" id="ban-customer-confirm-btn" onclick="doBanCustomer(${uid}, '${action}')">تأكيد</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function doBanCustomer(uid, action) {
        const btn = document.getElementById('ban-customer-confirm-btn');
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch('/api/admin/resellers/customers/' + uid + '/ban', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
            });
            const data = await res.json();
            if (data.success === false) {
                setResellersMsg('⚠️ ' + (data.message || 'فشل تنفيذ الإجراء'), true);
                showToast('⚠️ ' + (data.message || 'فشل تنفيذ الإجراء'), 'error');
                btn.disabled = false;
                btn.textContent = 'تأكيد';
                return;
            }
            closeModal();
            document.getElementById('ban-customer-uid').value = '';
            setResellersMsg('✅ ' + (data.message || 'تم تنفيذ الإجراء'), false);
            showToast('✅ ' + (data.message || 'تم تنفيذ الإجراء'), 'success');
        } catch (err) {
            setResellersMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            btn.disabled = false;
            btn.textContent = 'تأكيد';
        }
    }

    /* ===== Payment Settings ===== */
    let paymentConfig = null;
    const PAYMENT_PLAN_IDS = ['weekly', 'monthly', 'semester'];
    const PAYMENT_PLAN_LABELS = { weekly: 'أسبوعي', monthly: 'شهري', semester: 'ترم' };
    const PAYMENT_FIELD_LABELS = {
        price: 'السعر (ريال)', days: 'المدة (أيام)', max_homeworks: 'عدد الواجبات',
        stars: 'سعر النجوم', is_active: 'التفعيل',
        bank_name: 'اسم البنك', bank_account_name: 'اسم المستفيد',
        bank_account_number: 'رقم الحساب', bank_iban: 'الآيبان',
        stc_phone: 'رقم الجوال', stc_notes: 'ملاحظات',
        method_bank: 'تحويل بنكي', method_stc: 'STC Pay', method_stars: 'دفع بالنجوم'
    };

    function setPaymentSettingsMsg(text, isError) {
        const el = document.getElementById('settings-msg');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.className = 'action-msg ' + (isError ? 'action-msg-error' : 'action-msg-success');
            el.style.display = '';
        } else {
            el.textContent = '';
            el.className = 'action-msg';
            el.style.display = 'none';
        }
    }

    function renderPaymentPlans(plans) {
        const grid = document.getElementById('settings-plans-grid');
        grid.innerHTML = PAYMENT_PLAN_IDS.map(pid => {
            const p = plans[pid] || {};
            return '<div class="api-card" style="min-width:220px">' +
                '<div class="api-label">' + esc(p.name || PAYMENT_PLAN_LABELS[pid]) + '</div>' +
                '<div style="margin-top:10px">' +
                '<div class="action-panel-row"><label>السعر (ريال): <input type="number" id="ps-price-' + pid + '" class="day-custom" min="0" step="0.01" style="width:110px"></label></div>' +
                '<div class="action-panel-row"><label>المدة (أيام): <input type="number" id="ps-days-' + pid + '" class="day-custom" min="1" step="1" style="width:110px"></label></div>' +
                '<div class="action-panel-row"><label>عدد الواجبات: <input type="number" id="ps-hw-' + pid + '" class="day-custom" min="0" step="1" style="width:110px"></label></div>' +
                '<div class="action-panel-row"><label>سعر النجوم: <input type="number" id="ps-stars-' + pid + '" class="day-custom" min="0" step="1" style="width:110px"></label></div>' +
                '<div class="action-panel-row"><label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="ps-active-' + pid + '" style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer"> تفعيل/تعطيل</label></div>' +
                '</div></div>';
        }).join('');
    }

    async function loadPaymentSettings() {
        setPaymentSettingsMsg('⏳ جاري تحميل إعدادات الدفع...', false);
        try {
            const res = await fetch('/api/admin/payment-config');
            const data = await res.json();
            if (data.success === false || data.error) {
                setPaymentSettingsMsg('⚠️ ' + (data.message || data.error || 'فشل تحميل الإعدادات'), true);
                return;
            }
            paymentConfig = data;
            renderPaymentPlans(data.plans || {});
            const bank = data.bank || {};
            const stc = data.stc || {};
            const methods = data.methods || {};
            const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = (v === null || v === undefined) ? '' : v; };
            setVal('ps-bank_name', bank.bank_name);
            setVal('ps-bank_account_name', bank.bank_account_name);
            setVal('ps-bank_account_number', bank.bank_account_number);
            setVal('ps-bank_iban', bank.bank_iban);
            setVal('ps-stc_phone', stc.stc_phone);
            setVal('ps-stc_notes', stc.stc_notes);
            document.getElementById('ps-method-bank').checked = !!methods.bank;
            document.getElementById('ps-method-stc').checked = !!methods.stc;
            document.getElementById('ps-method-stars').checked = !!methods.stars;
            setPaymentSettingsMsg('', false);
        } catch (err) {
            setPaymentSettingsMsg('⚠️ فشل الاتصال بالخادم', true);
        }
    }

    function paymentValueLabel(key, value) {
        if (key === 'is_active') return value ? 'مفعل' : 'معطل';
        return String(value);
    }

    function buildPaymentChanges() {
        const changes = [];
        const payload = { plans: {}, bank: {}, stc: {}, methods: {} };
        const base = paymentConfig || {};
        const basePlans = base.plans || {};
        const baseBank = base.bank || {};
        const baseStc = base.stc || {};
        const baseMethods = base.methods || {};
        const num = v => (v === '' || v === null || v === undefined) ? NaN : Number(v);

        for (let i = 0; i < PAYMENT_PLAN_IDS.length; i++) {
            const pid = PAYMENT_PLAN_IDS[i];
            const label = PAYMENT_PLAN_LABELS[pid];
            const cur = basePlans[pid] || {};
            const price = num(document.getElementById('ps-price-' + pid).value);
            const days = num(document.getElementById('ps-days-' + pid).value);
            const hw = num(document.getElementById('ps-hw-' + pid).value);
            const stars = num(document.getElementById('ps-stars-' + pid).value);
            const active = document.getElementById('ps-active-' + pid).checked;
            if (!(price >= 0) || !(days >= 0) || !(hw >= 0) || !(stars >= 0)) {
                setPaymentSettingsMsg('⚠️ تأكد من إدخال قيم صحيحة لخطة ' + label, true);
                return null;
            }
            const fields = {};
            if (Number(cur.price) !== price) {
                fields.price = price;
                changes.push(esc(PAYMENT_FIELD_LABELS.price) + ' (' + esc(label) + '): ' + esc(paymentValueLabel('price', cur.price)) + ' → ' + esc(paymentValueLabel('price', price)));
            }
            if (Number(cur.days) !== days) {
                fields.days = days;
                changes.push(esc(PAYMENT_FIELD_LABELS.days) + ' (' + esc(label) + '): ' + esc(paymentValueLabel('days', cur.days)) + ' → ' + esc(paymentValueLabel('days', days)));
            }
            if (Number(cur.max_homeworks) !== hw) {
                fields.max_homeworks = hw;
                changes.push(esc(PAYMENT_FIELD_LABELS.max_homeworks) + ' (' + esc(label) + '): ' + esc(paymentValueLabel('max_homeworks', cur.max_homeworks)) + ' → ' + esc(paymentValueLabel('max_homeworks', hw)));
            }
            if (Number(cur.stars) !== stars) {
                fields.stars = stars;
                changes.push(esc(PAYMENT_FIELD_LABELS.stars) + ' (' + esc(label) + '): ' + esc(paymentValueLabel('stars', cur.stars)) + ' → ' + esc(paymentValueLabel('stars', stars)));
            }
            if (!!cur.is_active !== active) {
                fields.is_active = active;
                changes.push(esc(PAYMENT_FIELD_LABELS.is_active) + ' (' + esc(label) + '): ' + esc(paymentValueLabel('is_active', cur.is_active)) + ' → ' + esc(paymentValueLabel('is_active', active)));
            }
            if (Object.keys(fields).length) payload.plans[pid] = fields;
        }

        const textPairs = [
            ['bank_name', 'ps-bank_name', 'bank'],
            ['bank_account_name', 'ps-bank_account_name', 'bank'],
            ['bank_account_number', 'ps-bank_account_number', 'bank'],
            ['bank_iban', 'ps-bank_iban', 'bank'],
            ['stc_phone', 'ps-stc_phone', 'stc'],
            ['stc_notes', 'ps-stc_notes', 'stc']
        ];
        for (let i = 0; i < textPairs.length; i++) {
            const key = textPairs[i][0], elId = textPairs[i][1], section = textPairs[i][2];
            const curBase = section === 'bank' ? baseBank : baseStc;
            const newVal = document.getElementById(elId).value.trim();
            if (!newVal) {
                setPaymentSettingsMsg('⚠️ ' + esc(PAYMENT_FIELD_LABELS[key]) + ' مطلوب', true);
                return null;
            }
            const oldVal = curBase[key] || '';
            if (oldVal !== newVal) {
                payload[section][key] = newVal;
                changes.push(esc(PAYMENT_FIELD_LABELS[key]) + ': ' + esc(oldVal) + ' → ' + esc(newVal));
            }
        }

        const methodPairs = [['bank', 'ps-method-bank'], ['stc', 'ps-method-stc'], ['stars', 'ps-method-stars']];
        for (let i = 0; i < methodPairs.length; i++) {
            const key = methodPairs[i][0], elId = methodPairs[i][1];
            const newVal = document.getElementById(elId).checked;
            const oldVal = !!baseMethods[key];
            if (oldVal !== newVal) {
                payload.methods[key] = newVal;
                changes.push(esc(PAYMENT_FIELD_LABELS['method_' + key]) + ': ' + esc(oldVal ? 'مفعل' : 'معطل') + ' → ' + esc(newVal ? 'مفعل' : 'معطل'));
            }
        }
        return { changes: changes, payload: payload };
    }

    function confirmSavePaymentSettings() {
        const built = buildPaymentChanges();
        if (!built) return;
        if (!built.changes.length) { setPaymentSettingsMsg('ℹ️ لا توجد تغييرات للحفظ', true); return; }
        const lines = built.changes.map(c => '<div style="padding:6px 10px;border-bottom:1px solid var(--border)">' + c + '</div>').join('');
        openModal('💾 تأكيد حفظ الإعدادات', `
            <div class="action-panel">
                <div class="action-panel-title">📋 ملخص التغييرات</div>
                <div style="max-height:280px;overflow-y:auto;font-size:0.9em;line-height:1.7;margin-bottom:6px">${lines}</div>
                <div style="font-size:0.85em;color:var(--text-secondary)">هل أنت متأكد من حفظ هذه التغييرات؟</div>
                <div class="action-panel-btns">
                    <button class="action-btn action-btn-primary" id="pay-settings-confirm-btn" onclick="doSavePaymentSettings()">✅ تأكيد الحفظ</button>
                    <button class="action-btn action-btn-ghost" onclick="closeModal()">إلغاء</button>
                </div>
            </div>`);
    }

    async function doSavePaymentSettings() {
        const built = buildPaymentChanges();
        if (!built) return;
        const btn = document.getElementById('pay-settings-confirm-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ جاري الحفظ...'; }
        try {
            const res = await fetch('/api/admin/payment-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true, plans: built.payload.plans, bank: built.payload.bank, stc: built.payload.stc, methods: built.payload.methods })
            });
            const data = await res.json();
            if (data.success === false || data.error) {
                const msg = data.message || data.error || 'فشل حفظ الإعدادات';
                setPaymentSettingsMsg('⚠️ ' + msg, true);
                showToast('⚠️ ' + msg, 'error');
                if (btn) { btn.disabled = false; btn.textContent = '✅ تأكيد الحفظ'; }
                return;
            }
            closeModal();
            const msg = data.message || 'تم حفظ إعدادات الدفع';
            setPaymentSettingsMsg('✅ ' + msg, false);
            showToast('✅ ' + msg, 'success');
            await loadPaymentSettings();
        } catch (err) {
            setPaymentSettingsMsg('⚠️ فشل الاتصال بالخادم', true);
            showToast('⚠️ فشل الاتصال بالخادم', 'error');
            if (btn) { btn.disabled = false; btn.textContent = '✅ تأكيد الحفظ'; }
        }
    }

    /* ===== Clock ===== */
    function updateTime() {
        const now = new Date();
        document.getElementById('current-time').textContent =
            now.toLocaleString('ar-SA', { timeZone:'Asia/Riyadh', dateStyle:'full', timeStyle:'medium' });
    }
    setInterval(updateTime, 1000);
    updateTime();
    </script>
</body>
</html>
"""


# ==============================================================================
# WebSocket Connection Manager
# ==============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


manager = ConnectionManager()


# ==============================================================================
# Routes — الصفحة الرئيسية والداشبورد
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def login_page():
    return LOGIN_PAGE


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return DASHBOARD_PAGE


# ==============================================================================
# Routes — API endpoints (Authentication)
# ==============================================================================

@app.post("/api/login")
async def api_login(login_data: LoginData, request: Request):
    """
    تسجيل دخول آمن مع:
    - Rate Limiting (5 محاولات / 5 دقائق)
    - bcrypt password verification
    - JWT session cookie (HttpOnly)
    - Audit logging
    """
    success, message, token = await auth_manager.authenticate(
        username=login_data.username,
        password=login_data.password,
        request=request,
    )

    if success and token:
        # إنشاء response مع cookie
        json_response = JSONResponse({
            "success": True,
            "message": message,
            "username": login_data.username,
        })
        auth_manager.create_session_cookie(
            json_response,
            token,
            secure=config.dashboard_cookie_secure,
        )
        return json_response

    # Rate limit أو خطأ في المصادقة
    is_rate_limited = "rate" in message.lower() or "محظور" in message or "تجاوز" in message
    status_code = 429 if is_rate_limited else 401
    return JSONResponse(
        {"success": False, "message": message, "rate_limited": is_rate_limited},
        status_code=status_code,
    )


@app.post("/api/logout")
async def api_logout(request: Request):
    """تسجيل خروج ومسح الـ JWT cookie"""
    payload = await auth_manager.verify_session(request)
    if payload:
        auth_manager.audit_logger.log_attempt(
            username=payload.get("sub"),
            ip_address=request.client.host if request.client else "unknown",
            success=True,
            reason="logout",
        )

    response = JSONResponse({"success": True, "message": "تم تسجيل الخروج"})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/api/me")
async def api_me(request: Request):
    """جلب معلومات المستخدم الحالي (للـ frontend)"""
    payload = await auth_manager.verify_session(request)
    if not payload:
        return JSONResponse(
            {"authenticated": False, "redirect": "/"},
            status_code=401
        )
    return {
        "authenticated": True,
        "username": payload.get("sub"),
        "issued_at": payload.get("iat"),
        "expires_at": payload.get("exp"),
        "absolute_exp": payload.get("abs_exp"),
    }


@app.get("/api/verify")
async def api_verify(request: Request):
    """التحقق من صلاحية الجلسة (backward-compatible)"""
    payload = await auth_manager.verify_session(request)
    if payload:
        return {"success": True, "username": payload.get("sub")}
    return JSONResponse({"success": False}, status_code=401)


async def _user_detail_payload(user_id: int):
    """منطق تفاصيل المستخدم المشترك — يُستخدم من /api/user و /api/admin/users"""
    user = await db_get_user(user_id)
    if not user:
        return None

    conn = await _db_pool.get_connection()

    async with conn.execute("""
        SELECT event_name, created_at, details FROM event_logs
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 10
    """, (user_id,)) as c:
        activities = await c.fetchall()

    async with conn.execute("""
        SELECT COUNT(*) FROM event_logs WHERE user_id = ? AND event_type = 'QUESTION_SOLVED'
    """, (user_id,)) as c:
        total_questions = (await c.fetchone())[0] or 0

    return {
        "id": user['telegram_id'],
        "name": user.get('name', ''),
        "platform_user": user.get('dars360_user'),
        "password": None,
        "has_password": bool(user.get('dars360_pass')),
        "is_subscribed": await is_subscribed(user_id),
        "expiry": user.get('expiry_hijri'),
        "attempts": user.get('free_attempts', 0),
        "total_hw": user.get('total_hw_solved', 0),
        "total_questions": total_questions,
        "last_active": datetime.fromtimestamp(user.get('last_active', 0)).strftime('%Y-%m-%d %H:%M') if user.get('last_active') else '—',
        "recent_activities": [
            {
                "time": datetime.fromtimestamp(a[1]).strftime('%H:%M:%S'),
                "type": "success" if a[2] else "info",
                "icon": "📌",
                "description": a[0]
            } for a in activities
        ]
    }


@app.get("/api/user/{user_id}")
async def get_user_details(user_id: int):
    data = await _user_detail_payload(user_id)
    if data is None:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return data


@app.get("/api/db-questions")
async def get_db_questions():
    try:
        conn = await _db_pool.get_connection()
        questions = []
        async with conn.execute("""
            SELECT user_id, details, created_at FROM event_logs
            WHERE event_name = 'DB' AND event_type = 'QUESTION_SOLVED'
            ORDER BY created_at DESC LIMIT 50
        """) as c:
            async for row in c:
                details = json.loads(row[1]) if row[1] else {}
                user = await db_get_user(row[0])
                questions.append({
                    "user": user.get('name', str(row[0])) if user else str(row[0]),
                    "user_id": row[0],
                    "subject": details.get('subject', 'غير معروف'),
                    "question": details.get('question', 'سؤال'),
                    "time": datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')
                })
        return JSONResponse(questions)
    except Exception as e:
        admin_trace("DB_QUESTIONS_ERR", str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/groq-questions")
async def get_groq_questions():
    try:
        conn = await _db_pool.get_connection()
        questions = []
        async with conn.execute("""
            SELECT user_id, details, created_at FROM event_logs
            WHERE event_name = 'GROQ' AND event_type = 'QUESTION_SOLVED'
            ORDER BY created_at DESC LIMIT 50
        """) as c:
            async for row in c:
                details = json.loads(row[1]) if row[1] else {}
                user = await db_get_user(row[0])
                questions.append({
                    "user": user.get('name', str(row[0])) if user else str(row[0]),
                    "user_id": row[0],
                    "subject": details.get('subject', 'غير معروف'),
                    "question": details.get('question', 'سؤال'),
                    "time": datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')
                })
        return JSONResponse(questions)
    except Exception as e:
        admin_trace("GROQ_QUESTIONS_ERR", str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/detail/{detail_type}")
async def get_detail(detail_type: str):
    """جلب تفاصيل لأي بطاقة إحصائية"""
    try:
        conn = await _db_pool.get_connection()
        now_ts = time.time()
        today_start = now_ts - (now_ts % 86400)
        five_min_ago = now_ts - 300

        if detail_type == "all-users":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, tg_username, dars360_user, expiry_ts, free_attempts, total_hw_solved, last_active
                FROM users ORDER BY created_at DESC LIMIT 100
            """) as c:
                async for row in c:
                    is_sub = False
                    try: is_sub = float(row[4]) > now_ts if row[4] else False
                    except: pass
                    la = ""
                    if row[7]:
                        try: la = datetime.fromtimestamp(float(row[7])).strftime('%Y-%m-%d %H:%M')
                        except: la = "—"
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "username": row[2] or '—',
                                 "platform": row[3] or '—', "subscribed": is_sub, "free": row[5] or 0,
                                 "hw": row[6] or 0, "last_active": la})
            return JSONResponse({"title": "👥 إجمالي المستخدمين", "count": len(rows), "type": "users", "data": rows})

        elif detail_type == "active-now":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, last_active FROM users WHERE last_active > ? ORDER BY last_active DESC
            """, (five_min_ago,)) as c:
                async for row in c:
                    la = ""
                    if row[2]:
                        try: la = datetime.fromtimestamp(float(row[2])).strftime('%H:%M:%S')
                        except: la = "—"
                    in_session = row[0] in active_sessions
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "last_active": la, "in_session": in_session})
            return JSONResponse({"title": "⚡ نشطين الآن", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "active-today":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, last_active FROM users WHERE last_active > ? ORDER BY last_active DESC
            """, (today_start,)) as c:
                async for row in c:
                    la = ""
                    if row[2]:
                        try: la = datetime.fromtimestamp(float(row[2])).strftime('%H:%M:%S')
                        except: la = "—"
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "last_active": la})
            return JSONResponse({"title": "📆 نشطين اليوم", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "subscribers":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, expiry_ts, expiry_hijri, total_hw_solved, free_attempts
                FROM users WHERE expiry_ts > ? ORDER BY expiry_ts ASC
            """, (now_ts,)) as c:
                async for row in c:
                    try: days_left = int((float(row[2]) - now_ts) / 86400) if row[2] else 0
                    except: days_left = 0
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "expiry": row[3] or '—',
                                 "days_left": days_left, "hw": row[4] or 0, "free": row[5] or 0})
            return JSONResponse({"title": "👑 المشتركون", "count": len(rows), "type": "subscribers", "data": rows})

        elif detail_type == "finished-free":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, total_hw_solved, last_active
                FROM users WHERE (free_attempts = 0 OR free_attempts IS NULL) AND (expiry_ts IS NULL OR expiry_ts < ?)
                ORDER BY last_active DESC LIMIT 100
            """, (now_ts,)) as c:
                async for row in c:
                    la = ""
                    if row[3]:
                        try: la = datetime.fromtimestamp(float(row[3])).strftime('%Y-%m-%d %H:%M')
                        except: la = "—"
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "hw": row[2] or 0, "last_active": la})
            return JSONResponse({"title": "⛔ خلصت مجانيهم", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "remaining-free":
            rows = []
            async with conn.execute("""
                SELECT telegram_id, name, free_attempts, total_hw_solved, last_active
                FROM users WHERE free_attempts > 0 ORDER BY free_attempts DESC LIMIT 100
            """) as c:
                async for row in c:
                    la = ""
                    if row[4]:
                        try: la = datetime.fromtimestamp(float(row[4])).strftime('%Y-%m-%d %H:%M')
                        except: la = "—"
                    rows.append({"id": row[0], "name": row[1] or f"User {row[0]}", "free": row[2] or 0,
                                 "hw": row[3] or 0, "last_active": la})
            return JSONResponse({"title": "🎁 لسه عندهم مجاني", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "total-hw":
            rows = []
            async with conn.execute("""
                SELECT user_id, subject, total_questions, correct_answers, wrong_answers, status, start_time, end_time
                FROM homework_sessions WHERE status = 'completed' ORDER BY end_time DESC LIMIT 50
            """) as c:
                async for row in c:
                    user = await db_get_user(row[0])
                    pct = round(row[3] / row[2] * 100) if row[2] else 0
                    duration = ""
                    if row[6] and row[7]:
                        try: duration = f"{int((row[7] - row[6]) / 60)} دقيقة"
                        except: pass
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "user_id": row[0], "subject": row[1] or '—', "total": row[2] or 0,
                                 "correct": row[3] or 0, "wrong": row[4] or 0, "pct": pct, "duration": duration})
            return JSONResponse({"title": "📚 إجمالي الواجبات", "count": len(rows), "type": "homeworks", "data": rows})

        elif detail_type == "total-questions":
            rows = []
            async with conn.execute("""
                SELECT user_id, event_name, details, created_at FROM event_logs
                WHERE event_type = 'QUESTION_SOLVED' ORDER BY created_at DESC LIMIT 50
            """) as c:
                async for row in c:
                    details = json.loads(row[2]) if row[2] else {}
                    user = await db_get_user(row[0])
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "user_id": row[0], "subject": details.get('subject', 'غير معروف'),
                                 "question": details.get('question', 'سؤال')[:60],
                                 "source": (row[1] or 'db').lower(),
                                 "time": datetime.fromtimestamp(row[3]).strftime('%Y-%m-%d %H:%M')})
            return JSONResponse({"title": "📝 إجمالي الأسئلة", "count": len(rows), "type": "questions", "data": rows})

        elif detail_type == "correct":
            rows = []
            async with conn.execute("""
                SELECT h.user_id, h.subject, h.correct_answers, h.total_questions, h.end_time
                FROM homework_sessions h WHERE h.status = 'completed' AND h.correct_answers > 0
                ORDER BY h.end_time DESC LIMIT 50
            """) as c:
                async for row in c:
                    user = await db_get_user(row[0])
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "subject": row[1] or '—', "correct": row[2] or 0, "total": row[3] or 0})
            return JSONResponse({"title": "✅ إجابات صحيحة", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "wrong":
            rows = []
            async with conn.execute("""
                SELECT h.user_id, h.subject, h.wrong_answers, h.total_questions, h.end_time
                FROM homework_sessions h WHERE h.status = 'completed' AND h.wrong_answers > 0
                ORDER BY h.wrong_answers DESC LIMIT 50
            """) as c:
                async for row in c:
                    user = await db_get_user(row[0])
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "subject": row[1] or '—', "wrong": row[2] or 0, "total": row[3] or 0})
            return JSONResponse({"title": "❌ إجابات خاطئة", "count": len(rows), "type": "table", "data": rows})

        elif detail_type == "gemini":
            rows = []
            async with conn.execute("""
                SELECT user_id, details, created_at FROM event_logs
                WHERE event_name = 'GEMINI' AND event_type = 'QUESTION_SOLVED'
                ORDER BY created_at DESC LIMIT 50
            """) as c:
                async for row in c:
                    details = json.loads(row[1]) if row[1] else {}
                    user = await db_get_user(row[0])
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "user_id": row[0], "subject": details.get('subject', 'غير معروف'),
                                 "question": details.get('question', 'سؤال'),
                                 "time": datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')})
            return JSONResponse({"title": "✨ Gemini", "count": len(rows), "type": "questions", "data": rows})

        elif detail_type == "random":
            rows = []
            async with conn.execute("""
                SELECT user_id, details, created_at FROM event_logs
                WHERE event_name = 'RANDOM' AND event_type = 'QUESTION_SOLVED'
                ORDER BY created_at DESC LIMIT 50
            """) as c:
                async for row in c:
                    details = json.loads(row[1]) if row[1] else {}
                    user = await db_get_user(row[0])
                    rows.append({"user": user.get('name', str(row[0])) if user else str(row[0]),
                                 "user_id": row[0], "subject": details.get('subject', 'غير معروف'),
                                 "question": details.get('question', 'سؤال'),
                                 "time": datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')})
            return JSONResponse({"title": "🎲 حل عشوائي", "count": len(rows), "type": "questions", "data": rows})

        elif detail_type == "errors":
            rows = []
            async with conn.execute("""
                SELECT user_id, event_name, error_message, created_at FROM event_logs
                WHERE success = 0 AND error_message IS NOT NULL
                ORDER BY created_at DESC LIMIT 50
            """) as c:
                async for row in c:
                    rows.append({"user_id": row[0], "event": row[1],
                                 "message": row[2][:80] if row[2] else '—',
                                 "time": datetime.fromtimestamp(row[3]).strftime('%Y-%m-%d %H:%M:%S')})
            return JSONResponse({"title": "⚠️ الأخطاء", "count": len(rows), "type": "errors", "data": rows})

        elif detail_type == "system":
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                data = {
                    "cpu_percent": cpu,
                    "cpu_cores": psutil.cpu_count(),
                    "mem_percent": mem.percent,
                    "mem_used_gb": round(mem.used / (1024**3), 1),
                    "mem_total_gb": round(mem.total / (1024**3), 1),
                    "disk_percent": disk.percent,
                    "disk_used_gb": round(disk.used / (1024**3), 1),
                    "disk_total_gb": round(disk.total / (1024**3), 1),
                    "active_sessions": len(active_sessions),
                }
            except ImportError:
                data = {"error": "psutil not installed"}
            return JSONResponse({"title": "💻 معلومات النظام", "count": 0, "type": "system", "data": data})

        else:
            return JSONResponse({"error": "نوع غير معروف"}, status_code=400)

    except Exception as e:
        admin_trace("DETAIL_ERR", f"{detail_type}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ==============================================================================
# Routes — Admin API (المستخدمون + طلبات الدفع)
# ==============================================================================

async def _get_bot():
    """إنشاء كائن البوت بشكل كسول داخل كل endpoint"""
    from telegram import Bot
    return Bot(token=config.bot_token)


async def _parse_admin_body(request: Request) -> dict:
    """قراءة جسم الطلب JSON بأمان — إرجاع dict فارغ عند الفشل"""
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@app.get("/api/admin/users")
async def admin_list_users(q: Optional[str] = None, filter: Optional[str] = None):
    """قائمة المستخدمين مع بحث وفلاتر (بدون كلمات المرور)"""
    try:
        users = await db_all_users()
        query = (q or "").strip().lower()
        filt = (filter or "all").strip().lower()
        now_ts = time.time()

        result = []
        for u in users:
            uid = u.get("telegram_id")

            # الاشتراك: نفس منطق is_subscribed الحالي
            is_sub = uid == config.admin_id
            expiry_ts = u.get("expiry_ts")
            if not is_sub and expiry_ts:
                try:
                    is_sub = now_ts < float(expiry_ts)
                except (ValueError, TypeError):
                    pass

            if filt == "subscribed" and not is_sub:
                continue
            if filt == "not_subscribed" and is_sub:
                continue
            if filt == "admins" and not u.get("is_admin"):
                continue

            role = u.get("role") or ""
            is_reseller_flag = role == "reseller" or bool(u.get("is_admin"))
            if filt == "resellers" and not is_reseller_flag:
                continue

            platform_user = u.get("dars360_user") or ""
            if filt == "linked" and not platform_user:
                continue
            if filt == "not_linked" and platform_user:
                continue

            if query:
                hay = "{} {} {} {}".format(uid, u.get("name") or "", u.get("tg_username") or "", platform_user).lower()
                if query not in hay:
                    continue

            last_active = u.get("last_active") or 0
            result.append({
                "id": uid,
                "name": u.get("name") or "",
                "username": u.get("tg_username") or "",
                "platform_user": platform_user or None,
                "is_subscribed": is_sub,
                "expiry_hijri": u.get("expiry_hijri") or "",
                "free_attempts": u.get("free_attempts") or 0,
                "total_hw_solved": u.get("total_hw_solved") or 0,
                "last_active": datetime.fromtimestamp(last_active).strftime('%Y-%m-%d %H:%M') if last_active else None,
                "is_admin": bool(u.get("is_admin")),
                "is_reseller": is_reseller_flag,
            })

        return {"users": result}
    except Exception as e:
        logger.error(f"admin_list_users error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/users/{user_id}")
async def admin_get_user_detail(user_id: int):
    """تفاصيل مستخدم — نفس منطق /api/user/{user_id} (كلمات المرور مموهة)"""
    try:
        data = await _user_detail_payload(user_id)
        if data is None:
            return JSONResponse({"error": "User not found"}, status_code=404)
        return data
    except Exception as e:
        logger.error(f"admin_get_user_detail error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/users/{user_id}/renew")
async def admin_renew_subscription(user_id: int, request: Request):
    """تجديد اشتراك مستخدم"""
    try:
        body = await _parse_admin_body(request)
        days = body.get("days")
        if days is None or not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            return JSONResponse({"success": False, "message": "عدد الأيام غير صالح"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import renew_subscription
        success, message = await renew_subscription(bot, user_id, days, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_renew_subscription error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/users/{user_id}/revoke")
async def admin_revoke_subscription(user_id: int, request: Request):
    """إلغاء اشتراك مستخدم"""
    try:
        bot = await _get_bot()
        from hasad_bot.admin_ops import revoke_subscription
        success, message = await revoke_subscription(bot, user_id, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_revoke_subscription error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/users/{user_id}/unlock")
async def admin_unlock_user(user_id: int, request: Request):
    """فتح قفل مستخدم"""
    try:
        bot = await _get_bot()
        from hasad_bot.admin_ops import unlock_user
        success, message = await unlock_user(bot, user_id, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_unlock_user error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/users/{user_id}/homework")
async def admin_add_homework_credit(user_id: int, request: Request):
    """إضافة رصيد واجبات لمستخدم"""
    try:
        body = await _parse_admin_body(request)
        count = body.get("count")
        kind = body.get("kind")
        if count is None or not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return JSONResponse({"success": False, "message": "العدد غير صالح"}, status_code=400)
        if kind not in ("free", "sub"):
            return JSONResponse({"success": False, "message": "النوع غير صالح"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import add_homework_credit
        success, message = await add_homework_credit(bot, user_id, count, kind)
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_add_homework_credit error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request):
    """حذف مستخدم — يتطلب تأكيد DELETE في الجسم"""
    try:
        body = await _parse_admin_body(request)
        if body.get("confirm") != "DELETE":
            return JSONResponse({"success": False, "message": "مطلوب تأكيد الحذف"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import delete_user
        success, message = await delete_user(bot, user_id, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_delete_user error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/payment-requests")
async def admin_list_payment_requests():
    """قائمة طلبات الدفع — يعيد استخدام دالة جلب الطلبات الموجودة"""
    try:
        from hasad_bot.handlers.subscriptions import get_all_payment_requests
        requests = await get_all_payment_requests()
        return {"requests": requests}
    except Exception as e:
        logger.error(f"admin_list_payment_requests error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/payment-requests/{rid}/activate")
async def admin_activate_payment_request(rid: int, request: Request):
    """تفعيل طلب دفع (إعطاء أيام اشتراك)"""
    try:
        body = await _parse_admin_body(request)
        days = body.get("days")
        if days is None or not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            return JSONResponse({"success": False, "message": "عدد الأيام غير صالح"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import approve_payment_request
        success, message = await approve_payment_request(bot, rid, days, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_activate_payment_request error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/payment-requests/{rid}/reject")
async def admin_reject_payment_request(rid: int, request: Request):
    """رفض طلب دفع مع سبب"""
    try:
        body = await _parse_admin_body(request)
        reason = body.get("reason")
        if not reason or not isinstance(reason, str):
            return JSONResponse({"success": False, "message": "سبب غير صالح"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import reject_payment_request
        success, message = await reject_payment_request(bot, rid, reason, actor="dashboard")
        return {"success": success, "message": message}
    except Exception as e:
        logger.error(f"admin_reject_payment_request error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/payment-config")
async def admin_payment_config():
    """قراءة إعدادات الدفع الحالية (خطط + بنك + STC + طرق الدفع) — للوحة التحكم"""
    try:
        from hasad_bot.database.payment_settings import get_payment_config
        return await get_payment_config()
    except Exception as e:
        logger.error(f"admin_payment_config error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/payment-config")
async def admin_update_payment_config(request: Request):
    """حفظ إعدادات الدفع — تحقق كامل من الحمولة قبل أي تطبيق، ثم تطبيق تدريجي"""
    try:
        body = await _parse_admin_body(request)
        if body.get("confirm") is not True:
            return JSONResponse({"success": False, "message": "مطلوب تأكيد الحفظ"}, status_code=400)

        from hasad_bot.database.payment_settings import get_payment_config
        from hasad_bot.admin_ops import update_plan_config, update_payment_settings_op

        current = await get_payment_config()
        known_plans = current.get("plans", {})

        # ---- التحقق من الخطط أولاً (قبل أي تطبيق) ----
        plans_body = body.get("plans") or {}
        if not isinstance(plans_body, dict):
            return JSONResponse({"success": False, "message": "بيانات الخطط غير صالحة"}, status_code=400)

        plan_updates: Dict[str, dict] = {}
        for plan_id, fields in plans_body.items():
            if plan_id not in known_plans:
                return JSONResponse({"success": False, "message": f"الخطة '{plan_id}' غير موجودة"}, status_code=400)
            if not isinstance(fields, dict):
                return JSONResponse({"success": False, "message": f"بيانات الخطة '{plan_id}' غير صالحة"}, status_code=400)
            for key, value in fields.items():
                if key == "is_active":
                    if not isinstance(value, bool):
                        return JSONResponse({"success": False, "message": f"قيمة التفعيل للخطة '{plan_id}' غير صالحة"}, status_code=400)
                elif key == "price":
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(float(value)) or float(value) < 0):
                        return JSONResponse({"success": False, "message": f"سعر الخطة '{plan_id}' غير صالح"}, status_code=400)
                elif key in ("days", "max_homeworks", "stars"):
                    if (isinstance(value, bool) or not isinstance(value, int)
                            or not math.isfinite(float(value)) or value < 0):
                        return JSONResponse({"success": False, "message": f"قيمة '{key}' للخطة '{plan_id}' غير صالحة"}, status_code=400)
                else:
                    return JSONResponse({"success": False, "message": f"مفتاح غير صالح للخطة '{plan_id}': {key}"}, status_code=400)
            if fields:
                plan_updates[plan_id] = fields

        # ---- التحقق من بيانات الدفع (بنك + STC + طرق) قبل أي تطبيق ----
        text_map = {
            "bank_name": "اسم البنك", "bank_account_name": "اسم المستفيد",
            "bank_account_number": "رقم الحساب", "bank_iban": "الآيبان",
            "stc_phone": "رقم الجوال", "stc_notes": "ملاحظات",
        }
        method_map = {"bank": "payment_method_bank", "stc": "payment_method_stc", "stars": "payment_method_stars"}
        settings_fields: Dict[str, object] = {}

        for section in ("bank", "stc"):
            section_data = body.get(section) or {}
            if not isinstance(section_data, dict):
                return JSONResponse({"success": False, "message": f"بيانات القسم '{section}' غير صالحة"}, status_code=400)
            for key, value in section_data.items():
                if key not in text_map:
                    return JSONResponse({"success": False, "message": f"مفتاح غير صالح: {key}"}, status_code=400)
                if not isinstance(value, str) or not value.strip():
                    return JSONResponse({"success": False, "message": f"{text_map[key]} مطلوب"}, status_code=400)
                if len(value) > 200:
                    return JSONResponse({"success": False, "message": f"{text_map[key]} يجب ألا يتجاوز 200 حرف"}, status_code=400)
                settings_fields[key] = value

        methods_data = body.get("methods") or {}
        if not isinstance(methods_data, dict):
            return JSONResponse({"success": False, "message": "بيانات طرق الدفع غير صالحة"}, status_code=400)
        for key, value in methods_data.items():
            if key not in method_map:
                return JSONResponse({"success": False, "message": f"طريقة دفع غير صالحة: {key}"}, status_code=400)
            if not isinstance(value, bool):
                return JSONResponse({"success": False, "message": f"قيمة طريقة الدفع '{key}' غير صالحة"}, status_code=400)
            settings_fields[method_map[key]] = value

        # ---- التطبيق: الخطط أولاً (توقف عند أول فشل) ثم بيانات الدفع ----
        for plan_id, fields in plan_updates.items():
            ok, message = await update_plan_config(plan_id, fields, actor_uid=config.admin_id, actor_name="dashboard")
            if not ok:
                return JSONResponse({"success": False, "message": message}, status_code=400)

        if settings_fields:
            ok, message = await update_payment_settings_op(settings_fields, actor_uid=config.admin_id, actor_name="dashboard")
            if not ok:
                return JSONResponse({"success": False, "message": message}, status_code=400)

        return {"success": True, "message": "تم حفظ إعدادات الدفع"}
    except Exception as e:
        logger.error(f"admin_update_payment_config error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


# ==============================================================================
# Routes — Admin API (البث + الإعلانات)
# ==============================================================================

BROADCAST_TARGETS = ("all", "subscribed", "not_subscribed", "linked", "not_linked")


async def _announcement_type_exists(atype: str) -> bool:
    """التحقق من أن نوع الإعلان معروف ضمن القوالب (بعد ضمان الجداول)"""
    from hasad_bot.handlers.announcements import ensure_announcement_tables, get_all_templates
    await ensure_announcement_tables()
    templates = await get_all_templates()
    return any(t.get("type") == atype for t in templates)


@app.get("/api/admin/broadcast/preview")
async def admin_broadcast_preview(target: str = "all"):
    """معاينة فئة البث: اسم الفئة + العدد + عينة من الأسماء"""
    try:
        if target not in BROADCAST_TARGETS:
            return JSONResponse({"success": False, "message": "الفئة غير صالحة"}, status_code=400)
        from hasad_bot.database import get_users_count_by_target, get_users_by_target, get_target_name
        count = await get_users_count_by_target(target)
        ids = await get_users_by_target(target)
        sample = []
        for uid in ids[:10]:
            user = await db_get_user(uid)
            sample.append((user or {}).get("name") or f"ID: {uid}")
        return {
            "target": target,
            "target_name": get_target_name(target),
            "count": count,
            "sample": sample,
        }
    except Exception as e:
        logger.error(f"admin_broadcast_preview error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/broadcast")
async def admin_broadcast(request: Request):
    """إرسال بث نصي لكل مستخدمي الفئة (يتطلب تأكيد)"""
    try:
        body = await _parse_admin_body(request)
        if body.get("confirm") is not True:
            return JSONResponse({"success": False, "message": "مطلوب تأكيد البث"}, status_code=400)
        target = (body.get("target") or "").strip()
        text = body.get("text")
        if target not in BROADCAST_TARGETS:
            return JSONResponse({"success": False, "message": "الفئة غير صالحة"}, status_code=400)
        if not isinstance(text, str) or not text.strip():
            return JSONResponse({"success": False, "message": "نص البث مطلوب"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import start_broadcast
        job_id = await start_broadcast(bot, target, text, actor="dashboard")
        return {"success": True, "job_id": job_id}
    except Exception as e:
        logger.error(f"admin_broadcast error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/broadcast/jobs/{job_id}")
async def admin_broadcast_job(job_id: str):
    """حالة مهمة بث/إعلان من مخزن المهام"""
    try:
        from hasad_bot.admin_ops import get_send_job
        job = get_send_job(job_id)
        if job is None:
            return JSONResponse({"error": "المهمة غير موجودة"}, status_code=404)
        return job
    except Exception as e:
        logger.error(f"admin_broadcast_job error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/announcements")
async def admin_list_announcements():
    """قائمة قوالب الإعلانات"""
    try:
        from hasad_bot.handlers.announcements import ensure_announcement_tables, get_all_templates
        await ensure_announcement_tables()
        templates = await get_all_templates()
        return {"templates": templates}
    except Exception as e:
        logger.error(f"admin_list_announcements error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/announcements/{atype}/toggle")
async def admin_toggle_announcement(atype: str, request: Request):
    """تفعيل/تعطيل قالب إعلان"""
    try:
        body = await _parse_admin_body(request)
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return JSONResponse({"success": False, "message": "القيمة غير صالحة"}, status_code=400)
        if not await _announcement_type_exists(atype):
            return JSONResponse({"error": "النوع غير معروف"}, status_code=404)
        from hasad_bot.handlers.announcements import set_template_enabled
        await set_template_enabled(atype, enabled)
        from hasad_bot.database.auth import log_admin_action
        await log_admin_action(0, "dashboard", "ANNOUNCEMENT_TOGGLE", details=f"atype={atype} enabled={enabled}")
        return {"success": True, "enabled": enabled}
    except Exception as e:
        logger.error(f"admin_toggle_announcement error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/announcements/{atype}/text")
async def admin_update_announcement_text(atype: str, request: Request):
    """تعديل نص قالب الإعلان"""
    try:
        body = await _parse_admin_body(request)
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return JSONResponse({"success": False, "message": "النص مطلوب"}, status_code=400)
        if not await _announcement_type_exists(atype):
            return JSONResponse({"error": "النوع غير معروف"}, status_code=404)
        from hasad_bot.handlers.announcements import update_template_text
        await update_template_text(atype, text)
        from hasad_bot.database.auth import log_admin_action
        await log_admin_action(0, "dashboard", "ANNOUNCEMENT_TEXT", details=f"atype={atype} len={len(text)}")
        return {"success": True}
    except Exception as e:
        logger.error(f"admin_update_announcement_text error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/announcements/{atype}/preview")
async def admin_preview_announcement(atype: str):
    """معاينة إعلان قبل الإرسال"""
    try:
        if not await _announcement_type_exists(atype):
            return JSONResponse({"error": "النوع غير معروف"}, status_code=404)
        from hasad_bot.handlers.announcements import preview_announcement
        return await preview_announcement(atype)
    except Exception as e:
        logger.error(f"admin_preview_announcement error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/announcements/{atype}/send")
async def admin_send_announcement(atype: str):
    """إرسال إعلان يدوياً الآن"""
    try:
        if not await _announcement_type_exists(atype):
            return JSONResponse({"error": "النوع غير معروف"}, status_code=404)
        from hasad_bot.handlers.announcements import get_template
        tpl = await get_template(atype)
        if tpl and not tpl["enabled"]:
            return JSONResponse({"success": False, "message": "القالب معطّل — فعّله أولاً"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import start_announcement_send
        job_id = await start_announcement_send(bot, atype, actor="dashboard")
        return {"success": True, "job_id": job_id}
    except Exception as e:
        logger.error(f"admin_send_announcement error: {e}")
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


# ==============================================================================
# Routes — Admin API (الدعم + اللوجات + النسخ الاحتياطي)
# ==============================================================================

@app.get("/api/admin/support")
async def admin_support_conversations(status: str = "all", q: Optional[str] = None):
    """قائمة محادثات الدعم مع حالة وفلترة (بحث بالاسم أو المعرّف)"""
    try:
        if status not in ("all", "open", "closed"):
            return JSONResponse({"success": False, "message": "حالة غير صالحة"}, status_code=400)
        from hasad_bot.admin_ops import get_support_conversations
        conversations = await get_support_conversations(status=status, limit=100, q=q or "")
        return {"conversations": conversations}
    except Exception:
        logger.error("admin_support_conversations error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/support/{user_id}")
async def admin_support_history(user_id: int):
    """سجل محادثة دعم لمستخدم — معلومات آمنة فقط (بدون كلمات المرور)"""
    try:
        user = await db_get_user(user_id)
        safe_user = None
        if user:
            now_ts = time.time()
            is_sub = user_id == config.admin_id
            expiry_ts = user.get("expiry_ts")
            if not is_sub and expiry_ts:
                try:
                    is_sub = now_ts < float(expiry_ts)
                except (TypeError, ValueError):
                    pass
            last_active = user.get("last_active") or 0
            safe_user = {
                "id": user["telegram_id"],
                "name": user.get("name") or "",
                "username": user.get("tg_username") or "",
                "platform_user": user.get("dars360_user") or None,
                "is_subscribed": is_sub,
                "expiry_hijri": user.get("expiry_hijri") or "",
                "free_attempts": user.get("free_attempts") or 0,
                "total_hw_solved": user.get("total_hw_solved") or 0,
                "last_active": datetime.fromtimestamp(last_active).strftime('%Y-%m-%d %H:%M') if last_active else None,
                "is_admin": bool(user.get("is_admin")),
                "is_reseller": bool(user.get("is_admin")) or user.get("role") == "reseller",
            }
        from hasad_bot.admin_ops import get_support_history
        history = await get_support_history(user_id, limit=50)
        return {"user": safe_user, "history": history}
    except Exception:
        logger.error("admin_support_history error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/support/{user_id}/reply")
async def admin_support_reply(user_id: int, request: Request):
    """إرسال رد دعم لمستخدم"""
    try:
        body = await _parse_admin_body(request)
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return JSONResponse({"success": False, "message": "نص الرد مطلوب"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import OperationBlocked, send_support_reply
        success, message = await send_support_reply(bot, user_id, text, actor="dashboard")
        return {"success": success, "message": message}
    except OperationBlocked as e:
        return JSONResponse({"success": False, "message": f"{e}"}, status_code=403)
    except Exception:
        logger.error("admin_support_reply error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/logs")
async def admin_log_files():
    """قائمة ملفات اللوجات المتاحة (أسماء فقط — بدون مسارات)"""
    try:
        from hasad_bot.admin_ops import LOG_FILE_ALLOWLIST
        return {"files": list(LOG_FILE_ALLOWLIST.keys())}
    except Exception:
        logger.error("admin_log_files error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/logs/audit")
async def admin_audit_log(q: Optional[str] = None, action: Optional[str] = None,
                          limit: int = 100, after: Optional[float] = None, before: Optional[float] = None):
    """سجل إجراءات المشرفين (مع فلاتر بحث وفترة زمنية)"""
    try:
        if limit <= 0 or limit > 500:
            return JSONResponse({"success": False, "message": "الحد غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import get_admin_audit
        entries = await get_admin_audit(q=q or "", action=action or "", limit=limit, after=after, before=before)
        return {"entries": entries}
    except Exception:
        logger.error("admin_audit_log error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/logs/user/{uid}")
async def admin_user_log(uid: str, limit: int = 100, step: Optional[str] = None):
    """سجل تفاعلات مستخدم من اللوجات الداخلية"""
    try:
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            return JSONResponse({"success": False, "message": "معرّف المستخدم غير صالح"}, status_code=400)
        if limit <= 0 or limit > 1000:
            return JSONResponse({"success": False, "message": "الحد غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import get_user_log
        return await get_user_log(uid_int, limit=limit, step_filter=step)
    except Exception:
        logger.error("admin_user_log error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/logs/{name}")
async def admin_read_log(name: str, offset: int = 0, limit: int = 200, tail: bool = False):
    """قراءة ملف لوج من القائمة المسموحة فقط"""
    try:
        if offset < 0:
            return JSONResponse({"success": False, "message": "الإزاحة غير صالحة"}, status_code=400)
        if limit <= 0 or limit > 1000:
            return JSONResponse({"success": False, "message": "الحد غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import OperationBlocked, read_log_file
        result = await read_log_file(name=name, offset=offset, limit=limit, tail=tail)
        return result
    except OperationBlocked as e:
        return JSONResponse({"success": False, "message": f"{e}"}, status_code=403)
    except Exception:
        logger.error("admin_read_log error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/backup")
async def admin_run_backup(request: Request):
    """تشغيل نسخة احتياطية (قاعدة بيانات / سيرة ذاتية / سجلات إدارة)"""
    try:
        body = await _parse_admin_body(request)
        kind = body.get("kind")
        if kind not in ("db", "cv", "admin_logs"):
            return JSONResponse({"success": False, "message": "نوع النسخة الاحتياطية غير صالح"}, status_code=400)
        bot = await _get_bot()
        from hasad_bot.admin_ops import OperationBlocked, run_backup
        success, message = await run_backup(bot, kind, actor="dashboard")
        if not success and "تصدير آخر" in message:
            return JSONResponse({"success": success, "message": message}, status_code=409)
        return {"success": success, "message": message}
    except OperationBlocked as e:
        return JSONResponse({"success": False, "message": f"{e}"}, status_code=403)
    except Exception:
        logger.error("admin_run_backup error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


# ==============================================================================
# Bot Control / Admins / Resellers API (عبر shared services في admin_ops)
# ==============================================================================

@app.get("/api/admin/status")
async def admin_bot_status():
    """حالة البوت (تجميد / وضع عام / آخر إحصائيات)"""
    try:
        from hasad_bot.admin_ops import get_bot_status
        return await get_bot_status()
    except Exception:
        logger.error("admin_bot_status error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/system/freeze")
async def admin_set_bot_frozen(request: Request):
    """تجميد / إلغاء تجميد البوت"""
    try:
        body = await _parse_admin_body(request)
        frozen = body.get("frozen")
        if not isinstance(frozen, bool):
            return JSONResponse({"success": False, "message": "القيمة غير صالحة"}, status_code=400)
        from hasad_bot.admin_ops import set_bot_frozen_state
        success, message = await set_bot_frozen_state(frozen, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_set_bot_frozen error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/system/mode")
async def admin_set_public_mode(request: Request):
    """تفعيل / تعطيل الوضع العام للبوت"""
    try:
        body = await _parse_admin_body(request)
        public = body.get("public")
        if not isinstance(public, bool):
            return JSONResponse({"success": False, "message": "القيمة غير صالحة"}, status_code=400)
        from hasad_bot.admin_ops import set_public_mode_state
        success, message = await set_public_mode_state(public, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_set_public_mode error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/admins")
async def admin_list_admins():
    """قائمة الأدمنز"""
    try:
        from hasad_bot.admin_ops import list_admins
        success, admins, message = await list_admins(actor_uid=config.admin_id)
        if not success:
            return JSONResponse({"success": False, "message": message}, status_code=403)
        return {"admins": admins, "success": True}
    except Exception:
        logger.error("admin_list_admins error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/admins")
async def admin_add_admin(request: Request):
    """ترقية مستخدم إلى أدمن"""
    try:
        body = await _parse_admin_body(request)
        user_id = body.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return JSONResponse({"success": False, "message": "معرّف المستخدم غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import add_admin
        success, message = await add_admin(user_id, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_add_admin error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.delete("/api/admin/admins/{uid}")
async def admin_delete_admin(uid: int, request: Request):
    """إزالة أدمن — يتطلب تأكيد DELETE في الجسم"""
    try:
        body = await _parse_admin_body(request)
        if body.get("confirm") != "DELETE":
            return JSONResponse({"success": False, "message": "مطلوب تأكيد الحذف"}, status_code=400)
        from hasad_bot.admin_ops import delete_admin
        success, message = await delete_admin(uid, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_delete_admin error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/admins/{uid}/credit")
async def admin_charge_admin_credit(uid: int, request: Request):
    """شحن رصيد أدمن"""
    try:
        body = await _parse_admin_body(request)
        amount = body.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return JSONResponse({"success": False, "message": "المبلغ غير صالح"}, status_code=400)
        if amount < 0 or not math.isfinite(amount):
            return JSONResponse({"success": False, "message": "المبلغ غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import charge_admin_credit
        success, message = await charge_admin_credit(uid, amount, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_charge_admin_credit error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/resellers")
async def admin_list_resellers():
    """قائمة الموزعين"""
    try:
        from hasad_bot.admin_ops import list_resellers
        success, resellers, message = await list_resellers(actor_uid=config.admin_id)
        if not success:
            return JSONResponse({"success": False, "message": message}, status_code=403)
        return {"resellers": resellers}
    except Exception:
        logger.error("admin_list_resellers error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/resellers")
async def admin_add_reseller(request: Request):
    """إضافة موزع"""
    try:
        body = await _parse_admin_body(request)
        user_id = body.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return JSONResponse({"success": False, "message": "معرّف المستخدم غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import add_reseller
        success, message = await add_reseller(user_id, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_add_reseller error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/resellers/{uid}/credit")
async def admin_add_reseller_credit(uid: int, request: Request):
    """شحن رصيد موزع"""
    try:
        body = await _parse_admin_body(request)
        amount = body.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            return JSONResponse({"success": False, "message": "المبلغ غير صالح"}, status_code=400)
        if amount < 0 or not math.isfinite(amount):
            return JSONResponse({"success": False, "message": "المبلغ غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import add_reseller_credit_op
        success, message = await add_reseller_credit_op(uid, amount, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_add_reseller_credit error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/resellers/prices")
async def admin_set_reseller_prices(request: Request):
    """تحديد أسعار الموزعين (أسبوعي / شهري / فصل دراسي)"""
    try:
        body = await _parse_admin_body(request)
        prices = {}
        for key in ("weekly", "monthly", "semester"):
            val = body.get(key)
            if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                return JSONResponse({"success": False, "message": "الأسعار غير صالحة"}, status_code=400)
            prices[key] = val
        from hasad_bot.admin_ops import set_reseller_prices_op
        success, message = await set_reseller_prices_op(prices, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_set_reseller_prices error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/api/admin/resellers/stats")
async def admin_reseller_stats():
    """إحصائيات الموزعين"""
    try:
        from hasad_bot.admin_ops import reseller_stats_op
        success, stats, message = await reseller_stats_op(actor_uid=config.admin_id)
        if not success:
            return JSONResponse({"success": False, "message": message}, status_code=403)
        return {"success": True, "stats": stats}
    except Exception:
        logger.error("admin_reseller_stats error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.delete("/api/admin/resellers/{uid}")
async def admin_delete_reseller(uid: int, request: Request):
    """حذف موزع — يتطلب تأكيد DELETE في الجسم"""
    try:
        body = await _parse_admin_body(request)
        if body.get("confirm") != "DELETE":
            return JSONResponse({"success": False, "message": "مطلوب تأكيد الحذف"}, status_code=400)
        from hasad_bot.admin_ops import delete_reseller_op
        success, message = await delete_reseller_op(uid, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_delete_reseller error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.post("/api/admin/resellers/customers/{uid}/ban")
async def admin_ban_reseller_customer(uid: int, request: Request):
    """حظر / إيقاف عميل موزع (action: ban | stop)"""
    try:
        body = await _parse_admin_body(request)
        action = body.get("action")
        if action not in ("ban", "stop"):
            return JSONResponse({"success": False, "message": "الإجراء غير صالح"}, status_code=400)
        from hasad_bot.admin_ops import ban_reseller_customer_op
        success, message = await ban_reseller_customer_op(uid, action, actor_uid=config.admin_id, actor_name="dashboard")
        return {"success": success, "message": message}
    except Exception:
        logger.error("admin_ban_reseller_customer error", exc_info=True)
        return JSONResponse({"success": False, "message": "حدث خطأ داخلي"}, status_code=500)


@app.get("/test-db")
async def test_database(request: Request, _user: str = Depends(require_auth)):
    result = {
        "status": "unknown",
        "db_path": str(config.db_file),
        "db_exists": os.path.exists(config.db_file),
    }
    if result["db_exists"]:
        result["db_size_kb"] = round(os.path.getsize(config.db_file) / 1024, 2)
    try:
        conn = await _db_pool.get_connection()
        async with conn.execute("SELECT COUNT(*) FROM users") as c:
            result["users_count"] = (await c.fetchone())[0] or 0
            result["status"] = "connected"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return JSONResponse(result)


# ==============================================================================
# WebSocket
# ==============================================================================

@app.get("/api/live")
async def api_live(request: Request):
    """نفس حمولة الـ WebSocket عبر REST — fallback للمتصفحات التي تحجب ws"""
    try:
        return await get_dashboard_data()
    except Exception as e:
        logger.error(f"api_live error: {e}")
        return JSONResponse({"error": "حدث خطأ داخلي"}, status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # التحقق من الجلسة قبل السماح بالاتصال (نفس منطق IP الخاص بـ auth)
    token = websocket.cookies.get(COOKIE_NAME)
    forwarded = websocket.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        real_ip = websocket.headers.get("X-Real-IP")
        ip = real_ip if real_ip else (websocket.client.host if websocket.client else "unknown")
    payload = auth_manager.verify_session_token(token, ip)
    if not payload:
        logger.warning(f"WebSocket auth rejected: ip={ip}, token_present={bool(token)}")
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            data = await get_dashboard_data()
            try:
                await websocket.send_json(data)
            except Exception:
                # العميل انقطع — أخرج من الحلقة بهدوء
                break
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        admin_trace("WEBSOCKET_ERR", str(e))
    finally:
        manager.disconnect(websocket)


# ==============================================================================
# Helper Functions
# ==============================================================================

async def is_subscribed(uid: int) -> bool:
    if uid == config.admin_id:
        return True
    user = await db_get_user(uid)
    if not user:
        return False
    try:
        expiry = user.get("expiry_ts")
        if expiry:
            return time.time() < float(expiry)
    except (ValueError, TypeError):
        pass
    return False


async def get_recent_questions(limit: int = 10):
    try:
        conn = await _db_pool.get_connection()
        questions = []
        async with conn.execute("""
            SELECT user_id, event_name, details, created_at FROM event_logs
            WHERE event_type = 'QUESTION_SOLVED'
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)) as c:
            async for row in c:
                user_id, event_name, details_json, created_at = row
                details = json.loads(details_json) if details_json else {}
                user = await db_get_user(user_id)
                questions.append({
                    "text": details.get('question', 'سؤال')[:50] + "...",
                    "user": user.get('name', str(user_id)) if user else str(user_id),
                    "subject": details.get('subject', 'غير معروف'),
                    "answer": "✓",
                    "source": (event_name or 'db').lower(),
                    "time": datetime.fromtimestamp(created_at).strftime('%H:%M:%S')
                })
        return questions
    except Exception as e:
        admin_trace("QUESTIONS_FETCH", str(e))
        return []


async def get_recent_errors(limit: int = 10):
    try:
        conn = await _db_pool.get_connection()
        errors = []
        async with conn.execute("""
            SELECT user_id, event_name, error_message, created_at FROM event_logs
            WHERE success = 0 AND error_message IS NOT NULL
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)) as c:
            async for row in c:
                errors.append({
                    "user_id": row[0],
                    "event": row[1],
                    "message": (row[2][:50] + "...") if row[2] and len(row[2]) > 50 else (row[2] or ''),
                    "time": datetime.fromtimestamp(row[3]).strftime('%H:%M:%S')
                })
        return errors
    except Exception as e:
        admin_trace("ERRORS_FETCH", str(e))
        return []


# ==============================================================================
# Dashboard Data Aggregator
# ==============================================================================

# ✅ L1 Cache — لتخفيف الحمل عن DB (WebSocket يسأل كل 3s)
_DASHBOARD_CACHE = {"data": None, "ts": 0.0}
_DASHBOARD_TTL = config.dashboard_cache_ttl

async def get_dashboard_data():
    # ✅ L1 TTL Cache: WebSocket يستدعي كل 3 ثوانٍ — نخفف الحمل
    global _DASHBOARD_CACHE
    now = time.time()
    if _DASHBOARD_CACHE["data"] is not None and (now - _DASHBOARD_CACHE["ts"]) < _DASHBOARD_TTL:
        return _DASHBOARD_CACHE["data"]

    try:
        conn = await _db_pool.get_connection()
        now_ts = time.time()
        today_start = now_ts - (now_ts % 86400)
        five_min_ago = now_ts - 300

        # Users stats
        async with conn.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0] or 0
        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (five_min_ago,)) as c:
            active_now_db = (await c.fetchone())[0] or 0
        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (today_start,)) as c:
            active_today = (await c.fetchone())[0] or 0
        async with conn.execute("SELECT COUNT(*) FROM users WHERE expiry_ts > ?", (now_ts,)) as c:
            subscribers = (await c.fetchone())[0] or 0
        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE (free_attempts = 0 OR free_attempts IS NULL) AND (expiry_ts IS NULL OR expiry_ts < ?)
        """, (now_ts,)) as c:
            finished_free = (await c.fetchone())[0] or 0
        async with conn.execute("SELECT SUM(free_attempts) FROM users WHERE free_attempts > 0") as c:
            remaining_free = (await c.fetchone())[0] or 0
        async with conn.execute("SELECT SUM(total_hw_solved) FROM users") as c:
            total_hw = (await c.fetchone())[0] or 0

        # Homework sessions
        async with conn.execute("""
            SELECT SUM(solved_questions), SUM(correct_answers), SUM(wrong_answers)
            FROM homework_sessions WHERE status = 'completed'
        """) as c:
            row = await c.fetchone()
            total_questions_solved = (row[0] or 0) if row else 0
            total_correct = (row[1] or 0) if row else 0
            total_wrong = (row[2] or 0) if row else 0

        # Solved questions sources
        try:
            async with conn.execute("SELECT COUNT(*) FROM solved_questions") as c:
                total_questions = (await c.fetchone())[0] or 0
            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'db'") as c:
                db_hits = (await c.fetchone())[0] or 0
            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'groq'") as c:
                groq = (await c.fetchone())[0] or 0
            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'gemini'") as c:
                gemini = (await c.fetchone())[0] or 0
            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'random'") as c:
                random_count = (await c.fetchone())[0] or 0
        except Exception:
            total_questions = db_hits = groq = gemini = random_count = 0

        # Errors
        async with conn.execute("SELECT COUNT(*) FROM event_logs WHERE success = 0") as c:
            total_errors = (await c.fetchone())[0] or 0

        # Recent data
        recent_questions = await get_recent_questions(10)
        recent_errors = await get_recent_errors(10)

        # Active sessions
        active_users = []
        for uid, session in active_sessions.items():
            user = await db_get_user(uid)
            if user:
                if getattr(session, 'is_paused', False):
                    st, stc = "⏸ متوقف", "warning"
                    act = f"متوقف (واجب {getattr(session,'stats',{}).get('total_hw',0)})"
                elif getattr(session, 'is_running', False):
                    st, stc = "▶️ يحل", "success"
                    act = f"يحل واجب {getattr(session,'stats',{}).get('total_hw',0)} | أسئلة {getattr(session,'stats',{}).get('solved_q',0)}"
                else:
                    st, stc = "🟢 متصل", "info"
                    act = "متصل"
                active_users.append({
                    "id": uid, "name": user.get('name', f'User {uid}'),
                    "status": st, "status_class": stc,
                    "current_action": act, "time": "الآن", "details": {}
                })

        # Subscriptions
        subscriptions = []
        async with conn.execute("""
            SELECT telegram_id, name, expiry_ts, expiry_hijri, total_hw_solved
            FROM users WHERE expiry_ts > ? ORDER BY expiry_ts ASC LIMIT 20
        """, (now_ts,)) as c:
            async for row in c:
                try:
                    days_left = int((float(row[2]) - now_ts) / 86400) if row[2] else 0
                except (ValueError, TypeError):
                    days_left = 0
                subscriptions.append({
                    "id": row[0], "name": row[1] or f"ID: {row[0]}",
                    "expiry": row[3] or '—', "days_left": days_left, "total_hw": row[4] or 0
                })

        # All users
        users = []
        async with conn.execute("""
            SELECT telegram_id, name, tg_username, dars360_user,
                   expiry_ts, expiry_hijri, free_attempts, total_hw_solved,
                   rank_title, last_active, created_at
            FROM users ORDER BY created_at DESC LIMIT 50
        """) as c:
            async for row in c:
                try:
                    is_sub = float(row[4]) > now_ts if row[4] else False
                except (ValueError, TypeError):
                    is_sub = False
                la = ""
                if row[9]:
                    try: la = datetime.fromtimestamp(float(row[9])).strftime('%H:%M')
                    except: la = "—"
                users.append({
                    "id": row[0], "name": row[1] or f"User {row[0]}",
                    "tg_username": row[2] or '—', "platform_user": row[3] or '—',
                    "is_subscribed": is_sub, "expiry": row[5] or '—',
                    "free_attempts": row[6] or 0, "total_hw": row[7] or 0,
                    "rank_title": row[8] or '🥉 طالب جديد',
                    "last_active": la, "is_online": row[0] in active_sessions
                })

        # System metrics
        try:
            import psutil
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory().percent
        except ImportError:
            cpu = memory = 0

        # Activity chart (24h)
        activity_labels, activity_data = [], []
        for i in range(24):
            h_start = now_ts - (i * 3600)
            h_end = h_start + 3600
            async with conn.execute("""
                SELECT COUNT(DISTINCT user_id) FROM event_logs WHERE created_at BETWEEN ? AND ?
            """, (h_start, h_end)) as c:
                cnt = (await c.fetchone())[0] or 0
                activity_labels.insert(0, f"{23-i}:00")
                activity_data.insert(0, cnt)

        result = {
            "stats": {
                "total_users": total_users, "active_now": len(active_sessions),
                "active_today": active_today, "subscribers": subscribers,
                "finished_free": finished_free, "remaining_free": remaining_free,
                "total_hw": total_hw, "total_questions_solved": total_questions_solved,
                "total_questions": total_questions, "total_correct": total_correct,
                "total_wrong": total_wrong, "total_errors": total_errors,
                "db_hits": db_hits, "groq": groq, "gemini": gemini,
                "random": random_count, "cpu": cpu, "memory": memory
            },
            "api_stats": {"groq": groq, "gemini": gemini, "db_hits": db_hits, "random": random_count},
            "users": users, "active_users": active_users,
            "recent_questions": recent_questions, "recent_errors": recent_errors,
            "subscriptions": subscriptions,
            "activity_labels": activity_labels, "activity_data": activity_data
        }
        # ✅ حفظ في الـ cache
        _DASHBOARD_CACHE["data"] = result
        _DASHBOARD_CACHE["ts"] = time.time()
        return result

    except Exception as e:
        admin_trace("DASHBOARD_ERR", str(e))
        result = {
            "stats": {
                "total_users":0,"active_now":0,"active_today":0,"subscribers":0,
                "finished_free":0,"remaining_free":0,"total_hw":0,"total_questions_solved":0,
                "total_questions":0,"total_correct":0,"total_wrong":0,"total_errors":0,
                "db_hits":0,"groq":0,"gemini":0,"random":0,"cpu":0,"memory":0
            },
            "api_stats":{"groq":0,"gemini":0,"db_hits":0,"random":0},
            "users":[],"active_users":[],"recent_questions":[],"recent_errors":[],
            "subscriptions":[],"activity_labels":[],"activity_data":[]
        }
        # ❌ لا نخزّن الفشل في الـ cache
        return result


# ==============================================================================
# Entrypoint
# ==============================================================================

def find_working_port(preferred_port: int, fallbacks: Optional[List[int]] = None) -> int:
    """
    يجد منفذاً متاحاً للـ dashboard.
    يفضّل المنفذ المطلوب، لكن لو محجوز (Windows permission أو مشغول)
    يجرب المنافذ البديلة.
    """
    if fallbacks is None:
        fallbacks = [8765, 9876, 9999, 15000, 18000]

    candidates = [preferred_port] + [p for p in fallbacks if p != preferred_port]

    for port in candidates:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            # نتأكد أولاً إن المنفذ مشغول أصلاً
            in_use = sock.connect_ex(("127.0.0.1", port)) == 0
            if in_use:
                # في عملية أخرى تخدم — لا نستعمله (خلّيها ترجع)
                continue
        except Exception:
            pass
        finally:
            sock.close()

        # نجرّب الربط الفعلي — هذا اللي يكشف WinError 10013
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(0.3)
        try:
            test_sock.bind(("127.0.0.1", port))
            test_sock.close()
            if port != preferred_port:
                print(f"⚠️ المنفذ {preferred_port} محجوز، تم التحويل إلى {port}")
            return port
        except (OSError, PermissionError):
            # المنفذ محجوز — جرّب التالي
            continue
        finally:
            try:
                test_sock.close()
            except Exception:
                pass

    # ما لقينا ولا منفذ — نرجّع المفضّل وندع البوت يحاول ويسجل الخطأ
    print(f"❌ لم يُعثر على منفذ متاح (جرّبنا: {candidates})")
    return preferred_port


def start_dashboard():
    port = find_working_port(config.dashboard_port)
    print(f"🌐 Dashboard starting on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)

if __name__ == "__main__":
    start_dashboard()
