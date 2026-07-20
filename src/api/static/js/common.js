/**
 * common.js - 通用工具函数、认证、API封装
 */
const API_BASE = window.location.origin;
let currentToken = null;
let currentUser = null;
let _scopeCache = null;  // 缓存当前用户范围信息（登录时计算一次）

const PIE_COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#a855f7', '#22d3ee'];

// ===== API 请求封装 =====
async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (currentToken) opts.headers['Authorization'] = `Bearer ${currentToken}`;
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(API_BASE + path, opts);
    if (resp.status === 401) { handleLogout(); throw new Error('认证过期'); }
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || '请求失败');
    return data;
}

// ===== 认证 =====
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    const btn = document.getElementById('loginBtn');
    errorDiv.style.display = 'none'; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
    try {
        const data = await api('POST', '/api/auth/login', { username, password });
        currentToken = data.token; currentUser = data.user;
        sessionStorage.setItem('ssc_token', currentToken); showApp();
    } catch (err) { errorDiv.textContent = err.message; errorDiv.style.display = 'block'; }
    finally { btn.disabled = false; btn.textContent = '登 录'; }
}

function handleLogout() {
    if (currentToken) api('POST', '/api/auth/logout').catch(() => { });
    currentToken = null; currentUser = null; _scopeCache = null;
    sessionStorage.removeItem('ssc_token');
    // 清除智能问答聊天记录，防止下一个用户看到上一个用户的对话
    const chatMsgs = document.getElementById('chatMessages');
    if (chatMsgs) chatMsgs.innerHTML = '';
    document.getElementById('loginPage').style.display = '';
    document.getElementById('appPage').style.display = 'none';
}

// ===== 过滤器工具 =====
function buildFilterParams() {
    const params = new URLSearchParams();
    const fields = ['filterCompany', 'filterCenter', 'filterDepartment', 'filterMonth', 'filterEmpType'];
    const keys = ['company', 'center', 'department', 'month', 'emp_type'];
    fields.forEach((id, i) => { const val = document.getElementById(id).value; if (val) params.set(keys[i], val); });
    return params;
}

/**
 * refreshSelect：重建选项 + 应用角色范围约束。
 * 每次被dashboard.js调用时，用缓存的scope信息过滤选项并应用锁定。
 */
function refreshSelect(id, options, currentValue) {
    const sel = document.getElementById(id), isMonth = id === 'filterMonth';
    const placeholder = isMonth ? '' : '<option value="">全部</option>';
    if (currentValue && !options.includes(currentValue)) currentValue = '';
    if (isMonth && !currentValue && options.length > 0) currentValue = options[0];

    // 角色范围过滤：公司（lockedCompany时只保留该公司的选项）
    if (id === 'filterCompany' && _scopeCache && _scopeCache.lockedCompany) {
        options = options.filter(o => o === _scopeCache.lockedCompany);
    }

    sel.innerHTML = placeholder;
    options.forEach(opt => { const o = document.createElement('option'); o.value = opt; o.textContent = opt; sel.appendChild(o); });
    sel.value = currentValue;

    // 角色范围过滤：中心（根据当前公司值和allowedCenters过滤）
    if (id === 'filterCenter' && _scopeCache && _scopeCache.allowedCenters) {
        const companyVal = document.getElementById('filterCompany').value;
        const allowed = _scopeCache.allowedCenters[companyVal];
        if (allowed && allowed.length > 0) {
            const allowedSet = new Set(allowed);
            Array.from(sel.options).forEach(o => {
                if (o.value && !allowedSet.has(o.value)) o.remove();
            });
            // 自动选中（单中心时）
            if (sel.options.length <= 2 && !sel.value) {
                for (let i = 0; i < sel.options.length; i++) {
                    if (sel.options[i].value) { sel.value = sel.options[i].value; break; }
                }
            }
        }
    }

    // 角色范围过滤：部门（根据当前中心值和allowedDepts过滤）
    if (id === 'filterDepartment' && _scopeCache && _scopeCache.allowedDepts) {
        const centerVal = document.getElementById('filterCenter').value;
        const allowed = _scopeCache.allowedDepts[centerVal];
        if (allowed && allowed.length > 0) {
            const allowedSet = new Set(allowed);
            Array.from(sel.options).forEach(o => {
                if (o.value && !allowedSet.has(o.value)) o.remove();
            });
            if (allowed.length === 1 && !sel.value) sel.value = allowed[0];
        }
    }

    // 应用锁定disabled状态
    _applyFilterLocks();
}

/**
 * 根据 _scopeCache 应用所有筛选器的锁定/disabled状态。
 * 仅控制 disabled，不改变 value。
 */
