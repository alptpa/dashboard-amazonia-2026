from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PATCH_INDEX = ROOT / "scripts" / "patch_index_dynamic_data.py"

new_block = '''                const first = records[0];
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
'''

summary_pattern = re.compile(
    r"                const first = records\[0\];\r?\n"
    r"                const previous = records\.length >= 2 \? records\[records\.length - 2\] : null;\r?\n"
    r"                const last = records\[records\.length - 1\];\r?\n"
    r"                const variation7d = last\.value - first\.value;\r?\n"
    r"                const variation1d = previous \? last\.value - previous\.value : 0;\r?\n"
    r".*?"
    r"                if \(summary\) \{\r?\n"
    r".*?"
    r"                \}\r?\n",
    re.DOTALL,
)


def fix(path: Path):
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")

    updated, count = summary_pattern.subn(new_block, text, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")
        print(f"Semáforo corrigido em: {path}")
        return True

    if "trendText = variation1d > 0 ? 'subindo' : variation1d < 0 ? 'secando' : 'estável'" in text:
        print(f"Semáforo já estava corrigido em: {path}")
        return False

    print(f"Bloco alvo não encontrado em: {path}")
    return False


changed = fix(INDEX)
changed = fix(PATCH_INDEX) or changed

if not changed:
    print("Nenhuma alteração necessária no semáforo dos últimos 7 dias.")
