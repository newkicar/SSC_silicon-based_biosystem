/**
 * dashboard.js - 仪表板模块：KPI、图表、人效指标、部门明细表
 */
let chartDataCache = null;
let currentStructureDim = 'gender';
let echartsStructure = null, echartsContract = null, echartsLevel = null, echartsTrend = null;

const DIM_LABELS = { gender: '按性别', education: '按学历', age: '按年龄段', tenure: '按工龄段' };

// 人效指标配置
const EFF_CONFIG = {
    '每元人力投入产出': { el: 'indPerCapita', positive: true, unit: '' },
    '人事费用率': { el: 'indCostRatio', positive: false, unit: '%' },
    '人均毛利': { el: 'indGrossProfit', positive: true, unit: '' },
};

// 离职率配置
const TURNOVER_CONFIG = [
    { cat: '间接主动离职率', el: 'indTurnover1', hasBudget: true },
    { cat: '间接被动离职率', el: 'indTurnover2', hasBudget: false },
    { cat: '直接主动离职率', el: 'indTurnover3', hasBudget: true },
    { cat: '直接被动离职率', el: 'indTurnover4', hasBudget: false },
];

// ===== KPI 加载 =====
async function loadKPI() {
    try {
        const params = buildFilterParams();
        const data = await api('GET', `/api/dashboard/kpi?${params.toString()}`);
        const d = data.data;
        refreshSelect('filterCompany', d.filter_options.companies, document.getElementById('filterCompany').value);
        refreshSelect('filterCenter', d.filter_options.centers, document.getElementById('filterCenter').value);
        refreshSelect('filterDepartment', d.filter_options.departments, document.getElementById('filterDepartment').value);
        const monthSel = document.getElementById('filterMonth');
        const prevMonth = monthSel.value;
        refreshSelect('filterMonth', d.filter_options.months, document.getElementById('filterMonth').value);
        refreshSelect('filterEmpType', d.filter_options.emp_types, document.getElementById('filterEmpType').value);
        updateFilterLocks();

        // 如果月份被自动设置了默认值（从空变为有值），重新加载数据
        if (!prevMonth && monthSel.value) {
            const reParams = buildFilterParams();
            const reData = await api('GET', `/api/dashboard/kpi?${reParams.toString()}`);
            const rd = reData.data;
            document.getElementById('dataUpdateTime').textContent = rd.data_update_time;
            document.getElementById('dataCutoff').textContent = rd.data_cutoff;
            document.getElementById('kpiHeadcount').textContent = rd.headcount.current.toLocaleString();
            document.getElementById('kpiBudget').textContent = rd.headcount.budget.toLocaleString();
            const diffEl = document.getElementById('kpiDiff');
            diffEl.textContent = (rd.headcount.diff >= 0 ? '+' : '') + rd.headcount.diff.toLocaleString();
            diffEl.className = 'val ' + (rd.headcount.diff > 0 ? 'up' : rd.headcount.diff < 0 ? 'down' : 'neutral');
            const ratioEl = document.getElementById('kpiRatio');
            ratioEl.textContent = (rd.headcount.ratio >= 0 ? '+' : '') + rd.headcount.ratio + '%';
            ratioEl.className = 'val ' + (rd.headcount.ratio > 0 ? 'up' : rd.headcount.ratio < 0 ? 'down' : 'neutral');
            document.getElementById('kpiWhite').textContent = rd.headcount.white_collar.toLocaleString();
            document.getElementById('kpiBlue').textContent = rd.headcount.blue_collar.toLocaleString();
            document.getElementById('kpiRecruitTotal').textContent = rd.recruitment.total;
            document.getElementById('kpiRecruitHired').textContent = rd.recruitment.hired;
            document.getElementById('kpiRecruitPending').textContent = rd.recruitment.pending;
            document.getElementById('kpiCostRatio').textContent = rd.cost.ratio.toFixed(1) + '%';
            document.getElementById('kpiBudgetCost').textContent = formatMoney(rd.cost.budget);
            document.getElementById('kpiActualCost').textContent = formatMoney(rd.cost.actual);
        }
        document.getElementById('dataUpdateTime').textContent = d.data_update_time;
        document.getElementById('dataCutoff').textContent = d.data_cutoff;
        document.getElementById('kpiHeadcount').textContent = d.headcount.current.toLocaleString();
        document.getElementById('kpiBudget').textContent = d.headcount.budget.toLocaleString();
        const diffEl = document.getElementById('kpiDiff');
        diffEl.textContent = (d.headcount.diff >= 0 ? '+' : '') + d.headcount.diff.toLocaleString();
        diffEl.className = 'val ' + (d.headcount.diff > 0 ? 'up' : d.headcount.diff < 0 ? 'down' : 'neutral');
        const ratioEl = document.getElementById('kpiRatio');
        ratioEl.textContent = (d.headcount.ratio >= 0 ? '+' : '') + d.headcount.ratio + '%';
        ratioEl.className = 'val ' + (d.headcount.ratio > 0 ? 'up' : d.headcount.ratio < 0 ? 'down' : 'neutral');
        document.getElementById('kpiWhite').textContent = d.headcount.white_collar.toLocaleString();
        document.getElementById('kpiBlue').textContent = d.headcount.blue_collar.toLocaleString();
        document.getElementById('kpiRecruitTotal').textContent = d.recruitment.total;
        document.getElementById('kpiRecruitHired').textContent = d.recruitment.hired;
        document.getElementById('kpiRecruitPending').textContent = d.recruitment.pending;
        document.getElementById('kpiCostRatio').textContent = d.cost.ratio.toFixed(1) + '%';
        document.getElementById('kpiBudgetCost').textContent = formatMoney(d.cost.budget);
        document.getElementById('kpiActualCost').textContent = formatMoney(d.cost.actual);
    } catch (err) { console.error('KPI load error:', err); }
}

