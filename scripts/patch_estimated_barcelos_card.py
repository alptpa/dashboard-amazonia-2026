from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

CARD_MARKER = "estimated-seven-day-level-chart"
SCRIPT_MARKER = "updateEstimatedSevenDayLevelChart"

ESTIMATED_CARD = '''

                <!-- Cartão de estimativa do nível de Barcelos com base em Serrinha e Moura -->
                <div class="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-xl flex-1">
                    <div class="flex justify-between items-start gap-3 mb-4">
                        <div>
                            <h2 class="text-sm font-bold text-zinc-100 uppercase tracking-wide flex items-center gap-2">
                                <i class="ph ph-chart-line text-indigo-400"></i>
                                Nível estimado Barcelos – últimos 7 dias
                            </h2>
                            <p id="estimated-seven-day-level-summary" class="text-[10px] text-zinc-500 mt-1">Carregando estimativa...</p>
                        </div>
                        <span class="bg-indigo-500/15 text-indigo-300 border border-indigo-500/20 px-2.5 py-1 rounded-full text-[10px] font-bold">ESTIMATIVA</span>
                    </div>
                    <div id="estimated-seven-day-level-chart" class="w-full h-[230px] relative">
                        <div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">
                            Carregando gráfico estimado...
                        </div>
                    </div>
                    <div id="estimated-seven-day-api-updated" class="mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-500 font-medium leading-relaxed">
                        Estimativa baseada em Serrinha (14420000) e Moura (14840000). Não é dado oficial da estação Barcelos.
                    </div>
                </div>
'''

