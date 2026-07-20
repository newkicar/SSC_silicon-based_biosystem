/**
 * portal_ext.js - 工单系统、通知中心、个人中心
 */

// ===== 工单系统 =====
let _ticketView = 'submitted';  // submitted=我提出的, receiver=交给我的

function switchTicketView(view) {
    _ticketView = view;
    // 更新tab样式
    document.querySelectorAll('.ticket-view-tab').forEach(tab => {
        tab.style.borderBottom = tab.dataset.view === view ? '2px solid var(--accent-blue)' : '2px solid transparent';
        tab.style.color = tab.dataset.view === view ? 'var(--accent-blue)' : 'var(--text-muted)';
    });
    loadTickets();
}

async function loadTickets() {
    try {
        const status = document.getElementById('ticketStatusFilter') ? document.getElementById('ticketStatusFilter').value : '';
        let params = [];
        if (status) params.push(`status=${status}`);
        if (_ticketView) params.push(`view=${_ticketView}`);
        const qs = params.length ? `?${params.join('&')}` : '';
        const data = await api('GET', `/api/tickets${qs}`);
        const list = document.getElementById('ticketList');
        if (!data.tickets || data.tickets.length === 0) {
            const emptyMsg = _ticketView === 'receiver' ? '暂无交给您的工单' : '暂无工单';
            list.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-muted);">${emptyMsg}</div>`;
            return;
        }
        const statusLabels = { open: '待处理', processing: '处理中', done: '✅ 已完成', cancelled: '🚫 已撤销' };
        const statusStyles = { open: '', processing: '', done: 'background:rgba(16,185,129,0.15);color:#10b981;', cancelled: 'background:rgba(239,68,68,0.15);color:#ef4444;' };
        const priorityLabels = { normal: '', high: '🔴 高', urgent: '🟠 紧急' };
        let html = '';
        data.tickets.forEach(t => {
            const sClass = t.status === 'done' ? 'done' : t.status === 'cancelled' ? 'cancelled' : t.status === 'processing' ? 'processing' : 'open';
            const prio = priorityLabels[t.priority] ? `<span style="font-size:11px;margin-left:8px;">${priorityLabels[t.priority]}</span>` : '';
            const assigneeInfo = t.assignee ? `<div style="font-size:11px;color:var(--accent-blue);margin-top:2px;">👤 处理人: ${t.assignee}</div>` : '';
            const submitterInfo = _ticketView === 'receiver' && t.submitter ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">📋 提交人: ${t.submitter}</div>` : '';

            // 操作按钮：根据视图和状态显示不同按钮
            // 按钮顺序：状态标签、详情、完成/未完成、撤销
            let actionButtons = '';

            // 详情按钮（所有视图都显示）
            actionButtons += `<button onclick="viewTicketDetail('${t.ticket_no}')" style="padding:4px 12px;font-size:11px;border:1px solid rgba(59,130,246,0.3);border-radius:6px;background:rgba(59,130,246,0.1);color:#3b82f6;cursor:pointer;white-space:nowrap;">📄 详情</button>`;

            if (_ticketView === 'submitted') {
                // 我提出的视图
                if (t.status === 'open' || t.status === 'processing') {
                    actionButtons += `<button onclick="cancelTicket('${t.ticket_no}')" style="padding:4px 12px;font-size:11px;border:1px solid rgba(239,68,68,0.3);border-radius:6px;background:rgba(239,68,68,0.1);color:#ef4444;cursor:pointer;white-space:nowrap;">🚫 撤销</button>`;
                }
            } else if (_ticketView === 'receiver') {
                // 交给我的视图
                if (t.status === 'open' || t.status === 'processing') {
                    actionButtons += `<button onclick="doneTicket('${t.ticket_no}')" style="padding:4px 12px;font-size:11px;border:1px solid rgba(16,185,129,0.3);border-radius:6px;background:rgba(16,185,129,0.1);color:#10b981;cursor:pointer;white-space:nowrap;">✅ 完成</button>`;
                    actionButtons += `<button onclick="transferTicket('${t.ticket_no}')" style="padding:4px 12px;font-size:11px;border:1px solid rgba(139,92,246,0.3);border-radius:6px;background:rgba(139,92,246,0.1);color:#8b5cf6;cursor:pointer;white-space:nowrap;">🔄 转办</button>`;
                } else if (t.status === 'done') {
                    actionButtons += `<button onclick="undoneTicket('${t.ticket_no}')" style="padding:4px 12px;font-size:11px;border:1px solid rgba(245,158,11,0.3);border-radius:6px;background:rgba(245,158,11,0.1);color:#f59e0b;cursor:pointer;white-space:nowrap;">🔄 标为未完成</button>`;
                }
            }

            html += `<div class="ticket-item">
                <div class="tk-left">
                    <div class="tk-title">${t.title}${prio}</div>
                    <div class="tk-meta">工单 #${t.ticket_no} · 提交于 ${t.created_at} · ${t.category || '一般'}</div>
                    ${assigneeInfo}
                    ${submitterInfo}
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <div class="tk-status ${sClass}" style="${statusStyles[t.status] || ''}">${statusLabels[t.status] || t.status}</div>
                    ${actionButtons}
                </div>
            </div>`;
        });
        list.innerHTML = html;
    } catch (err) { console.error('Tickets load error:', err); }
}

