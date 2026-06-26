from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

html = INDEX.read_text(encoding="utf-8")

new_fetch_river_data = r'''        // Dados do gráfico carregados dos JSONs gerados pela automação da ANA.
        // Semana 1 = 01/06 a 07/06 de cada ano. Período considerado: Junho a Outubro.
        async function fetchRiverData() {
            const response = await fetch(`data/barcelos-semanal.json?ts=${Date.now()}`);
            if (!response.ok) {
                throw new Error(`Falha ao carregar barcelos-semanal.json: ${response.status}`);
            }

            const payload = await response.json();
            const weekly = payload.weekly || [];
            const monthLabels = {
                1: 'Jun', 2: 'Jun', 3: 'Jun', 4: 'Jun',
                5: 'Jun/Jul', 6: 'Jul', 7: 'Jul', 8: 'Jul',
                9: 'Jul/Ago', 10: 'Ago', 11: 'Ago', 12: 'Ago', 13: 'Ago',
                14: 'Set', 15: 'Set', 16: 'Set', 17: 'Set',
                18: 'Out', 19: 'Out', 20: 'Out', 21: 'Out', 22: 'Out'
            };

            const data = Array.from({ length: 22 }, (_, index) => {
                const week = index + 1;
                return {
                    week,
                    month: monthLabels[week] || '',
                    y2020: null,
                    y2021: null,
                    y2022: null,
                    y2023: null,
                    y2024: null,
                    y2025: null,
                    y2026: null,
                    y2026Forecast: null
                };
            });

            weekly.forEach(item => {
                const week = Number(item.week);
                const year = Number(item.year);
                const value = Number(item.level_avg_m);
                if (!week || week < 1 || week > 22 || !year || Number.isNaN(value)) return;
                const key = `y${year}`;
                if (Object.prototype.hasOwnProperty.call(data[week - 1], key)) {
                    data[week - 1][key] = value;
                }
            });

            // Previsão 2026: usa a variação média percentual semanal dos anos históricos.
            const historicalYears = [2020, 2021, 2022, 2023, 2024, 2025];
            const actual2026 = data.filter(d => d.y2026 !== null && d.y2026 !== undefined);
            const lastActual = actual2026[actual2026.length - 1];

            if (lastActual) {
                let forecastValue = lastActual.y2026;
                for (let week = lastActual.week + 1; week <= 22; week++) {
                    const previousRow = data[week - 2];
                    const currentRow = data[week - 1];
                    const changes = [];

                    historicalYears.forEach(year => {
                        const key = `y${year}`;
                        const previousValue = previousRow?.[key];
                        const currentValue = currentRow?.[key];
                        if (previousValue && currentValue) {
                            changes.push((currentValue - previousValue) / previousValue);
                        }
                    });

                    if (changes.length > 0) {
                        const avgChange = changes.reduce((sum, value) => sum + value, 0) / changes.length;
                        forecastValue = forecastValue * (1 + avgChange);
                        currentRow.y2026Forecast = Number(forecastValue.toFixed(2));
                    }
                }
            }

            return data;
        }
'''

pattern_fetch_static = re.compile(
    r"        // Dados reais do CSV ANA, agrupados por média semanal\.\r?\n"
    r"        // Semana 1 = 01/06 a 07/06 de cada ano\. Período considerado: Junho a Outubro\.\r?\n"
    r"        async function fetchRiverData\(\) \{.*?\r?\n        \}\r?\n\r?\n        // 2\. Criação do Gráfico D3\.js de Comparativo Semanal",
    re.DOTALL,
)
html, count_static = pattern_fetch_static.subn(new_fetch_river_data + "\n        // 2. Criação do Gráfico D3.js de Comparativo Semanal", html)