// ===== 图表加载 =====
async function loadCharts() {
    try {
        const params = buildFilterParams();
        const data = await api('GET', `/api/dashboard/charts?${params.toString()}`);
        chartDataCache = data.data;
        const d = chartDataCache;
        refreshSelect('filterCompany', d.filter_options.companies, document.getElementById('filterCompany').value);
        refreshSelect('filterCenter', d.filter_options.centers, document.getElementById('filterCenter').value);
        refreshSelect('filterDepartment', d.filter_options.departments, document.getElementById('filterDepartment').value);
        refreshSelect('filterMonth', d.filter_options.months, document.getElementById('filterMonth').value);
        refreshSelect('filterEmpType', d.filter_options.emp_types, document.getElementById('filterEmpType').value);
        renderStructureChart(currentStructureDim); renderContractChart(); renderLevelChart(); renderTrendChart();
    } catch (err) { console.error('Charts load error:', err); }
}

// ===== 人效指标加载 =====
async function loadEfficiency() {
    try {
        const params = new URLSearchParams();
        const company = document.getElementById('filterCompany').value;
        const month = document.getElementById('filterMonth').value;
        if (company) params.set('company', company);
        if (month) params.set('month', month);
        const data = await api('GET', `/api/dashboard/efficiency?${params.toString()}`);
        const eff = data.data;
        const indicators = eff.indicators || {};
        for (const [proj, cfg] of Object.entries(EFF_CONFIG)) {
            const el = document.getElementById(cfg.el);
            const d = indicators[proj];
            if (!d) { el.innerHTML = `<div class="indicator-title">${proj}</div><div class="indicator-detail">暂无数据</div>`; continue; }
            const monthDiffClass = d.month_diff !== null ? (cfg.positive ? (d.month_diff >= 0 ? 'positive' : 'negative') : (d.month_diff >= 0 ? 'positive-reverse' : 'negative-reverse')) : '';
            const cumDiffClass = d.cum_diff !== null ? (cfg.positive ? (d.cum_diff >= 0 ? 'positive' : 'negative') : (d.cum_diff >= 0 ? 'positive-reverse' : 'negative-reverse')) : '';
            const monthDiffSign = d.month_diff !== null && d.month_diff >= 0 ? '+' : '';
            const cumDiffSign = d.cum_diff !== null && d.cum_diff >= 0 ? '+' : '';
            el.innerHTML = `
                <div class="indicator-title">${proj}</div>
                <div class="indicator-main">
                    <span class="indicator-value">${d.actual_month}${cfg.unit}</span>
                    <span class="indicator-divider">|</span>
                    <span class="indicator-value-sm">${d.actual_cum}${cfg.unit}</span>
                    <span class="indicator-label" style="margin-left:8px;font-size:12px;color:var(--text-muted);">当月 | 累积</span>
                </div>
                <div class="indicator-detail" style="flex-direction:column;gap:2px;">
                    <div style="display:flex;gap:10px;">
                        <span><span class="label">当月管控：</span><span class="val">${d.budget_month}${cfg.unit}</span></span>
                        <span><span class="label">当月较管控：</span><span class="val ${monthDiffClass}">${monthDiffSign}${d.month_diff !== null ? parseFloat(d.month_diff).toFixed(2) : '--'}</span></span>
                    </div>
                    <div style="display:flex;gap:10px;">
                        <span><span class="label">累积管控：</span><span class="val">${d.budget_cum}${cfg.unit}</span></span>
                        <span><span class="label">累积较管控：</span><span class="val ${cumDiffClass}">${cumDiffSign}${d.cum_diff !== null ? parseFloat(d.cum_diff).toFixed(2) : '--'}</span></span>
                    </div>
                </div>
            `;
        }
        // 离职率卡片
        const turnover = eff.turnover || {};
        for (const cfg of TURNOVER_CONFIG) {
            const el = document.getElementById(cfg.el);
            const d = turnover[cfg.cat];
            if (!d) { el.innerHTML = `<div class="indicator-title">${cfg.cat}</div><div class="indicator-detail">暂无数据</div>`; continue; }
            let budgetHtml = '';
            if (cfg.hasBudget && d.budget !== '--') {
                budgetHtml = `<div style="display:flex;gap:10px;"><span><span class="label">管控目标：</span><span class="val">${d.budget}</span></span></div>`;
            }
            el.innerHTML = `
                <div class="indicator-title">${cfg.cat}</div>
                <div class="indicator-main">
                    <span class="indicator-value">${d.actual}</span>
                </div>
                <div class="indicator-detail" style="flex-direction:column;gap:2px;">
                    ${budgetHtml}
                </div>
            `;
        }
    } catch (err) { console.error('Efficiency load error:', err); }
}