async function cancelTicket(ticketNo) {
    if (!confirm(`确定要撤销工单 ${ticketNo} 吗？`)) return;
    try {
        await api('POST', `/api/tickets/${ticketNo}/cancel`);
        loadTickets();
    } catch (err) { alert('撤销失败: ' + err.message); }
}

async function doneTicket(ticketNo) {
    if (!confirm(`确定要标记工单 ${ticketNo} 为已完成吗？`)) return;
    try {
        await api('POST', `/api/tickets/${ticketNo}/done`);
        loadTickets();
    } catch (err) { alert('操作失败: ' + err.message); }
}

async function undoneTicket(ticketNo) {
    if (!confirm(`确定要标记工单 ${ticketNo} 为未完成吗？`)) return;
    try {
        await api('PUT', `/api/tickets/${ticketNo}`, { status: 'processing' });
        loadTickets();
    } catch (err) { alert('操作失败: ' + err.message); }
}

async function viewTicketDetail(ticketNo) {
    try {
        const data = await api('GET', `/api/tickets/${ticketNo}`);
        if (!data.ticket) {
            alert('工单不存在');
            return;
        }
        const t = data.ticket;
        const statusLabels = { open: '待处理', processing: '处理中', done: '已完成', cancelled: '已撤销' };
        alert(
            `工单详情\n` +
            `━━━━━━━━━━━━━━━\n` +
            `工单号: ${t.ticket_no}\n` +
            `标题: ${t.title}\n` +
            `分类: ${t.category || '一般'}\n` +
            `优先级: ${t.priority || 'normal'}\n` +
            `状态: ${statusLabels[t.status] || t.status}\n` +
            `提交人: ${t.submitter || '未知'}\n` +
            `处理人: ${t.assignee || '未分配'}\n` +
            `部门: ${t.department || 'SSC'}\n` +
            `───────────────\n` +
            `详细描述:\n${t.description || '无'}`
        );
    } catch (err) {
        alert('获取工单详情失败: ' + err.message);
    }
}

function showCreateTicket() {
    const title = prompt('工单标题：');
    if (title === null) return;  // 用户点击取消
    if (!title.trim()) { alert('工单标题不能为空'); return; }

    const category = prompt('分类（薪酬/社保/合同/招聘/考勤/其他）：', '其他');
    if (category === null) return;  // 用户点击取消
    const finalCategory = category.trim() || '一般';

    const description = prompt('问题描述：', '');
    if (description === null) return;  // 用户点击取消

    const priority = prompt('优先级（normal/high/urgent）：', 'normal');
    if (priority === null) return;  // 用户点击取消
    const finalPriority = priority.trim() || 'normal';

    api('POST', '/api/tickets', {
        title: title.trim(),
        category: finalCategory,
        description: description || '',
        priority: finalPriority
    }).then(() => {
        loadTickets();
    }).catch(err => alert('创建失败: ' + err.message));
}

