import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

BASE_URL = os.getenv("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas").rstrip("/")
STATION_ID = os.getenv("ANA_STATION_ID", "14480002")
STATION_LABEL = os.getenv("ANA_STATION_LABEL", "5 - 14480002 - BARCELOS")
STATION_NAME = "BARCELOS"
SOURCE_NAME = "Histórico CSV + ANA HidroWebService"
TZ_OFFSET = timezone(timedelta(hours=-3))

RAW_JSON = DATA_DIR / "barcelos-nivel.json"
DAILY_JSON = DATA_DIR / "barcelos-diario.json"
CURRENT_JSON = DATA_DIR / "barcelos-atual.json"
WEEKLY_JSON = DATA_DIR / "barcelos-semanal.json"


def now_iso():
    return datetime.now(TZ_OFFSET).isoformat(timespec="seconds")


def read_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def station_meta():
    return {"id": STATION_ID, "label": STATION_LABEL, "name": STATION_NAME}


def parse_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # A API ANA retorna valores como "939.00" usando ponto decimal.
    # Alguns arquivos brasileiros podem vir com vírgula decimal. Tratamos ambos.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_datetime(value):
    if value is None:
        return None
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def get_token():
    identificador = os.getenv("ANA_IDENTIFICADOR")
    senha = os.getenv("ANA_SENHA")
    token_env = os.getenv("ANA_API_TOKEN")
    if token_env:
        return token_env
    if not identificador or not senha:
        raise RuntimeError("Configure ANA_IDENTIFICADOR e ANA_SENHA nos GitHub Actions Secrets.")

    response = requests.get(
        f"{BASE_URL}/OAUth/v1",
        headers={"Identificador": identificador, "Senha": senha},
        timeout=90,
    )
    print("Auth HTTP status:", response.status_code)
    response.raise_for_status()
    payload = response.json()
    token = (payload.get("items") or {}).get("tokenautenticacao") or (payload.get("items") or {}).get("token")
    if not token:
        raise RuntimeError("Token não encontrado na resposta da ANA.")
    return token


def normalize_items(items):
    records = []
    for item in items:
        dt = parse_datetime(item.get("Data_Hora_Medicao") or item.get("Data_Hora_Automatica") or item.get("Data_Hora"))
        cota_cm = parse_float(item.get("Cota_Adotada") or item.get("Cota_Sensor") or item.get("Cota_Automatica"))
        if dt is None or cota_cm is None:
            continue
        chuva = parse_float(item.get("Chuva_Adotada") or item.get("Chuva_Sensor") or item.get("Chuva_Acumulada"))
        vazao = parse_float(item.get("Vazao_Adotada"))
        records.append({
            "datetime": dt.isoformat(sep=" "),
            "date": dt.date().isoformat(),
            "level_cm": round(cota_cm, 2),
            "level_m": round(cota_cm / 100, 3),
            "rain_mm": None if chuva is None else round(chuva, 2),
            "flow_m3s": None if vazao is None else round(vazao, 2),
            "level_status": str(item.get("Cota_Adotada_Status", "")),
            "station_id": STATION_ID,
            "source": "api_ana",
        })
    records.sort(key=lambda row: row["datetime"])
    return records


def fetch_recent_raw():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    url = f"{BASE_URL}/HidroinfoanaSerieTelemetricaDetalhada/v1"

    candidates = []
    today = date.today()
    for days_back in range(0, 8):
        day = today - timedelta(days=days_back)
        for range_value in ("DIAS_14", "HORA_24", "HORA_1"):
            candidates.append((day.isoformat(), range_value))

    last_payload_items = []
    for data_busca, range_value in candidates:
        params = {
            "Código da Estação": STATION_ID,
            "Tipo Filtro Data": "DATA_LEITURA",
            "Data de Busca (yyyy-MM-dd)": data_busca,
            "Range Intervalo de busca": range_value,
        }
        response = requests.get(url, params=params, headers=headers, timeout=90)
        print(f"Data HTTP status: {response.status_code} | Data de Busca: {data_busca} | Range: {range_value}")
        print("Data final URL:", response.url)
        response.raise_for_status()

        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("items") or []
        print("Items retornados:", len(items))
        last_payload_items = items
        records = normalize_items(items)
        print("Registros normalizados:", len(records))
        if records:
            return records

    if last_payload_items:
        print("A API retornou items, mas nenhum campo de cota/data foi normalizado.")
        print("Campos do primeiro item:", sorted(last_payload_items[0].keys()))
    return []