pattern_fetch_dynamic = re.compile(
    r"        // Dados do gráfico carregados dos JSONs gerados pela automação da ANA\.\r?\n"
    r"        // Semana 1 = 01/06 a 07/06 de cada ano\. Período considerado: Junho a Outubro\.\r?\n"
    r"        async function fetchRiverData\(\) \{.*?\r?\n        \}\r?\n\r?\n        // 2\. Criação do Gráfico D3\.js de Comparativo Semanal",
    re.DOTALL,
)
if count_static == 0:
    html, count_dynamic = pattern_fetch_dynamic.subn(new_fetch_river_data + "\n        // 2. Criação do Gráfico D3.js de Comparativo Semanal", html)
    if count_dynamic == 0:
        raise SystemExit("Não foi possível localizar fetchRiverData para atualizar.")

old_init_snippet = '''                riverData = await fetchRiverData();

                const current2026Data = riverData.filter(d => d.y2026 !== null).pop();

                if (current2026Data) {
                    // Formatação à portuguesa (com vírgula) e força duas casas decimais
                    riverLevelElement.textContent = current2026Data.y2026.toFixed(2).replace('.', ',');
                    riverLevelElement.classList.add('text-indigo-400'); 
                    setTimeout(() => riverLevelElement.classList.remove('text-indigo-400'), 1000);
                }
'''

new_init_snippet = '''                const [loadedRiverData, currentLevelPayload] = await Promise.all([
                    fetchRiverData(),
                    fetch(`data/barcelos-atual.json?ts=${Date.now()}`).then(response => response.ok ? response.json() : null).catch(() => null)
                ]);

                riverData = loadedRiverData;

                const current2026Data = riverData.filter(d => d.y2026 !== null && d.y2026 !== undefined).pop();
                const currentLevel = currentLevelPayload?.latest?.level_last_m ?? currentLevelPayload?.latest?.level_avg_m ?? current2026Data?.y2026;

                if (currentLevel !== null && currentLevel !== undefined) {
                    // Formatação à portuguesa (com vírgula) e força duas casas decimais
                    riverLevelElement.textContent = Number(currentLevel).toFixed(2).replace('.', ',');
                    riverLevelElement.classList.add('text-indigo-400'); 
                    setTimeout(() => riverLevelElement.classList.remove('text-indigo-400'), 1000);
                }
'''

if old_init_snippet in html:
    html = html.replace(old_init_snippet, new_init_snippet, 1)
elif new_init_snippet not in html:
    raise SystemExit("Não foi possível localizar o bloco do nível atual.")

old_financial_card_pattern = re.compile(
    r"\n\s*<!-- Cartão de Alertas/Avisos \(Baseado nos dados reais de Depósitos e Custos\) -->\r?\n"
    r"\s*<div class=\"bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex-1\">.*?\r?\n\s*</div>\r?\n\r?\n\s*<!-- Cartão de Chuva Prevista -->",
    re.DOTALL,
)

seven_day_card = r'''
                <!-- Cartão de acompanhamento do nível nos últimos 7 dias -->
                <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex-1">
                    <div class="flex justify-between items-start gap-3 mb-4">
                        <div>
                            <h2 class="text-sm font-bold text-zinc-100 uppercase tracking-wide flex items-center gap-2">
                                <i class="ph ph-trend-up text-emerald-400"></i>
                                Nível últimos 7 dias
                            </h2>
                            <p id="seven-day-level-summary" class="text-[10px] text-zinc-500 mt-1">Carregando histórico diário...</p>
                        </div>
                        <span class="bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-full text-[10px] font-bold">ANA</span>
                    </div>
                    <div id="seven-day-level-chart" class="w-full h-[230px] relative">
                        <div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">
                            Carregando gráfico...
                        </div>
                    </div>
                </div>

                <!-- Cartão de Chuva Prevista -->'''

html, count_financial = old_financial_card_pattern.subn("\n" + seven_day_card, html)
if count_financial == 0 and 'id="seven-day-level-chart"' not in html:
    raise SystemExit("Não foi possível substituir o card financeiro.")