function _applyFilterLocks() {
    if (!_scopeCache) return;
    if (_scopeCache.lockedCompany) document.getElementById('filterCompany').disabled = true;
    if (_scopeCache.lockedCenter) document.getElementById('filterCenter').disabled = true;
    if (_scopeCache.lockedDepartment) document.getElementById('filterDepartment').disabled = true;
    // 联动逻辑：公司未选定时，中心应灰掉（与权限锁定无关）
    const companyVal = document.getElementById('filterCompany').value;
    const centerSel = document.getElementById('filterCenter');
    if (!companyVal && !_scopeCache.lockedCenter) {
        centerSel.disabled = true;
    }
}

/**
 * updateFilterLocks：设置筛选器值 + 应用锁定。
 * 在 loadKPI 完成（选项已填充）后调用，只执行一次。
 */
function updateFilterLocks() {
    const companySel = document.getElementById('filterCompany');
    const centerSel = document.getElementById('filterCenter');
    const deptSel = document.getElementById('filterDepartment');

    if (!_scopeCache) return;
    const s = _scopeCache;

    // ---- 公司 ----
    if (s.lockedCompany) {
        companySel.value = s.lockedCompany;
        companySel.disabled = true;
    }

    // ---- 中心 ----
    const currentCompany = companySel.value;
    if (s.lockedCenter) {
        // 纯经理：中心锁定
        _ensureOption(centerSel, currentCompany, s.lockedCenter);
        centerSel.value = s.lockedCenter;
        centerSel.disabled = true;
    } else if (currentCompany && s.allowedCenters && s.allowedCenters[currentCompany]) {
        // 有allowedCenters约束：过滤中心选项
        const allowed = s.allowedCenters[currentCompany];
        const prevCenter = centerSel.value;
        centerSel.innerHTML = '<option value="">全部</option>';
        allowed.forEach(c => {
            const opt = document.createElement('option'); opt.value = c; opt.textContent = c; centerSel.appendChild(opt);
        });
        if (allowed.includes(prevCenter)) centerSel.value = prevCenter;
        if (allowed.length === 1) { centerSel.value = allowed[0]; centerSel.disabled = true; }
        else centerSel.disabled = false;
    } else if (currentCompany && (!s.allowedCenters || Object.keys(s.allowedCenters).length === 0 || (s.allowedCenters && !s.allowedCenters[currentCompany]))) {
        // 公司级别访问（无allowedCenters约束）：中心不锁定
        centerSel.disabled = false;
    } else if (!currentCompany) {
        // 联动逻辑：公司未选定（全部）时，中心应灰掉
        centerSel.disabled = true;
        centerSel.innerHTML = '<option value="">全部</option>';
    }

    // ---- 部门 ----
    if (s.lockedDepartment) {
        _ensureOption(deptSel, null, s.lockedDepartment);
        deptSel.value = s.lockedDepartment;
        deptSel.disabled = true;
    } else if (!centerSel.value) {
        deptSel.disabled = true;
        deptSel.innerHTML = '<option value="">全部</option>';
    } else if (s.allowedDepts && s.allowedDepts[centerSel.value]) {
        // 有部门级约束：过滤部门选项
        const allowed = s.allowedDepts[centerSel.value];
        const allowedSet = new Set(allowed);
        Array.from(deptSel.options).forEach(o => {
            if (o.value && !allowedSet.has(o.value)) o.remove();
        });
        if (allowed.length === 1) { deptSel.value = allowed[0]; deptSel.disabled = true; }
        else deptSel.disabled = false;
    } else {
        deptSel.disabled = false;
    }
}

/** 部门→中心映射 */
const DEPT_TO_CENTER = {
    "总装部": "制造一中心", "卓越制造部": "制造一中心", "物流运营部": "制造一中心",
    "质量管理部": "职能中心", "采购部": "职能中心", "财务管理部": "职能中心",
    "行政管理部": "职能中心", "信息技术部": "职能中心", "人力资源管理部": "职能中心", "总经办": "职能中心",
    "德系大客户管理部": "德系业务中心", "德系产品策划部": "德系业务中心", "德系项目管理部": "德系业务中心",
    "大客户管理部-日系": "日系业务中心", "业务策划管理部-产品-日系": "日系业务中心", "业务策划管理部-项目-日系": "日系业务中心",
    "大客户管理部-自主": "自主业务中心", "业务策划管理部-产品-自主": "自主业务中心", "业务策划管理部-项目-自主": "自主业务中心",
    "大客户管理部-代工": "代工业务中心", "业务策划管理部-产品-代工": "代工业务中心", "业务策划管理部-项目-代工": "代工业务中心",
    "软件研发部": "长春研发中心", "硬件研发部": "长春研发中心", "系统部": "长春研发中心", "设计质量部": "长春研发中心",
    "表面贴装技术部": "制造二中心", "预装部": "制造二中心", "工程技术部": "制造二中心",
    "软件智能座舱研发部(大连)": "大连研发中心", "软件智能驾驶研发部(大连)": "大连研发中心",
    "软件项目管理部(大连)": "大连研发中心", "卓越运营部(大连)": "大连研发中心",
    "财务管理部-EM": "益劢职能中心", "采购部-EM": "益劢职能中心", "总经办-EM": "益劢职能中心",
};

