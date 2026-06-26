from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PATCH = ROOT / "scripts" / "patch_index_dynamic_data.py"

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

patterns = [
    re.compile(
        r"                if \(summary\) \{\r?\n"
        r"                    summary\.textContent = `D-1: \$\{variation1dText\} · \$\{trendText\} · 7d: \$\{variation7dText\}`;\r?\n"
        r"                \}\r?\n",
        re.MULTILINE,
    ),
    re.compile(
        r"                if \(summary\) \{\r?\n"
        r"                    summary\.textContent = `.*?\$\{trendText\}.*?`;\r?\n"
        r"                \}\r?\n",
        re.DOTALL,
    ),
]


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if 'const trendClass = trendText ===' in text and 'summary.innerHTML = `' in text:
        print(f"Badge de status já aplicado em {path.name}.")
        return False

    for pattern in patterns:
        text, count = pattern.subn(new_block, text, count=1)
        if count:
            path.write_text(text, encoding="utf-8")
            print(f"Badge de status aplicado em {path.name}.")
            return True

    print(f"Bloco de resumo não encontrado em {path.name}; seguindo sem falhar.")
    return False

changed = False
if INDEX.exists():
    changed = patch_file(INDEX) or changed
if PATCH.exists():
    changed = patch_file(PATCH) or changed

if not changed:
    print("Nenhuma alteração necessária para badge de status.")