def aggregate_daily(raw_records):
    if not raw_records:
        return []
    df = pd.DataFrame(raw_records)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.date.astype(str)
    df["level_m"] = pd.to_numeric(df["level_m"], errors="coerce")
    df["level_cm"] = pd.to_numeric(df["level_cm"], errors="coerce")
    df = df.dropna(subset=["level_m", "level_cm"])

    output = []
    for day, group in df.groupby("date", sort=True):
        group = group.sort_values("datetime")
        first = group.iloc[0]
        last = group.iloc[-1]
        output.append({
            "date": day,
            "level_avg_m": round(float(group["level_m"].mean()), 3),
            "level_min_m": round(float(group["level_m"].min()), 3),
            "level_max_m": round(float(group["level_m"].max()), 3),
            "level_first_m": round(float(first["level_m"]), 3),
            "level_last_m": round(float(last["level_m"]), 3),
            "level_avg_cm": round(float(group["level_cm"].mean()), 2),
            "samples": int(len(group)),
            "first_datetime": first["datetime"].isoformat(sep=" "),
            "last_datetime": last["datetime"].isoformat(sep=" "),
            "source": "+".join(sorted(set(str(x) for x in group["source"].dropna()))),
        })
    return output


def merge_daily(existing, new):
    merged = {row["date"]: row for row in existing if row.get("date")}
    for row in new:
        merged[row["date"]] = row
    return [merged[key] for key in sorted(merged)]


def build_current(daily):
    if not daily:
        return None
    latest = daily[-1]
    previous = daily[-2] if len(daily) >= 2 else None
    week_ref = daily[-8] if len(daily) >= 8 else None

    def delta(ref):
        if not ref:
            return None
        return round(latest["level_last_m"] - ref["level_last_m"], 3)

    d1 = delta(previous)
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


def build_weekly(daily):
    df = pd.DataFrame(daily)
    if df.empty:
        return []
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].dt.month.between(6, 10)].copy()
    if df.empty:
        return []
    df["year"] = df["date"].dt.year
    df["season_start"] = pd.to_datetime(df["year"].astype(str) + "-06-01")
    df["week"] = ((df["date"] - df["season_start"]).dt.days // 7) + 1
    df = df[(df["week"] >= 1) & (df["week"] <= 22)]
    grouped = df.groupby(["year", "week"], as_index=False).agg(
        level_avg_m=("level_avg_m", "mean"),
        level_min_m=("level_min_m", "min"),
        level_max_m=("level_max_m", "max"),
        days=("date", "count"),
        samples=("samples", "sum"),
    )

    output = []
    for _, row in grouped.sort_values(["year", "week"]).iterrows():
        year = int(row["year"])
        week = int(row["week"])
        start = date(year, 6, 1) + timedelta(days=(week - 1) * 7)
        end = min(start + timedelta(days=6), date(year, 10, 31))
        output.append({
            "year": year,
            "week": week,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "level_avg_m": round(float(row["level_avg_m"]), 3),
            "level_min_m": round(float(row["level_min_m"]), 3),
            "level_max_m": round(float(row["level_max_m"]), 3),
            "days": int(row["days"]),
            "samples": int(row["samples"]),
        })
    return output


def main():
    raw = fetch_recent_raw()
    if not raw:
        raise SystemExit("Nenhum registro de cota foi encontrado nos últimos 8 dias testados.")

    existing_daily = read_json(DAILY_JSON, {"records": []}).get("records", [])
    daily = merge_daily(existing_daily, aggregate_daily(raw))
    generated_at = now_iso()

    write_json(RAW_JSON, {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": "ok",
        "note": "Arquivo operacional com amostra recente. A base principal do projeto é diária.",
        "latest": raw[-1],
        "records": raw[-500:],
    })

    write_json(DAILY_JSON, {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": "ok",
        "aggregation": "1 registro por dia; nível principal = média diária das leituras disponíveis",
        "records": daily,
    })

    write_json(CURRENT_JSON, build_current(daily))
    write_json(WEEKLY_JSON, {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": "ok",
        "season": {
            "start_month": 6,
            "end_month": 10,
            "week_1_rule": "Semana 1 começa em 01/06 de cada ano",
            "base": "média semanal calculada a partir da média diária",
        },
        "weekly": build_weekly(daily),
    })
    print(f"Coleta OK: {len(raw)} leituras brutas; {len(daily)} dias na base diária.")


if __name__ == "__main__":
    main()