ESTIMATED_SCRIPT = r'''

    <script>
        async function updateEstimatedSevenDayLevelChart() {
            const container = document.getElementById('estimated-seven-day-level-chart');
            const summary = document.getElementById('estimated-seven-day-level-summary');
            const footer = document.getElementById('estimated-seven-day-api-updated');
            if (!container || typeof d3 === 'undefined') return;

            try {
                const response = await fetch(`data/barcelos-estimado.json?ts=${Date.now()}`);
                if (!response.ok) throw new Error('Estimativa não disponível');
                const payload = await response.json();
                const records = (payload.records || [])
                    .filter(row => row.date && row.level_estimated_m !== null && row.level_estimated_m !== undefined)
                    .map(row => ({
                        date: row.date,
                        value: Number(row.level_estimated_m),
                        serrinha: Number(row.serrinha_level_m),
                        moura: Number(row.moura_level_m)
                    }))
                    .filter(row => Number.isFinite(row.value))
                    .slice(-7);

                if (!records.length) {
                    container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500 text-center px-4">Estimativa ainda não disponível. Aguardando dados de Serrinha e Moura.</div>';
                    if (summary) summary.textContent = 'Estimativa indisponível';
                    if (footer) footer.textContent = 'Sem dados suficientes em Serrinha e Moura para estimar Barcelos.';
                    return;
                }

                container.innerHTML = '';
                const margin = { top: 22, right: 16, bottom: 28, left: 38 };
                const width = Math.max(container.clientWidth || 320, 280);
                const height = Math.max(container.clientHeight || 230, 200);
                const innerWidth = width - margin.left - margin.right;
                const innerHeight = height - margin.top - margin.bottom;

                const svg = d3.select(container)
                    .append('svg')
                    .attr('width', width)
                    .attr('height', height)
                    .attr('viewBox', `0 0 ${width} ${height}`)
                    .attr('preserveAspectRatio', 'xMidYMid meet');

                const x = d3.scalePoint()
                    .domain(records.map(row => row.date))
                    .range([0, innerWidth])
                    .padding(0.35);

                const minValue = d3.min(records, row => row.value);
                const maxValue = d3.max(records, row => row.value);
                const spread = Math.max((maxValue - minValue) || 0.08, 0.08);
                const y = d3.scaleLinear()
                    .domain([minValue - spread * 0.25, maxValue + spread * 0.35])
                    .nice()
                    .range([innerHeight, 0]);

                const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

                g.append('g')
                    .attr('class', 'grid')
                    .call(d3.axisLeft(y).ticks(4).tickSize(-innerWidth).tickFormat(''))
                    .selectAll('line')
                    .attr('stroke', '#27272a')
                    .attr('stroke-dasharray', '3 3');

                g.selectAll('.grid path').attr('stroke', 'none');

                g.append('g')
                    .attr('transform', `translate(0,${innerHeight})`)
                    .call(d3.axisBottom(x).tickFormat(date => {
                        const [year, month, day] = date.split('-');
                        return `${day}/${month}`;
                    }))
                    .call(axis => axis.select('.domain').attr('stroke', '#3f3f46'))
                    .call(axis => axis.selectAll('line').attr('stroke', '#3f3f46'))
                    .call(axis => axis.selectAll('text').attr('fill', '#a1a1aa').attr('font-size', 10).attr('font-weight', 700));

                g.append('g')
                    .call(d3.axisLeft(y).ticks(4).tickFormat(value => `${Number(value).toFixed(2).replace('.', ',')} m`))
                    .call(axis => axis.select('.domain').attr('stroke', 'none'))
                    .call(axis => axis.selectAll('line').attr('stroke', 'none'))
                    .call(axis => axis.selectAll('text').attr('fill', '#71717a').attr('font-size', 10).attr('font-weight', 700));

                const line = d3.line()
                    .x(row => x(row.date))
                    .y(row => y(row.value))
                    .curve(d3.curveMonotoneX);

                g.append('path')
                    .datum(records)
                    .attr('fill', 'none')
                    .attr('stroke', '#818cf8')
                    .attr('stroke-width', 3)
                    .attr('stroke-linecap', 'round')
                    .attr('stroke-linejoin', 'round')
                    .attr('stroke-dasharray', '6 4')
                    .attr('d', line);

                g.selectAll('.estimated-point')
                    .data(records)
                    .enter()
                    .append('circle')
                    .attr('class', 'estimated-point')
                    .attr('cx', row => x(row.date))
                    .attr('cy', row => y(row.value))
                    .attr('r', 4.5)
                    .attr('fill', '#c4b5fd')
                    .attr('stroke', '#18181b')
                    .attr('stroke-width', 2);

                g.selectAll('.estimated-label')
                    .data(records)
                    .enter()
                    .append('text')
                    .attr('class', 'estimated-label')
                    .attr('x', row => x(row.date))
                    .attr('y', row => y(row.value) - 10)
                    .attr('text-anchor', 'middle')
                    .attr('fill', '#e0e7ff')
                    .attr('font-size', 10)
                    .attr('font-weight', 800)
                    .text(row => `${row.value.toFixed(2).replace('.', ',')}m`);

                const first = records[0];
                const previous = records.length >= 2 ? records[records.length - 2] : null;
                const last = records[records.length - 1];
                const variation7d = last.value - first.value;
                const variation1d = previous ? last.value - previous.value : 0;
                const signal7d = variation7d > 0 ? '+' : '';
                const variation7dText = `${signal7d}${variation7d.toFixed(2).replace('.', ',')} m`;
                const trendText = variation1d > 0 ? 'subindo' : variation1d < 0 ? 'secando' : 'estável';

                if (summary) {
                    const trendClass = trendText === 'subindo'
                        ? 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
                        : trendText === 'secando'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                            : 'bg-amber-500/15 text-amber-400 border border-amber-500/20';

                    summary.innerHTML = `
                        <span>7d: ${variation7dText}</span>
                        <span class="mx-1 text-zinc-600">·</span>
                        <span class="${trendClass} px-2 py-0.5 rounded-full text-[10px] font-bold uppercase">${trendText}</span>
                    `;
                }

                if (footer) {
                    const generated = payload.generated_at ? new Date(payload.generated_at) : null;
                    const generatedText = generated && !Number.isNaN(generated.getTime())
                        ? generated.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                        : '--';
                    const model = payload.method?.model || {};
                    const confidence = model.confidence ? ` · confiança ${model.confidence}` : '';
                    const mae = model.mean_absolute_error_m !== null && model.mean_absolute_error_m !== undefined
                        ? ` · erro médio hist. ${Number(model.mean_absolute_error_m).toFixed(2).replace('.', ',')} m`
                        : '';
                    footer.innerHTML = `Estimativa baseada em Serrinha (14420000) e Moura (14840000).<br>Atualização do cálculo: ${generatedText}${confidence}${mae}. Não é dado oficial da estação Barcelos.`;
                }
            } catch (error) {
                console.error('Erro ao carregar estimativa de Barcelos:', error);
                container.innerHTML = '<div class="absolute inset-0 flex items-center justify-center text-xs text-zinc-500 text-center px-4">Não foi possível carregar a estimativa de Barcelos.</div>';
                if (summary) summary.textContent = 'Estimativa indisponível';
            }
        }

        updateEstimatedSevenDayLevelChart();
        window.addEventListener('resize', updateEstimatedSevenDayLevelChart);
    </script>
'''


def main():
    html = INDEX.read_text(encoding="utf-8")
    changed = False

    if CARD_MARKER not in html:
        marker = "                <!-- Cartão de Chuva Prevista -->"
        if marker not in html:
            raise SystemExit("Não foi possível localizar o ponto de inserção do card de estimativa.")
        html = html.replace(marker, ESTIMATED_CARD + "\n" + marker, 1)
        changed = True
        print("Card de estimativa inserido no dashboard.")
    else:
        print("Card de estimativa já existe no dashboard.")

    if SCRIPT_MARKER not in html:
        if "</body>" not in html:
            raise SystemExit("Não foi possível localizar </body> para inserir script de estimativa.")
        html = html.replace("</body>", ESTIMATED_SCRIPT + "\n</body>", 1)
        changed = True
        print("Script do gráfico estimado inserido no dashboard.")
    else:
        print("Script do gráfico estimado já existe no dashboard.")

    if changed:
        INDEX.write_text(html, encoding="utf-8")
        print("Aplicado: card estimado de Barcelos por Serrinha e Moura.")
    else:
        print("Nenhuma alteração necessária para o card estimado.")


if __name__ == "__main__":
    main()
