from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_barcelos_data_v2.py"

text = SCRIPT.read_text(encoding="utf-8")

old = 'for range_value in ("HORA_24", "HORA_1"):'
new = 'for range_value in ("DIAS_14", "HORA_24", "HORA_1"):'

if new in text:
    print("DIAS_14 já está habilitado na coleta.")
elif old in text:
    SCRIPT.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("DIAS_14 habilitado temporariamente na coleta ANA.")
else:
    raise SystemExit("Não foi possível localizar lista de ranges da coleta ANA.")
