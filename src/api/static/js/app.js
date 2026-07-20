/**
 * app.js - 应用初始化、导航切换、智能问答、自动登录
 */

// ===== 所有ECharts实例引用（用于resize） =====
function getAllCharts() {
    return [echartsStructure, echartsContract, echartsLevel, echartsTrend,
        echartsOvertimeCenter, echartsOvertimeDept, echartsCostAnalysis];
}

// ===== 应用显示 =====
function showApp() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('appPage').style.display = '';
    document.getElementById('userName').textContent = currentUser.display_name;
    document.getElementById('userRole').textContent = currentUser.role;
    document.getElementById('userAvatar').textContent = currentUser.display_name.charAt(0);

    // 计算用户scope（只算一次，缓存到_scopeCache）
    _scopeCache = _calcUserScope();
    console.log('[ShowApp] scope计算完成:', JSON.stringify(_scopeCache));

    // loadKPI会填充筛选器选项，完成后应用锁定并重新加载数据
    loadKPI().then(() => {
        updateFilterLocks();  // 设置值+锁定
        // 自动选中默认月份（解决部门经理登录后月份为空导致显示全公司数据的问题）
        applyDefaultMonth();

        // 手动触发一次 emp_type 变化，刷新数据（解决筛选器值在 loadKPI 请求后才设置的问题）
        // 先切到"白领"再切回"全部"，确保数据按用户管辖范围正确加载
        const empTypeSel = document.getElementById('filterEmpType');
        if (empTypeSel && empTypeSel.options.length > 1) {
            // 先切到"白领"触发刷新（无论当前是什么值）
            empTypeSel.value = '白领';
            empTypeSel.dispatchEvent(new Event('change'));
            // 短暂延迟后切回"全部"
            setTimeout(() => {
                empTypeSel.value = '';
                empTypeSel.dispatchEvent(new Event('change'));
            }, 100);
        }

        loadCharts(); loadEfficiency(); loadOvertime(); loadDeptDetail(); loadCostAnalysis();
    });

    loadTickets(); loadNotifications(); loadProfile();
}

// ===== Tab导航切换 =====
function switchTab(tabName) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('page-' + tabName).classList.add('active');
    document.querySelector(`.nav-tab[data-tab="${tabName}"]`).classList.add('active');
    // ECharts charts need resize after page switch
    setTimeout(() => {
        getAllCharts().forEach(c => { if (c) c.resize(); });
    }, 100);
}

// ===== 智能问答 =====
async function sendChat() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    const messages = document.getElementById('chatMessages');
    messages.innerHTML += `<div class="chat-msg user">${msg.replace(/</g, '<')}</div>`;
    messages.innerHTML += `<div class="chat-msg bot" id="chatPending"><span class="spinner"></span> 思考中...</div>`;
    messages.scrollTop = messages.scrollHeight;
    try {
        const data = await api('POST', '/api/chat', { message: msg, source: 'web' });
        const pending = document.getElementById('chatPending');
        if (pending) pending.remove();
        messages.innerHTML += `<div class="chat-msg bot">${(data.response || '暂无回复').replace(/</g, '<').replace(/\n/g, '<br>')}</div>`;
    } catch (err) {
        const pending = document.getElementById('chatPending');
        if (pending) pending.remove();
        messages.innerHTML += `<div class="chat-msg bot" style="color:var(--accent-red);">请求失败：${err.message}</div>`;
    }
    messages.scrollTop = messages.scrollHeight;
}

// ===== 自动登录（Session恢复） =====
(async function () {
    const saved = sessionStorage.getItem('ssc_token');
    if (saved) {
        try { currentToken = saved; const data = await api('GET', '/api/auth/me'); currentUser = data.user; showApp(); }
        catch (e) { sessionStorage.removeItem('ssc_token'); }
    }
})();