// ===== 通知中心 =====
let _notifFilter = 'all';  // all(全部) / unread(未读) / read(已读)
let _notifCursor = null;    // 游标（下一页的起点）
let _notifHasMore = true;   // 是否有更多数据
let _notifLoading = false;  // 是否正在加载中

function switchNotifFilter(filter) {
    _notifFilter = filter;
    _notifCursor = null;
    _notifHasMore = true;
    // 清空列表
    const list = document.getElementById('notifList');
    if (list) list.innerHTML = '';
    // 更新筛选标签样式
    document.querySelectorAll('.notif-filter-btn').forEach(btn => {
        const isActive = btn.dataset.filter === filter;
        btn.style.background = isActive ? 'var(--accent-blue)' : 'var(--bg-card)';
        btn.style.color = isActive ? '#fff' : 'var(--text-secondary)';
        btn.style.borderColor = isActive ? 'var(--accent-blue)' : 'var(--border-color)';
    });
    loadNotifications();
}

async function loadNotifications(append = false) {
    if (_notifLoading || (!_notifCursor && append && !_notifHasMore)) return;
    _notifLoading = true;

    try {
        let url = `/api/notifications?filter=${_notifFilter}&limit=50`;
        if (_notifCursor) url += `&cursor=${_notifCursor}`;

        const data = await api('GET', url);
        const list = document.getElementById('notifList');

        if (!append) {
            list.innerHTML = '';
        }

        const notifs = data.notifications || [];
        if (!append && notifs.length === 0) {
            const emptyText = _notifFilter === 'unread' ? '🎉 没有未读通知' : _notifFilter === 'read' ? '没有已读通知' : '暂无通知';
            list.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-muted);">${emptyText}</div>`;
            _notifHasMore = false;
            _notifLoading = false;
            return;
        }

        if (notifs.length > 0) {
            _notifCursor = notifs[notifs.length - 1].id;
            _notifHasMore = data.has_more || false;
        } else if (!append) {
            _notifHasMore = false;
        }

        let html = '';
        notifs.forEach(n => {
            const isRead = n.is_read === 1;
            const unreadBtn = isRead ? `<button onclick="markNotifUnread(${n.id}, this)" style="padding:2px 8px;font-size:11px;border:1px solid rgba(239,68,68,0.3);border-radius:4px;background:rgba(239,68,68,0.1);color:#ef4444;cursor:pointer;white-space:nowrap;margin-left:auto;">标记未读</button>` : '';
            html += `<div class="notif-item" style="${isRead ? 'opacity:0.6;' : ''}" onclick="markNotifRead(${n.id}, this)">
                <div class="ni-icon">${n.icon || '🔔'}</div>
                <div class="ni-body" style="display:flex;flex-direction:column;flex:1;">
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <div class="ni-title">${n.title}</div>
                        ${unreadBtn}
                    </div>
                    <div class="ni-text">${n.content}</div>
                    <div class="ni-time">${n.created_at}</div>
                    <div class="ni-tag ${n.type || 'info'}">${n.type === 'warning' ? '预警' : n.type === 'success' ? '完成' : n.type === 'info' ? '信息' : '通知'}</div>
                </div>
            </div>`;
        });

        if (append) {
            list.insertAdjacentHTML('beforeend', html);
        } else {
            list.innerHTML = html;
        }

        // 添加加载指示器
        const loaderId = 'notif-loader';
        let loader = document.getElementById(loaderId);
        if (!loader) {
            loader = document.createElement('div');
            loader.id = loaderId;
            loader.style.cssText = 'padding:15px;text-align:center;color:var(--text-muted);font-size:12px;';
            list.appendChild(loader);
        }

        if (_notifHasMore) {
            loader.textContent = '加载中...';
            loader.style.display = 'block';
        } else {
            loader.textContent = notifs.length === 0 ? '没有更多通知了' : '已加载全部通知';
            loader.style.display = 'block';
        }
    } catch (err) {
        console.error('Notifications load error:', err);
        _notifHasMore = false;
    }

    _notifLoading = false;
}

