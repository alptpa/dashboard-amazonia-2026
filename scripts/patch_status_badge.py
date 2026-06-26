from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

html = INDEX.read_text(encoding="utf-8")

old_block = '''                if (summary) {
                    summary.textContent = `D-1: ${variation1dText} · ${trendText} · 7d: ${variation7dText}`;
                }
'''

new_block = '''                if (summary) {
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
'''

if old_block in html:
    html = html.replace(old_block, new_block, 1)
elif 'summary.innerHTML = `' in html and 'trendClass' in html:
    print("Badge de status já aplicado no index.html.")
else:
    raise SystemExit("Não foi possível localizar bloco de resumo para aplicar badge de status.")

INDEX.write_text(html, encoding="utf-8")
print("Badge de status aplicado: subindo verde, baixando vermelho e estável cinza.")