/** 中心→公司映射（精确映射，避免名称推断错误） */
const CENTER_TO_COMPANY = {
    "制造一中心": "[公司名称]", "德系业务中心": "[公司名称]", "日系业务中心": "[公司名称]",
    "自主业务中心": "[公司名称]", "代工业务中心": "[公司名称]", "职能中心": "[公司名称]",
    "长春研发中心": "[公司名称]", "大连研发中心": "[公司名称]",
    "制造二中心": "[关联公司]", "益劢职能中心": "[关联公司]",
};

/** 公司名集合（用于判断org名是否是公司名） */
const COMPANY_NAMES = new Set(['[公司名称]', '[关联公司]']);

function _inferCompany(org) {
    // 优先用精确映射
    if (CENTER_TO_COMPANY[org]) return CENTER_TO_COMPANY[org];
    // 名称推断兜底
    if (org.includes('益劢') || org.includes('-EM')) return '[关联公司]';
    return '[公司名称]';
}

/**
 * 计算当前用户的可见组织范围。
 * 统一规则：所有人（包括总经理/副总）的范围都从org倒推。
 * SSC操作层无管辖限制的角色直接返回空（不锁定）。
 *
 * 返回: { lockedCompany, lockedCenter, lockedDepartment, allowedCenters, allowedDepts }
 */
function _calcUserScope() {
    const result = { lockedCompany: null, lockedCenter: null, lockedDepartment: null, allowedCenters: {}, allowedDepts: {} };
    if (!currentUser) return result;

    const roleDetails = currentUser.role_details || [];
    const company = currentUser.company || '';

    // ---- SSC操作层无限制角色（有任一即全部不锁定） ----
    const noRestrictRoles = ['高级HRIS工程师', 'HRIS工程师', '薪酬主管', '薪酬专员', '考勤专员', '招聘主管', '招聘专员', '员工关系主管', '员工关系专员', 'HR_SSC学科经理', 'HR_SSC经理'];
    const allRoleNames = roleDetails.map(r => r.role);
    if (allRoleNames.some(rn => noRestrictRoles.includes(rn))) {
        return result;
    }

    // ---- 收集所有 org 信息 ----
    // role_details中的org可能为空（register_user插入主角色时org=''）
    // 此时用用户department字段推断
    const userDept = currentUser.department || '';
    const orgs = [];
    roleDetails.forEach(rd => {
        if (rd.org && rd.org_level) {
            orgs.push({ org: rd.org, level: rd.org_level });
        }
    });
    // 如果没有任何有效org，用department推断
    if (orgs.length === 0 && userDept) {
        // 判断department是center还是department级别
        if (DEPT_TO_CENTER[userDept]) {
            // department是一个部门名 → level=department
            orgs.push({ org: userDept, level: 'department' });
        } else {
            // 可能是中心名 → level=center
            orgs.push({ org: userDept, level: 'center' });
        }
    }
    // 最后兜底：company字段
    if (orgs.length === 0 && company) orgs.push({ org: company, level: 'company' });
    if (orgs.length === 0) return result;

    // ---- 按公司→中心→部门 分桶 ----
    const companyToCenters = {};
    const centerToDepts = {};

    orgs.forEach(({ org, level }) => {
        // 如果org名是公司名（如"[关联公司]"），即使level=center也视为company级
        if (level === 'center' && COMPANY_NAMES.has(org)) {
            level = 'company';
        }
        if (level === 'company') {
            if (!companyToCenters[org]) companyToCenters[org] = new Set();
        } else if (level === 'center') {
            const comp = _inferCompany(org);
            if (!companyToCenters[comp]) companyToCenters[comp] = new Set();
            companyToCenters[comp].add(org);
            if (!centerToDepts[org]) centerToDepts[org] = new Set();
        } else if (level === 'department') {
            const center = DEPT_TO_CENTER[org];
            if (center) {
                const comp = _inferCompany(center);
                if (!companyToCenters[comp]) companyToCenters[comp] = new Set();
                companyToCenters[comp].add(center);
                if (!centerToDepts[center]) centerToDepts[center] = new Set();
                centerToDepts[center].add(org);
            }
        }
    });

    // ---- 构建 allowedCenters ----
    Object.keys(companyToCenters).forEach(comp => {
        const centers = [...companyToCenters[comp]];
        if (centers.length > 0) result.allowedCenters[comp] = centers;
    });

    // ---- 构建 allowedDepts（仅当有部门级约束时） ----
    Object.keys(centerToDepts).forEach(center => {
        const depts = [...centerToDepts[center]];
        if (depts.length > 0) result.allowedDepts[center] = depts;
    });

    // ---- 公司锁定（仅单公司） ----
    const companies = Object.keys(companyToCenters);
    if (companies.length === 1) result.lockedCompany = companies[0];

    // ---- 中心/部门锁定（仅纯经理：只有一个中心/部门） ----
    let hasDirectorOrHRBPRole = allRoleNames.some(rn => rn === '总监' || rn === 'HRBP');
    let hasPureManagerRole = allRoleNames.includes('经理') && !hasDirectorOrHRBPRole;
    if (hasPureManagerRole) {
        const allCenters = new Set();
        Object.values(companyToCenters).forEach(s => s.forEach(c => allCenters.add(c)));
        if (allCenters.size === 1) result.lockedCenter = [...allCenters][0];
        const allDepts = new Set();
        Object.values(centerToDepts).forEach(s => s.forEach(d => allDepts.add(d)));
        if (allDepts.size === 1) result.lockedDepartment = [...allDepts][0];
    }

    console.log('[ScopeCalc]', currentUser.username, JSON.stringify(result));
    return result;
}