// 无限滚动：监听滚动事件
function setupInfiniteScroll() {
    const notifContainer = document.querySelector('.notif-tabs-container') || document.getElementById('notifList');
    if (!notifContainer) return;

    let scrollTimeout = null;
    notifContainer.addEventListener('scroll', () => {
        if (scrollTimeout) return;
        scrollTimeout = setTimeout(() => {
            scrollTimeout = null;
            // 判断是否滚动到底部（距离底部 < 100px）
            const { scrollTop, scrollHeight, clientHeight } = notifContainer;
            if (scrollHeight - scrollTop - clientHeight < 100 && _notifHasMore && !_notifLoading) {
                loadNotifications(true);
            }
        }, 200);
    }, { passive: true });
}

// 页面加载完成后设置无限滚动
document.addEventListener('DOMContentLoaded', setupInfiniteScroll);

async function markNotifRead(id, el) {
    try {
        await api('PUT', `/api/notifications/${id}/read`);
        if (el) el.style.opacity = '0.6';
    } catch (err) {
        console.error('[markNotifRead] failed:', err);
        alert('标记已读失败，请重试');
    }
}

async function markNotifUnread(id, btn) {
    try {
        await api('DELETE', `/api/notifications/${id}/read`);
        // 重新加载当前视图以更新状态
        loadNotifications();
    } catch (err) {
        console.error('[markNotifUnread] failed:', err);
        alert('标记未读失败，请重试');
    }
}

async function markAllNotifRead() {
    try {
        await api('PUT', '/api/notifications/read-all');
        // 保持在当前标签，重新加载当前视图
        loadNotifications();
    } catch (err) {
        alert('操作失败: ' + (err.message || '未知错误'));
    }
}

// ===== 个人中心 =====
async function loadProfile() {
    try {
        const data = await api('GET', '/api/profile');
        const p = data.profile;
        const el = document.getElementById('profileInfo');
        const extraRoles = (p.extra_roles && p.extra_roles.length > 0) ? `<br><span style="color:var(--text-muted);">兼岗角色：</span>${p.extra_roles.join('、')}` : '';
        el.innerHTML = `
            <div style="display:grid;grid-template-columns:100px 1fr;gap:12px;line-height:2;">
                <span style="color:var(--text-muted);">用户名</span><span>${p.username}</span>
                <span style="color:var(--text-muted);">姓名</span><span>${p.display_name}</span>
                <span style="color:var(--text-muted);">角色</span><span>${p.role}${extraRoles}</span>
                <span style="color:var(--text-muted);">部门</span><span>${p.department || '--'}</span>
                <span style="color:var(--text-muted);">工号</span><span>${p.employee_id || '--'}</span>
                <span style="color:var(--text-muted);">注册时间</span><span>${p.created_at || '--'}</span>
            </div>`;
    } catch (err) { console.error('Profile load error:', err); }
}

function showEditProfile() {
    const name = prompt('显示名称：', currentUser ? currentUser.display_name : '');
    if (name === null) return;
    const dept = prompt('部门：', '');
    const data = {};
    if (name) data.display_name = name;
    if (dept) data.department = dept;
    if (Object.keys(data).length === 0) return;
    api('PUT', '/api/profile', data).then(result => {
        alert(result.message || '更新成功');
        loadProfile();
        if (name && currentUser) {
            currentUser.display_name = name;
            document.getElementById('userName').textContent = name;
            document.getElementById('userAvatar').textContent = name.charAt(0);
        }
    }).catch(err => alert('更新失败: ' + err.message));
}

async function handleChangePassword() {
    const oldPwd = document.getElementById('oldPassword').value;
    const newPwd = document.getElementById('newPassword').value;
    const confirmPwd = document.getElementById('confirmPassword').value;
    const msgEl = document.getElementById('passwordMsg');
    if (!oldPwd || !newPwd || !confirmPwd) {
        msgEl.style.display = 'block'; msgEl.style.color = 'var(--accent-red)';
        msgEl.textContent = '请填写所有密码字段'; return;
    }
    if (newPwd !== confirmPwd) {
        msgEl.style.display = 'block'; msgEl.style.color = 'var(--accent-red)';
        msgEl.textContent = '两次输入的新密码不一致'; return;
    }
    if (newPwd.length < 6) {
        msgEl.style.display = 'block'; msgEl.style.color = 'var(--accent-red)';
        msgEl.textContent = '新密码至少6位'; return;
    }
    try {
        const result = await api('POST', '/api/profile/change-password', { old_password: oldPwd, new_password: newPwd });
        msgEl.style.display = 'block'; msgEl.style.color = 'var(--accent-green)';
        msgEl.textContent = result.message || '密码修改成功';
        document.getElementById('oldPassword').value = '';
        document.getElementById('newPassword').value = '';
        document.getElementById('confirmPassword').value = '';
    } catch (err) {
        msgEl.style.display = 'block'; msgEl.style.color = 'var(--accent-red)';
        msgEl.textContent = err.message;
    }
}

