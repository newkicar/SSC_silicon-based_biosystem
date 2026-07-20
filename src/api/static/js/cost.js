/**
 * cost.js - 各部门成本包使用情况图表
 */
let echartsCostAnalysis = null;

async function loadCostAnalysis() {
    try {
        const params = new URLSearchParams();
        const company = document.getElementById('filterCompany').value;
        const center = document.getElementById('filterCenter').value;
        const department = document.getElementById('filterDepartment').value;
        const month = document.getElementById('filterMonth').value;
        if (company) params.set('company', company);
        if (center) params.set('center', center);
        if (department) params.set('department', department);
        if (month) params.set('month', month);
        const data = await api('GET', `/api/dashboard/cost-analysis?${params.toString()}`);
        const d = data.data;
        const container = document.getElementById('chartCostAnalysis');
        if (!container) return;
        if (!echartsCostAnalysis) { echartsCostAnalysis = echarts.init(container); window.addEventListener('resize', () => echartsCostAnalysis && echartsCostAnalysis.resize()); }
        const names = d.names || [];
        const actualW = (d.actual || []).map(v => Math.round(v / 10000 * 10) / 10);
        const budgetW = (d.budget || []).map(v => Math.round(v / 10000 * 10) / 10);
        const ratio = d.ratio || [];
        echartsCostAnalysis.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#64748b' } }, backgroundColor: '#1a2332', borderColor: '#2d3a4f', textStyle: { color: '#e2e8f0', fontSize: 12 },
                formatter: function(params) { let s = '<b>' + params[0].axisValue + '</b><br/>'; params.forEach(p => { if (p.seriesName === '使用率') s += p.marker + ' 使用率: <b>' + p.value.toFixed(1) + '%</b><br/>'; else s += p.marker + ' ' + p.seriesName + ': ' + p.value.toFixed(1) + '万<br/>'; }); return s; } },
            legend: { top: 0, left: 'center', textStyle: { color: '#94a3b8', fontSize: 11 }, itemWidth: 14, itemHeight: 10 },
            grid: { left: '5%', right: '8%', top: 45, bottom: 60, containLabel: true },
            xAxis: { type: 'category', data: names, axisLabel: { color: '#94a3b8', fontSize: 11, rotate: names.length > 6 ? 30 : 0, interval: 0 }, axisLine: { lineStyle: { color: '#2d3a4f' } }, axisTick: { show: false } },
            yAxis: [
                { type: 'value', name: '万元', nameTextStyle: { color: '#64748b', fontSize: 11 }, axisLabel: { color: '#64748b', fontSize: 11 }, axisLine: { show: false }, splitLine: { lineStyle: { color: '#1e293b' } } },
                { type: 'value', name: '使用率', nameTextStyle: { color: '#64748b', fontSize: 11 }, axisLabel: { color: '#64748b', fontSize: 11, formatter: '{value}%' }, axisLine: { show: false }, splitLine: { show: false } }
            ],
            series: [
                { name: '实际成本', type: 'bar', data: actualW, barWidth: '30%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#3b82f6' }, { offset: 1, color: 'rgba(59,130,246,0.3)' }]), borderRadius: [4, 4, 0, 0] }, label: { show: names.length <= 10, position: 'top', color: '#94a3b8', fontSize: 10, formatter: function(p) { return p.value.toFixed(1); } } },
                { name: '管控成本', type: 'bar', data: budgetW, barWidth: '30%', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#8b5cf6' }, { offset: 1, color: 'rgba(139,92,246,0.3)' }]), borderRadius: [4, 4, 0, 0] }, label: { show: names.length <= 10, position: 'top', color: '#94a3b8', fontSize: 10, formatter: function(p) { return p.value.toFixed(1); } } },
                { name: '使用率', type: 'line', yAxisIndex: 1, data: ratio, smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#f59e0b', width: 2 }, itemStyle: { color: '#f59e0b', borderColor: '#1a2332', borderWidth: 2 }, label: { show: names.length <= 10, position: 'top', color: '#f59e0b', fontSize: 10, formatter: function(p) { return p.value.toFixed(1) + '%'; } } }
            ],
            dataZoom: [],
        }, true);
    } catch (err) { console.error('Cost analysis load error:', err); }
}