seven_day_function = r'''        async function updateSevenDayLevelChart() {
            const container = document.getElementById('seven-day-level-chart');
            const summary = document.getElementById('seven-day-level-summary');
            if (!container) return;

            try {
                const response = await fetch(`data/barcelos-diario.json?ts=${Date.now()}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const payload = await response.json();
                const records = (payload.records || [])
                    .filter(item => item.date && (item.level_last_m ?? item.level_avg_m) !== undefined)
                    .sort((a, b) => a.date.localeCompare(b.date))
                    .slice(-7)
                    .map(item => ({
                        date: item.date,
                        value: Number(item.level_last_m ?? item.level_avg_m),
                        samples: item.samples || 1
                    }));

                container.innerHTML = '';

                if (records.length === 0) {
                    container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">Sem dados recentes.</div>';
                    if (summary) summary.textContent = 'Sem dados recentes disponíveis';
                    return;
                }

                const formatDate = (dateString) => {
                    const [year, month, day] = dateString.split('-');
                    return `${day}/${month}`;
                };

                const width = container.clientWidth || 320;
                const height = container.clientHeight || 230;
                const margin = { top: 28, right: 18, bottom: 34, left: 36 };
                const innerWidth = width - margin.left - margin.right;
                const innerHeight = height - margin.top - margin.bottom;

                const minValue = d3.min(records, d => d.value);
                const maxValue = d3.max(records, d => d.value);
                const padding = Math.max(0.08, (maxValue - minValue) * 0.35 || 0.08);

                const x = d3.scalePoint()
                    .domain(records.map(d => d.date))
                    .range([0, innerWidth])
                    .padding(0.5);

                const y = d3.scaleLinear()
                    .domain([minValue - padding, maxValue + padding])
                    .range([innerHeight, 0])
                    .nice();

                const svg = d3.select(container)
                    .append('svg')
                    .attr('width', width)
                    .attr('height', height)
                    .append('g')
                    .attr('transform', `translate(${margin.left},${margin.top})`);

                svg.append('g')
                    .call(d3.axisLeft(y).ticks(4).tickFormat(d => `${Number(d).toFixed(1)}m`).tickSize(-innerWidth).tickPadding(8))
                    .call(g => g.select('.domain').remove())
                    .call(g => g.selectAll('line').attr('stroke', '#27272a').attr('stroke-dasharray', '4,4'))
                    .call(g => g.selectAll('text').attr('class', 'text-[10px] font-semibold fill-zinc-500'));

                svg.append('g')
                    .attr('transform', `translate(0,${innerHeight})`)
                    .call(d3.axisBottom(x).tickFormat(formatDate).tickSize(0).tickPadding(10))
                    .call(g => g.select('.domain').remove())
                    .call(g => g.selectAll('text').attr('class', 'text-[10px] font-bold fill-zinc-500'));

                const line = d3.line()
                    .x(d => x(d.date))
                    .y(d => y(d.value))
                    .curve(d3.curveMonotoneX);

                svg.append('path')
                    .datum(records)
                    .attr('fill', 'none')
                    .attr('stroke', '#34d399')
                    .attr('stroke-width', 3)
                    .style('filter', 'drop-shadow(0 0 4px rgba(52,211,153,0.45))')
                    .attr('d', line);

                svg.selectAll('.seven-day-dot')
                    .data(records)
                    .enter()
                    .append('circle')
                    .attr('class', 'seven-day-dot')
                    .attr('cx', d => x(d.date))
                    .attr('cy', d => y(d.value))
                    .attr('r', 4.5)
                    .attr('fill', '#34d399')
                    .attr('stroke', '#064e3b')
                    .attr('stroke-width', 2);

                svg.selectAll('.seven-day-label')
                    .data(records)
                    .enter()
                    .append('text')
                    .attr('class', 'seven-day-label')
                    .attr('x', d => x(d.date))
                    .attr('y', d => y(d.value) - 10)
                    .attr('text-anchor', 'middle')
                    .attr('class', 'text-[10px] font-extrabold fill-emerald-300')
                    .text(d => `${d.value.toFixed(2).replace('.', ',')}m`);

                const first = records[0];
                const previous = records.length >= 2 ? records[records.length - 2] : null;
                const last = records[records.length - 1];
                const variation7d = last.value - first.value;
                const variation1d = previous ? last.value - previous.value : 0;
                const signal1d = variation1d > 0 ? '+' : '';
                const signal7d = variation7d > 0 ? '+' : '';
                const variation1dText = `${signal1d}${variation1d.toFixed(2).replace('.', ',')} m`;
                const variation7dText = `${signal7d}${variation7d.toFixed(2).replace('.', ',')} m`;
                const trendText = variation1d > 0.03 ? 'subindo' : variation1d < -0.03 ? 'baixando' : 'estável';

                if (summary) {
                    const trendClass = trendText === 'subindo'
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                        : trendText === 'baixando'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
                            : 'bg-zinc-700/40 text-zinc-300 border border-zinc-600/40';

                    summary.innerHTML = `
                        <span>D-1: ${variation1dText}</span>
                        <span class="mx-1 text-zinc-600">·</span>
                        <span class="${trendClass} px-2 py-0.5 rounded-full text-[10px] font-bold uppercase">${trendText}</span>
                        <span class="mx-1 text-zinc-600">·</span>
                        <span>7d: ${variation7dText}</span>
                    `;
                }
            } catch (error) {
                console.error('Erro ao carregar gráfico dos últimos 7 dias:', error);
                container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-xs text-rose-400">Erro ao carregar últimos 7 dias.</div>';
                if (summary) summary.textContent = 'Não foi possível carregar o histórico diário';
            }
        }
'''