// ===== 部门明细表加载 =====
async function loadDeptDetail() {
    try {
        const params = buildFilterParams();
        const data = await api('GET', `/api/dashboard/dept-detail?${params.toString()}`);
        const d = data.data;
        const tbody = document.getElementById('deptDetailBody');
        if (!d.data || d.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="padding:20px;text-align:center;color:var(--text-muted);">暂无数据</td></tr>';
            return;
        }
        let html = '';
        d.data.forEach((row, idx) => {
            const bg = idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)';
            html += `<tr style="border-bottom:1px solid var(--border-color);background:${bg};">`;
            html += `<td style="padding:8px 12px;text-align:left;color:var(--text-primary);white-space:nowrap;">${row.dept}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:var(--text-secondary);">${row.headcount}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:var(--text-secondary);">${row.turnover_rate !== null ? row.turnover_rate + '%' : '--'}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:var(--text-secondary);">${row.attendance !== null ? row.attendance + '%' : '--'}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:var(--text-secondary);">${row.overtime_hours !== null ? row.overtime_hours.toFixed(1) : '--'}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:${row.hc_rate !== null ? (row.hc_rate > 100 ? 'var(--accent-red)' : 'var(--text-secondary)') : 'var(--text-muted)'};">${row.hc_rate !== null ? row.hc_rate + '%' : '--'}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:${row.cost_rate !== null ? (row.cost_rate > 100 ? 'var(--accent-red)' : 'var(--text-secondary)') : 'var(--text-muted)'};">${row.cost_rate !== null ? row.cost_rate + '%' : '--'}</td>`;
            html += `<td style="padding:8px 12px;text-align:right;color:${row.pending_recruit > 0 ? 'var(--accent-orange)' : 'var(--text-secondary)'};">${row.pending_recruit > 0 ? row.pending_recruit : '0'}</td>`;
            html += '</tr>';
        });
        tbody.innerHTML = html;
    } catch (err) { console.error('Dept detail load error:', err); }
}