function _ensureOption(sel, company, value) {
    if (!value) return;
    if (!Array.from(sel.options).some(o => o.value === value)) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = value;
        sel.appendChild(opt);
    }
}

/**
 * applyDefaultMonth - 当月份选择器为空时，默认选中最新月份
 * 在部门经理登录场景下，月份默认值为空会导致加载全公司数据
 */
function applyDefaultMonth() {
    const monthSel = document.getElementById('filterMonth');
    if (!monthSel || monthSel.options.length === 0) return;
    // 如果当前没有选中任何月份，自动选中第一个（最新）
    if (!monthSel.value) {
        monthSel.value = monthSel.options[1] ? monthSel.options[1].value : monthSel.options[0].value;
    }
}

function applyFilters(changedField) {
    // 切换公司/中心/部门时，只清空下级筛选器，不清空人员类型
    if (changedField === 'company') { document.getElementById('filterCenter').value = ''; document.getElementById('filterDepartment').value = ''; }
    else if (changedField === 'center') { document.getElementById('filterDepartment').value = ''; }
    // department 切换时不清空任何字段
    updateFilterLocks();
    const needEfficiency = (changedField === 'company' || changedField === 'month' || changedField === undefined);
    loadKPI(); loadCharts(); loadOvertime(); loadDeptDetail(); loadCostAnalysis();
    if (needEfficiency) loadEfficiency();
}

// ===== 格式化工具 =====
function formatMoney(val) {
    if (val >= 100000000) return (val / 100000000).toFixed(2) + '亿';
    if (val >= 10000) return (val / 10000).toFixed(1) + '万';
    return val.toLocaleString();
}

// ===== 柱形渐变色 =====
const BAR_GRADIENTS = [
    [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: 'rgba(59,130,246,0.4)' }],
    [{ offset: 0, color: '#8b5cf6' }, { offset: 1, color: 'rgba(139,92,246,0.4)' }],
    [{ offset: 0, color: '#06b6d4' }, { offset: 1, color: 'rgba(6,182,212,0.4)' }],
    [{ offset: 0, color: '#10b981' }, { offset: 1, color: 'rgba(16,185,129,0.4)' }],
    [{ offset: 0, color: '#f59e0b' }, { offset: 1, color: 'rgba(245,158,11,0.4)' }],
    [{ offset: 0, color: '#ef4444' }, { offset: 1, color: 'rgba(239,68,68,0.4)' }],
    [{ offset: 0, color: '#ec4899' }, { offset: 1, color: 'rgba(236,72,153,0.4)' }],
    [{ offset: 0, color: '#6366f1' }, { offset: 1, color: 'rgba(99,102,241,0.4)' }],
    [{ offset: 0, color: '#14b8a6' }, { offset: 1, color: 'rgba(20,184,166,0.4)' }],
    [{ offset: 0, color: '#f97316' }, { offset: 1, color: 'rgba(249,115,22,0.4)' }],
    [{ offset: 0, color: '#a855f7' }, { offset: 1, color: 'rgba(168,85,247,0.4)' }],
    [{ offset: 0, color: '#22d3ee' }, { offset: 1, color: 'rgba(34,211,238,0.4)' }],
];