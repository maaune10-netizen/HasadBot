

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

    /* ===== Clock ===== */
    function updateTime() {
        const now = new Date();
        document.getElementById('current-time').textContent =
            now.toLocaleString('ar-SA', { timeZone:'Asia/Riyadh', dateStyle:'full', timeStyle:'medium' });
    }
    setInterval(updateTime, 1000);
    updateTime();
    