// ===== ECharts 渲染 =====
function renderStructureChart(dim) {
    if (!chartDataCache) return;
    currentStructureDim = dim;
    document.getElementById('structureSubtitle').textContent = DIM_LABELS[dim] || '';
    document.querySelectorAll('#structureDimBtns .dim-btn').forEach(btn => { btn.classList.toggle('active', btn.getAttribute('onclick').includes(`'${dim}'`)); });
    const pieData = chartDataCache.structure[dim] || [];
    if (!echartsStructure) { echartsStructure = echarts.init(document.getElementById('chartStructure')); window.addEventListener('resize', () => echartsStructure && echartsStructure.resize()); }
    echartsStructure.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)', backgroundColor: '#1a2332', borderColor: '#2d3a4f', textStyle: { color: '#e2e8f0' } },
        legend: { orient: 'horizontal', top: 0, left: 'center', textStyle: { color: '#94a3b8', fontSize: 12 }, itemWidth: 10, itemHeight: 10 },
        color: PIE_COLORS,
        series: [{
            type: 'pie', radius: ['35%', '65%'], center: ['50%', '55%'], avoidLabelOverlap: true,
            itemStyle: { borderRadius: 6, borderColor: '#1a2332', borderWidth: 2 },
            label: { show: true, color: '#94a3b8', fontSize: 12, formatter: '{b}\n{d}%', overflow: 'truncate', width: 80 },
            labelLine: { lineStyle: { color: '#2d3a4f' }, length: 10, length2: 15 },
            emphasis: { label: { fontSize: 14, fontWeight: 'bold' }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
            data: pieData.map(d => ({ name: d.name, value: d.value }))
        }]
    });
}

function switchStructureDim(dim) { renderStructureChart(dim); }

function renderContractChart() {
    if (!chartDataCache) return;
    const pieData = chartDataCache.contract || [];
    if (!echartsContract) { echartsContract = echarts.init(document.getElementById('chartContract')); window.addEventListener('resize', () => echartsContract && echartsContract.resize()); }
    echartsContract.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)', backgroundColor: '#1a2332', borderColor: '#2d3a4f', textStyle: { color: '#e2e8f0' } },
        legend: { orient: 'horizontal', top: 0, left: 'center', textStyle: { color: '#94a3b8', fontSize: 12 }, itemWidth: 10, itemHeight: 10 },
        color: PIE_COLORS,
        series: [{
            type: 'pie', radius: ['35%', '65%'], center: ['50%', '55%'], avoidLabelOverlap: true,
            itemStyle: { borderRadius: 6, borderColor: '#1a2332', borderWidth: 2 },
            label: { show: true, color: '#94a3b8', fontSize: 12, formatter: '{b}\n{d}%', overflow: 'truncate', width: 80 },
            labelLine: { lineStyle: { color: '#2d3a4f' }, length: 10, length2: 15 },
            emphasis: { label: { fontSize: 14, fontWeight: 'bold' }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
            data: pieData.map(d => ({ name: d.name, value: d.value }))
        }]
    });
}

