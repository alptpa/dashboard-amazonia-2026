from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
collector_path = ROOT / "scripts" / "update_barcelos_data_v2.py"
patch_path = ROOT / "scripts" / "patch_index_dynamic_data.py"

collector = collector_path.read_text(encoding="utf-8")

old_collector = '''    d7 = delta(week_ref)
    trend = "estável"
    if d7 is not None and d7 > 0.05:
        trend = "subindo"
    elif d7 is not None and d7 < -0.05:
        trend = "baixando"

    return {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": now_iso(),
        "status": "ok",
        "latest": latest,
        "variation": {
            "last_24h_m": delta(previous),
            "last_7d_m": d7,
            "trend": trend,
        },
    }
'''

new_collector = '''    d1 = delta(previous)
    d7 = delta(week_ref)
    trend = "estável"
    if d1 is not None and d1 > 0.03:
        trend = "subindo"
    elif d1 is not None and d1 < -0.03:
        trend = "baixando"

    return {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": now_iso(),
        "status": "ok",
        "latest": latest,
        "variation": {
            "last_24h_m": d1,
            "last_7d_m": d7,
            "trend": trend,
            "trend_basis": "last_24h_m",
        },
    }
'''

if old_collector in collector:
    collector = collector.replace(old_collector, new_collector, 1)
elif '"trend_basis": "last_24h_m"' not in collector:
    raise SystemExit("Não foi possível localizar bloco de tendência no coletor.")
collector_path.write_text(collector, encoding="utf-8")

patch = patch_path.read_text(encoding="utf-8")

old_js = '''                const first = records[0];
                const last = records[records.length - 1];
                const variation = last.value - first.value;
                const signal = variation > 0 ? '+' : '';
                const variationText = `${signal}${variation.toFixed(2).replace('.', ',')} m`;
                const trendText = variation > 0.03 ? 'subindo' : variation < -0.03 ? 'baixando' : 'estável';

                if (summary) {
                    summary.textContent = `${formatDate(first.date)} a ${formatDate(last.date)} · ${variationText} · ${trendText}`;
                }
'''

new_js = '''                const first = records[0];
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
                    summary.textContent = `D-1: ${variation1dText} · ${trendText} · 7d: ${variation7dText}`;
                }
'''

if old_js in patch:
    patch = patch.replace(old_js, new_js, 1)
elif 'D-1: ${variation1dText}' not in patch:
    raise SystemExit("Não foi possível localizar bloco de resumo dos 7 dias.")
patch_path.write_text(patch, encoding="utf-8")

print("Regra de tendência ajustada: status baseado apenas em hoje vs dia anterior.")
