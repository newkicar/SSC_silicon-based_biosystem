/**
 * overtime.js - 加班时长分析模块
 */
let echartsOvertimeCenter = null, echartsOvertimeDept = null;

async function loadOvertime() {
    try {
        const params = buildFilterParams();
        const data = await api('GET', `/api/dashboard/overtime?${params.toString()}`);
        const ot = data.data;

        // 图表1：各中心（纵向柱形+公司平均折线）
        renderOvertimeComboChart('chartOvertimeCenter', echartsOvertimeCenter, ot.center || {}, ot.company_avg || 0,
            function(chart) { echartsOvertimeCenter = chart; });

        // 图表2：各部门（纵向柱形+公司平均折线）
        renderOvertimeComboChart('chartOvertimeDept', echartsOvertimeDept, ot.department || {}, ot.company_avg || 0,
            function(chart) { echartsOvertimeDept = chart; });
    } catch (err) { console.error('Overtime load error:', err); }
}

function renderOvertimeComboChart(containerId, existingChart, seriesData, companyAvg, setChart) {
    const container = document.getElementById(containerId);
    if (!container) return;
    let chart = existingChart;
    if (!chart) {
        chart = echarts.init(container);
        window.addEventListener('resize', () => chart && chart.resize());
        setChart(chart);
    }

    const names = seriesData.names || [];
    const values = seriesData.values || [];
    const avgLine = new Array(names.length).fill(companyAvg);

    chart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross', crossStyle: { color: '#64748b' } },
            backgroundColor: '#1a2332',
            borderColor: '#2d3a4f',
            textStyle: { color: '#e2e8f0', fontSize: 12 },
            formatter: function(params) {
                let s = '<b>' + params[0].axisValue + '</b><br/>';
                params.forEach(p => {
                    if (p.seriesType === 'bar') {
                        s += p.marker + ' ' + p.seriesName + ': <b>' + p.value.toFixed(2) + 'h</b><br/>';
                    } else if (p.seriesType === 'line') {
                        s += p.marker + ' ' + p.seriesName + ': ' + p.value.toFixed(2) + 'h<br/>';
                    }
                });
                return s;
            }
        },
        legend: { top: 0, left: 'center', textStyle: { color: '#94a3b8', fontSize: 11 }, itemWidth: 14, itemHeight: 10 },
        grid: { left: '5%', right: '5%', top: 45, bottom: 60, containLabel: true },
        xAxis: {
            type: 'category',
            data: names,
            axisLabel: { color: '#94a3b8', fontSize: 11, rotate: names.length > 6 ? 30 : 0, interval: 0 },
            axisLine: { lineStyle: { color: '#2d3a4f' } },
            axisTick: { show: false }
        },
        yAxis: {
            type: 'value',
            name: '小时',
            nameTextStyle: { color: '#64748b', fontSize: 11 },
            axisLabel: { color: '#64748b', fontSize: 11 },
            axisLine: { show: false },
            splitLine: { lineStyle: { color: '#1e293b' } }
        },
        series: [
            {
                name: '人均加班时长',
                type: 'bar',
                data: values,
                barWidth: names.length > 8 ? '45%' : '35%',
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#3b82f6' },
                        { offset: 1, color: 'rgba(59,130,246,0.3)' }
                    ]),
                    borderRadius: [4, 4, 0, 0],
                },
                label: {
                    show: true,
                    position: 'top',
                    color: '#94a3b8',
                    fontSize: 10,
                    formatter: function(p) { return p.value.toFixed(1); }
                },
            },
            {
                name: '平均',
                type: 'line',
                data: avgLine,
                smooth: false,
                symbol: 'none',
                lineStyle: { color: '#f59e0b', width: 2, type: 'dashed' },
                label: {
                    show: true,
                    position: 'top',
                    distance: 8,
                    formatter: '平均: {c}h',
                    color: '#f59e0b',
                    fontSize: 11,
                },
            }
        ],
    }, true);
}