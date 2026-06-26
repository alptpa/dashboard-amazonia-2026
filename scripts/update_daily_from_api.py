import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

STATION_ID = os.getenv("ANA_STATION_ID", "14480002")
STATION_LABEL = os.getenv("ANA_STATION_LABEL", "5 - 14480002 - BARCELOS")
API_BASE = os.getenv("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas")
TZ = timezone(timedelta(hours=-3))

DAILY_FILE = DATA / "barcelos-diario.json"
CURRENT_FILE = DATA / "barcelos-atual.json"
WEEKLY_FILE = DATA / "barcelos-semanal.json"
RECENT_FILE = DATA / "barcelos-nivel.json"


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def station():
    return {"id": STATION_ID, "label": STATION_LABEL, "name": "BARCELOS"}


def read_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_dt(value):
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def authenticate():
    identificador = os.getenv("ANA_IDENTIFICADOR")
    senha = os.getenv("ANA_SENHA")
    if not identificador or not senha:
        raise RuntimeError("Configure os secrets ANA_IDENTIFICADOR e ANA_SENHA no GitHub Actions.")
    response = requests.get(
        f"{API_BASE}/OAUth/v1",
        headers={"Identificador": identificador, "Senha": senha},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") or {}
    token = items.get("tokenautenticacao") or items.get("tokenAutenticacao") or items.get("token")
    if not token:
        raise RuntimeError("Token não encontrado na resposta da API.")
    return token


def fetch_last_30_days():
    token = authenticate()
    response = requests.get(
        f"{API_BASE}/HidroinfoanaSerieTelemetricaAdotada/v1",
        params={
            "CodigoDaEstacao": STATION_ID,
            "TipoFiltroData": "DATA_LEITURA",
            "DataDeBusca": date.today().isoformat(),
            "RangeIntervaloDeBusca": "DIAS_30",
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("items") if isinstance(payload, dict) else payload
    out = []
    for item in rows or []:
        dt = parse_dt(item.get("Data_Hora_Medicao"))
        level_cm = parse_float(item.get("Cota_Adotada"))
        if not dt or level_cm is None:
            continue
        out.append({
            "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "date": dt.date().isoformat(),
            "level_cm": round(level_cm, 2),
            "level_m": round(level_cm / 100, 3),
            "rain_mm": parse_float(item.get("Chuva_Adotada")),
            "flow_m3s": parse_float(item.get("Vazao_Adotada")),
            "level_status": item.get("Cota_Adotada_Status"),
            "source": "ana_api",
        })
    return sorted(out, key=lambda r: r["datetime"])


def daily_from_raw(raw):
    by_date = {}
    for row in raw:
        by_date.setdefault(row["date"], []).append(row)
    daily = []
    for day in sorted(by_date):
        rows = sorted(by_date[day], key=lambda r: r["datetime"])
        levels = [r["level_m"] for r in rows if r.get("level_m") is not None]
        if not levels:
            continue
        daily.append({
            "date": day,
            "level_avg_m": round(sum(levels) / len(levels), 3),
            "level_min_m": round(min(levels), 3),
            "level_max_m": round(max(levels), 3),
            "level_first_m": rows[0]["level_m"],
            "level_last_m": rows[-1]["level_m"],
            "samples": len(levels),
            "first_datetime": rows[0]["datetime"],
            "last_datetime": rows[-1]["datetime"],
            "source": "ana_api",
        })
    return daily


def merge_daily(existing, recent_raw):
    merged = {r["date"]: r for r in existing if r.get("date")}
    for row in daily_from_raw(recent_raw):
        merged[row["date"]] = row
    return [merged[k] for k in sorted(merged)]


def build_weekly(daily):
    buckets = {}
    for row in daily:
        d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if d.month < 6 or d.month > 10:
            continue
        week = ((d - date(d.year, 6, 1)).days // 7) + 1
        if week < 1 or week > 22:
            continue
        buckets.setdefault((d.year, week), []).append(row)
    weekly = []
    for (year, week), rows in sorted(buckets.items()):
        vals = [r["level_avg_m"] for r in rows]
        weekly.append({
            "year": year,
            "week": week,
            "period_start": rows[0]["date"],
            "period_end": rows[-1]["date"],
            "level_avg_m": round(sum(vals) / len(vals), 3),
            "level_min_m": round(min(vals), 3),
            "level_max_m": round(max(vals), 3),
            "days": len(vals),
        })
    return weekly


def build_current(daily, recent_raw):
    latest = recent_raw[-1] if recent_raw else (daily[-1] if daily else None)
    by_date = {r["date"]: r for r in daily}
    latest_daily = daily[-1] if daily else None
    last_1d = last_7d = None
    if latest_daily:
        d = datetime.strptime(latest_daily["date"], "%Y-%m-%d").date()
        last_1d = by_date.get((d - timedelta(days=1)).isoformat())
        last_7d = by_date.get((d - timedelta(days=7)).isoformat())
    level = latest.get("level_m") if latest else None
    return {
        "station": station(),
        "source": "ANA HidroWebService",
        "generated_at": now_iso(),
        "latest": latest,
        "daily_reference": latest_daily,
        "variation": {
            "last_24h_m": round(level - last_1d["level_avg_m"], 3) if level is not None and last_1d else None,
            "last_7d_m": round(level - last_7d["level_avg_m"], 3) if level is not None and last_7d else None,
        },
    }


def main():
    existing_daily = read_json(DAILY_FILE, {"daily": []}).get("daily", [])
    recent_raw = fetch_last_30_days()
    daily = merge_daily(existing_daily, recent_raw)
    generated_at = now_iso()
    base = {"station": station(), "source": "ANA HidroWebService", "generated_at": generated_at, "status": "ok"}
    write_json(DAILY_FILE, base | {"grain": "daily", "method": "Média diária das leituras disponíveis", "daily": daily})
    write_json(CURRENT_FILE, build_current(daily, recent_raw) | {"status": "ok"})
    write_json(WEEKLY_FILE, base | {"season": {"start_month": 6, "end_month": 10}, "weekly": build_weekly(daily)})
    write_json(RECENT_FILE, base | {"grain": "raw_recent", "records": recent_raw[-1500:]})
    print(f"Dias na base: {len(daily)} | leituras recentes: {len(recent_raw)}")


if __name__ == "__main__":
    main()
