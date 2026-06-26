from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PATCH_INDEX = ROOT / "scripts" / "patch_index_dynamic_data.py"

bad_block = '''                const first = records[0];
                const last = records[records.length - 1];
                const variation = last.value - first.value;
                const signal = variation > 0 ? '+' : '';
                const variationText = `${signal}${variation.toFixed(2).replace('.', ',')} m`;
                const trendText = variation > 0.03 ? 'subindo' : variation < -0.03 ? 'baixando' : 'estável';

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
'''

good_block = '''                const first = records[0];
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
'''


def fix(path: Path):
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if bad_block in text:
        path.write_text(text.replace(bad_block, good_block, 1), encoding="utf-8")
        print(f"Corrigido: {path}")
        return True
    if "variation1dText" in text and "variation7dText" in text and "variation1d =" in text:
        print(f"Já estava corrigido: {path}")
        return False
    print(f"Bloco alvo não encontrado: {path}")
    return False

changed = fix(INDEX)
changed = fix(PATCH_INDEX) or changed

if not changed:
    print("Nenhuma alteração necessária no resumo dos últimos 7 dias.")