// ===== 工单转办功能 =====
let _transferHistoryLoaded = {};

async function transferTicket(ticketNo) {
    // 弹出目标用户输入
    const target = prompt('转办给用户（输入用户名，如：110031）：');
    if (target === null) return;
    if (!target.trim()) { alert('请输入目标用户名'); return; }

    const reason = prompt('转办原因（选填）：', '');
    if (reason === null) return;

    try {
        const result = await api('POST', `/api/tickets/${ticketNo}/transfer`, {
            target_username: target.trim(),
            reason: (reason || '').trim()
        });
        alert(result.message || '转办成功');
        loadTickets();
        // 加载转办历史
        loadTransferHistory(ticketNo);
    } catch (err) {
        alert('转办失败: ' + err.message);
    }
}

async function loadTransferHistory(ticketNo) {
    // 避免重复加载
    if (_transferHistoryLoaded[ticketNo]) return;
    _transferHistoryLoaded[ticketNo] = true;

    try {
        const data = await api('GET', `/api/tickets/${ticketNo}/transfers`);
        const transfers = data.transfers || [];
        if (transfers.length === 0) return;

        // 在工单详情弹窗中追加转办历史
        let historyHtml = '<hr style="margin:12px 0;border:none;border-top:1px solid #ddd;"><strong>转办历史</strong><br>';
        transfers.forEach(t => {
            const fromName = t.from_name || t.from_user;
            const toName = t.to_name || t.to_user;
            historyHtml += `🔄 ${t.transferred_at}：${fromName} → ${toName}<br>`;
            if (t.reason) historyHtml += `&nbsp;&nbsp;&nbsp;&nbsp;原因：${t.reason}<br>`;
        });

        // 在现有详情弹窗中追加（通过修改 alert 内容为 HTML 方式）
        // 由于 alert 不支持 HTML，我们用一个自定义弹窗来显示
        showTransferModal(ticketNo, transfers);
    } catch (err) {
        console.error('加载转办历史失败:', err);
    }
}

function showTransferModal(ticketNo, transfers) {
    // 创建遮罩层
    const overlay = document.createElement('div');
    overlay.id = 'transferModal';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';

    let historyHtml = '<div style="max-height:300px;overflow-y:auto;">';
    transfers.forEach(t => {
        const fromName = t.from_name || t.from_user;
        const toName = t.to_name || t.to_user;
        historyHtml += `<div style="padding:8px 0;border-bottom:1px solid #333;">
            <div style="color:#3b82f6;">🔄 ${t.transferred_at}</div>
            <div>${fromName} → ${toName}</div>
            ${t.reason ? `<div style="color:#94a3b8;font-size:12px;">原因：${t.reason}</div>` : ''}
        </div>`;
    });
    historyHtml += '</div>';

    overlay.innerHTML = `<div style="background:#1a2332;border:1px solid #2d3a4f;border-radius:12px;padding:24px;max-width:500px;width:90%;color:#e2e8f0;">
        <h3 style="margin:0 0 16px;color:#3b82f6;">📋 工单 #${ticketNo} 转办历史</h3>
        ${historyHtml}
        <div style="text-align:right;margin-top:16px;">
            <button onclick="document.getElementById('transferModal').remove()" style="padding:8px 20px;background:#3b82f6;color:#fff;border:none;border-radius:6px;cursor:pointer;">关闭</button>
        </div>
    </div>`;

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    document.body.appendChild(overlay);
}
