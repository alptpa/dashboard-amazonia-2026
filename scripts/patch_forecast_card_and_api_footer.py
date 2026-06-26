from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

html = INDEX.read_text(encoding="utf-8")

# 1) Troca o antigo card Caixa Equipa pelo card de previsão da semana 2 de setembro/2026.
forecast_card = '''            <!-- Cartão 3: Previsão de nível para a semana 2 de setembro/2026 -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex flex-col justify-between">
                <h3 class="text-xs font-bold text-indigo-400 tracking-wider mb-2 flex items-center gap-2">
                    <i class="ph ph-chart-line-up text-lg"></i> PREVISÃO SET/2026
                </h3>
                <div class="flex flex-col">
                    <div class="flex items-baseline gap-2">
                        <span id="september-week2-forecast" class="text-3xl lg:text-4xl font-extrabold text-indigo-400">--</span>
                        <span class="text-sm text-zinc-500 font-medium">m</span>
                    </div>
                    <p id="september-week2-label" class="text-[10px] text-zinc-500 font-medium mb-1 mt-1">Semana 2 de setembro · 07 a 13/09</p>
                    <div class="w-full bg-zinc-800 h-1.5 rounded-full">
                        <div id="september-week2-bar" class="bg-indigo-500 h-1.5 rounded-full" style="width: 0%"></div>
                    </div>
                </div>
            </div>'''

card_pattern = re.compile(
    r'''            <!-- Cartão 3: .*? -->\r?\n            <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex flex-col justify-between">\r?\n                <h3 class="text-xs font-bold text-indigo-400 tracking-wider mb-2 flex items-center gap-2">\r?\n                    <i class="ph ph-currency-circle-dollar text-lg"></i> CAIXA EQUIPA\r?\n                </h3>.*?\r?\n            </div>''',
    re.DOTALL,
)
html, card_count = card_pattern.subn(forecast_card, html, count=1)
if card_count == 0 and 'id="september-week2-forecast"' not in html:
    raise SystemExit("Não foi possível localizar o card Caixa Equipa.")

# 2) Garante espaço de rodapé no card dos últimos 7 dias.
old_chart_block = '''                    <div id="seven-day-level-chart" class="w-full h-[230px] relative">
                        <div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">
                            Carregando gráfico...
                        </div>
                    </div>
                </div>'''
new_chart_block = '''                    <div id="seven-day-level-chart" class="w-full h-[230px] relative">
                        <div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">
                            Carregando gráfico...
                        </div>
                    </div>
                    <div id="seven-day-api-updated" class="mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-500 font-medium">
                        Última atualização ANA: --
                    </div>
                </div>'''
if old_chart_block in html:
    html = html.replace(old_chart_block, new_chart_block, 1)

# 3) Injeta/atualiza função de previsão do card superior.
forecast_function = '''        function updateSeptemberForecastCard(data) {
            const valueElement = document.getElementById('september-week2-forecast');
            const labelElement = document.getElementById('september-week2-label');
            const barElement = document.getElementById('september-week2-bar');
            if (!valueElement) return;

            // Semana 2 de setembro/2026 = 07/09 a 13/09.
            // Pela regra do projeto, semana 1 começa em 01/06; então este período é a semana 15.
            const targetWeek = 15;
            const target = (data || []).find(item => item.week === targetWeek);
            const forecast = target?.y2026Forecast ?? target?.y2026 ?? null;

            if (forecast === null || forecast === undefined || Number.isNaN(Number(forecast))) {
                valueElement.textContent = '--';
                if (labelElement) labelElement.textContent = 'Semana 2 de setembro · previsão indisponível';
                if (barElement) barElement.style.width = '0%';
                return;
            }

            const level = Number(forecast);
            valueElement.textContent = level.toFixed(2).replace('.', ',');
            if (labelElement) labelElement.textContent = 'Semana 2 de setembro · 07 a 13/09';

            // Barra visual simples: escala aproximada de 0 a 11m, igual à escala principal do gráfico.
            const percent = Math.max(0, Math.min(100, (level / 11) * 100));
            if (barElement) barElement.style.width = `${percent.toFixed(0)}%`;
        }

'''
if 'function updateSeptemberForecastCard(data)' not in html:
    marker = '        async function fetchRiverData() {'
    if marker not in html:
        raise SystemExit("Não foi possível localizar ponto para inserir updateSeptemberForecastCard.")
    html = html.replace(marker, forecast_function + marker, 1)

# 4) Chama a função após carregar riverData.
old_after_level = '''                if (currentLevel !== null && currentLevel !== undefined) {
                    // Formatação à portuguesa (com vírgula) e força duas casas decimais
                    riverLevelElement.textContent = Number(currentLevel).toFixed(2).replace('.', ',');
                    riverLevelElement.classList.add('text-indigo-400'); 
                    setTimeout(() => riverLevelElement.classList.remove('text-indigo-400'), 1000);
                }
'''
new_after_level = '''                if (currentLevel !== null && currentLevel !== undefined) {
                    // Formatação à portuguesa (com vírgula) e força duas casas decimais
                    riverLevelElement.textContent = Number(currentLevel).toFixed(2).replace('.', ',');
                    riverLevelElement.classList.add('text-indigo-400'); 
                    setTimeout(() => riverLevelElement.classList.remove('text-indigo-400'), 1000);
                }

                updateSeptemberForecastCard(riverData);
'''
if old_after_level in html and 'updateSeptemberForecastCard(riverData);' not in html:
    html = html.replace(old_after_level, new_after_level, 1)

# 5) Redesenha o card no resize junto com os gráficos.
if 'drawChart(riverData);\n                updateSeptemberForecastCard(riverData);' not in html:
    html = html.replace('drawChart(riverData);\n                updateSevenDayLevelChart();', 'drawChart(riverData);\n                updateSeptemberForecastCard(riverData);\n                updateSevenDayLevelChart();')

# 6) Atualiza função dos 7 dias para preencher o rodapé da última atualização ANA.
# Usamos um patch simples logo após carregar o payload.
old_payload_line = '''                const payload = await response.json();
                const records = (payload.records || [])'''
new_payload_line = '''                const payload = await response.json();
                const updatedElement = document.getElementById('seven-day-api-updated');
                if (updatedElement) {
                    const generatedAt = payload.generated_at;
                    let updatedText = '--';
                    if (generatedAt) {
                        const updatedDate = new Date(generatedAt);
                        if (!Number.isNaN(updatedDate.getTime())) {
                            updatedText = updatedDate.toLocaleString('pt-BR', {
                                day: '2-digit', month: '2-digit', year: 'numeric',
                                hour: '2-digit', minute: '2-digit'
                            });
                        } else {
                            updatedText = String(generatedAt);
                        }
                    }
                    updatedElement.textContent = `Última atualização ANA: ${updatedText}`;
                }
                const records = (payload.records || [])'''
if old_payload_line in html and 'seven-day-api-updated' not in html[html.find('const payload = await response.json();'):html.find('const payload = await response.json();') + 800]:
    html = html.replace(old_payload_line, new_payload_line, 1)

INDEX.write_text(html, encoding="utf-8")
print("Aplicado: rodapé de atualização ANA e card de previsão de setembro/2026.")