if 'async function updateSevenDayLevelChart()' not in html:
    marker = '        updateRainForecast();\n\n'
    if marker not in html:
        raise SystemExit("Não foi possível localizar updateRainForecast para inserir gráfico de 7 dias.")
    html = html.replace(marker, marker + seven_day_function + '\n        updateSevenDayLevelChart();\n\n', 1)
elif 'updateSevenDayLevelChart();' not in html:
    html = html.replace('        updateRainForecast();\n\n', '        updateRainForecast();\n        updateSevenDayLevelChart();\n\n', 1)

old_resize = '''        window.addEventListener('resize', () => {
            clearTimeout(window.resizeTimer);
            window.resizeTimer = setTimeout(() => drawChart(riverData), 200);
        });
'''

new_resize = '''        function hideChartTooltip() {
            const tooltipElement = document.getElementById('tooltip');
            if (tooltipElement) {
                tooltipElement.style.opacity = '0';
                tooltipElement.style.left = '-9999px';
                tooltipElement.style.top = '-9999px';
            }

            try {
                d3.selectAll('.overlay').dispatch('mouseout');
            } catch (error) {
                // D3 pode ainda não estar pronto durante mudanças rápidas de orientação.
            }
        }

        window.addEventListener('resize', () => {
            hideChartTooltip();
            clearTimeout(window.resizeTimer);
            window.resizeTimer = setTimeout(() => {
                drawChart(riverData);
                updateSevenDayLevelChart();
            }, 200);
        });

        window.addEventListener('orientationchange', hideChartTooltip);
        window.addEventListener('scroll', hideChartTooltip, { passive: true });
        document.addEventListener('touchstart', (event) => {
            const chartContainer = document.getElementById('chart-container');
            if (chartContainer && !chartContainer.contains(event.target)) {
                hideChartTooltip();
            }
        }, { passive: true });
        document.addEventListener('visibilitychange', hideChartTooltip);
'''

if old_resize in html:
    html = html.replace(old_resize, new_resize, 1)
elif 'window.resizeTimer = setTimeout(() => drawChart(riverData), 200);' in html:
    html = html.replace(
        'window.resizeTimer = setTimeout(() => drawChart(riverData), 200);',
        "window.resizeTimer = setTimeout(() => {\n                drawChart(riverData);\n                updateSevenDayLevelChart();\n            }, 200);",
        1,
    )

if 'max-width: min(260px, calc(100vw - 32px));' not in html:
    html = html.replace(
        '            z-index: 50;\n',
        '            z-index: 50;\n            max-width: min(260px, calc(100vw - 32px));\n',
        1,
    )

INDEX.write_text(html, encoding="utf-8")
print("index.html atualizado: JSONs ANA, gráfico 7 dias e remoção dos avisos financeiros.")