function renderLevelChart() {
    if (!chartDataCache) return;
    const levelData = chartDataCache.level || [];
    if (!echartsLevel) { echartsLevel = echarts.init(document.getElementById('chartLevel')); window.addEventListener('resize', () => echartsLevel && echartsLevel.resize()); }
    const LEVEL_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '/', '//'];
    const dataMap = {}; levelData.forEach(d => { dataMap[d.name] = d.value; });
    const orderedLevels = LEVEL_ORDER.filter(l => dataMap[l] !== undefined);
    levelData.forEach(d => { if (!orderedLevels.includes(d.name)) orderedLevels.push(d.name); });
    const categories = orderedLevels.map(l => l + '级'), values = orderedLevels.map(l => dataMap[l] || 0);
    const halfValues = values.map(v => v / 2), maxHalf = Math.max(...halfValues, 1);

    // 动态计算百分比，确保加和=100%（最大余数法，保留一位小数）
    const total = values.reduce((a, b) => a + b, 0);
    const pctLabels = [];
    if (total > 0) {
        const rawPct = values.map(v => v / total * 1000);
        const intPct = rawPct.map(v => Math.floor(v));
        let remainder = 1000 - intPct.reduce((a, b) => a + b, 0);
        const indices = rawPct.map((v, i) => i).sort((a, b) => (rawPct[b] - intPct[b]) - (rawPct[a] - intPct[a]));
        for (let i = 0; i < remainder; i++) { intPct[indices[i]]++; }
        for (let i = 0; i < values.length; i++) {
            pctLabels.push(values[i] + '人 (' + (intPct[i] / 10).toFixed(1) + '%)');
        }
    } else {
        values.forEach(v => pctLabels.push(v + '人'));
    }

    echartsLevel.setOption({
        tooltip: {
            trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: '#1a2332', borderColor: '#2d3a4f', textStyle: { color: '#e2e8f0' },
            formatter: function (params) { const idx = params[0].dataIndex; return orderedLevels[idx] + '级: ' + values[idx] + '人 (' + (total > 0 ? (values[idx] / total * 100).toFixed(1) : '0.0') + '%)'; }
        },
        grid: { left: '12%', right: '18%', top: 10, bottom: 10 },
        xAxis: { type: 'value', min: -maxHalf * 1.2, max: maxHalf * 1.2, axisLabel: { color: '#64748b', fontSize: 11, formatter: function (v) { return Math.abs(v); } }, axisLine: { show: false }, splitLine: { lineStyle: { color: '#1e293b' } } },
        yAxis: { type: 'category', data: categories, axisLabel: { color: '#94a3b8', fontSize: 12 }, axisLine: { lineStyle: { color: '#2d3a4f' } }, axisTick: { show: false } },
        series: [
            { type: 'bar', stack: 'tornado', data: halfValues.map(v => -v), barWidth: '55%', itemStyle: { color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: '#8b5cf6' }]), borderRadius: [4, 0, 0, 4] }, label: { show: false } },
            { type: 'bar', stack: 'tornado', data: halfValues, barWidth: '55%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: '#8b5cf6' }]), borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: '#94a3b8', fontSize: 11, formatter: function (p) { return pctLabels[p.dataIndex]; } } }
        ]
    });
}

function renderTrendChart() {
    if (!chartDataCache || !chartDataCache.trend) return;
    const trend = chartDataCache.trend;
    if (!echartsTrend) { echartsTrend = echarts.init(document.getElementById('chartTrend')); window.addEventListener('resize', () => echartsTrend && echartsTrend.resize()); }
    const monthLabels = trend.months.map(m => parseInt(m.split('-')[1]) + '月');
    echartsTrend.setOption({
        tooltip: { trigger: 'axis', backgroundColor: '#1a2332', borderColor: '#2d3a4f', textStyle: { color: '#e2e8f0' }, axisPointer: { type: 'cross', crossStyle: { color: '#64748b' } } },
        legend: { top: 0, left: 'center', textStyle: { color: '#94a3b8', fontSize: 12 }, itemWidth: 14, itemHeight: 10 },
        grid: { left: '5%', right: '5%', top: 40, bottom: 30, containLabel: true },
        xAxis: { type: 'category', data: monthLabels, axisLabel: { color: '#94a3b8', fontSize: 12 }, axisLine: { lineStyle: { color: '#2d3a4f' } }, axisTick: { show: false } },
        yAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 11 }, axisLine: { show: false }, splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [
            { name: '入职人数', type: 'bar', data: trend.hire, barWidth: '25%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: 'rgba(59,130,246,0.3)' }]), borderRadius: [4, 4, 0, 0] }, label: { show: true, position: 'top', color: '#3b82f6', fontSize: 11 } },
            { name: '离职人数', type: 'bar', data: trend.leave, barWidth: '25%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#8b5cf6' }, { offset: 1, color: 'rgba(139,92,246,0.3)' }]), borderRadius: [4, 4, 0, 0] }, label: { show: true, position: 'top', color: '#8b5cf6', fontSize: 11 } },
            { name: '净增长', type: 'line', data: trend.net, smooth: true, symbol: 'circle', symbolSize: 8, lineStyle: { color: '#f59e0b', width: 3 }, itemStyle: { color: '#f59e0b', borderColor: '#1a2332', borderWidth: 2 }, label: { show: true, position: trend.net.map(v => v >= 0 ? 'top' : 'bottom'), color: '#f59e0b', fontSize: 11 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(245,158,11,0.15)' }, { offset: 1, color: 'rgba(245,158,11,0)' }]) } }
        ]
    });
}