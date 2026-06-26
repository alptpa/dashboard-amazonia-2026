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

pattern_fetch = re.compile(
    r"        // Dados reais do CSV ANA, agrupados por média semanal\.\r?\n"
    r"        // Semana 1 = 01/06 a 07/06 de cada ano\. Período considerado: Junho a Outubro\.\r?\n"
    r"        async function fetchRiverData\(\) \{.*?\r?\n        \}\r?\n\r?\n        // 2\. Criação do Gráfico D3\.js de Comparativo Semanal",
    re.DOTALL,
)
html, count_fetch = pattern_fetch.subn(new_fetch_river_data + "\n        // 2. Criação do Gráfico D3.js de Comparativo Semanal", html)
if count_fetch != 1:
    raise SystemExit(f"Não foi possível substituir fetchRiverData. Substituições: {count_fetch}")

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

if old_init_snippet not in html:
    raise SystemExit("Não foi possível localizar o bloco antigo do nível atual.")
html = html.replace(old_init_snippet, new_init_snippet, 1)

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
            window.resizeTimer = setTimeout(() => drawChart(riverData), 200);
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

if 'max-width: min(260px, calc(100vw - 32px));' not in html:
    html = html.replace(
        '            z-index: 50;\n',
        '            z-index: 50;\n            max-width: min(260px, calc(100vw - 32px));\n',
        1,
    )

INDEX.write_text(html, encoding="utf-8")
print("index.html atualizado para consumir JSONs automáticos da ANA.")
