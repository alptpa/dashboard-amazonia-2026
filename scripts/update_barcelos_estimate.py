import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

BASE_URL = os.getenv("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas").rstrip("/")
TZ_OFFSET = timezone(timedelta(hours=-3))

BARCELOS_ID = "14480002"
BARCELOS_LABEL = "5 - 14480002 - BARCELOS"
SERRINHA_ID = "14420000"
SERRINHA_LABEL = "SERRINHA - 14420000"
MOURA_ID = "14840000"
MOURA_LABEL = "MOURA - 14840000"

BARCELOS_DAILY_JSON = DATA_DIR / "barcelos-diario.json"
SERRINHA_DAILY_JSON = DATA_DIR / "serrinha-diario.json"
MOURA_DAILY_JSON = DATA_DIR / "moura-diario.json"
ESTIMATED_JSON = DATA_DIR / "barcelos-estimado.json"

SOURCE_NAME = "Estimativa baseada nas estações Serrinha (14420000) e Moura (14840000)"


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


def parse_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
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
    token_env = os.getenv("ANA_API_TOKEN")
    if token_env:
        return token_env

    identificador = os.getenv("ANA_IDENTIFICADOR")
    senha = os.getenv("ANA_SENHA")
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


def normalize_items(items, station_id):
    records = []
    for item in items:
        dt = parse_datetime(item.get("Data_Hora_Medicao") or item.get("Data_Hora_Automatica") or item.get("Data_Hora"))
        cota_cm = parse_float(item.get("Cota_Adotada") or item.get("Cota_Sensor") or item.get("Cota_Automatica"))
        if dt is None or cota_cm is None:
            continue
        records.append({
            "datetime": dt.isoformat(sep=" "),
            "date": dt.date().isoformat(),
            "level_cm": round(cota_cm, 2),
            "level_m": round(cota_cm / 100, 3),
            "level_status": str(item.get("Cota_Adotada_Status", "")),
            "station_id": station_id,
            "source": "api_ana",
        })
    records.sort(key=lambda row: row["datetime"])
    return records


def fetch_station_raw(token, station_id, label, days_back=35):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{BASE_URL}/HidroinfoanaSerieTelemetricaDetalhada/v1"
    collected = {}
    today = date.today()

    for offset in range(0, days_back + 1):
        day = today - timedelta(days=offset)
        for range_value in ("HORA_24", "HORA_1"):
            params = {
                "Código da Estação": station_id,
                "Tipo Filtro Data": "DATA_LEITURA",
                "Data de Busca (yyyy-MM-dd)": day.isoformat(),
                "Range Intervalo de busca": range_value,
            }
            try:
                response = requests.get(url, params=params, headers=headers, timeout=90)
                print(f"{label} | HTTP {response.status_code} | {day.isoformat()} | {range_value}")
                response.raise_for_status()
                payload = response.json()
                items = payload if isinstance(payload, list) else payload.get("items") or []
                records = normalize_items(items, station_id)
                print(f"{label} | itens: {len(items)} | normalizados: {len(records)}")
                for record in records:
                    collected[record["datetime"]] = record
            except Exception as exc:
                print(f"Aviso: falha ao consultar {label} em {day.isoformat()} {range_value}: {exc}")

    return [collected[key] for key in sorted(collected)]


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
            "source": "api_ana",
        })
    return output


def station_payload(station_id, label, records, generated_at):
    return {
        "station": {"id": station_id, "label": label},
        "source": "ANA HidroWebService",
        "generated_at": generated_at,
        "status": "ok" if records else "sem_dados",
        "aggregation": "1 registro por dia; nível principal = média diária das leituras disponíveis",
        "records": records,
    }


def fit_model(barcelos_daily, serrinha_daily, moura_daily):
    b = {row["date"]: row for row in barcelos_daily if row.get("date")}
    s = {row["date"]: row for row in serrinha_daily if row.get("date")}
    m = {row["date"]: row for row in moura_daily if row.get("date")}
    overlap_dates = sorted(set(b) & set(s) & set(m))

    if len(overlap_dates) >= 5:
        x = np.array([[s[d]["level_avg_m"], m[d]["level_avg_m"], 1.0] for d in overlap_dates], dtype=float)
        y = np.array([b[d]["level_avg_m"] for d in overlap_dates], dtype=float)
        coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
        predicted = x @ coefficients
        mae = float(np.mean(np.abs(predicted - y)))
        confidence = "alta" if mae <= 0.10 else "média" if mae <= 0.25 else "baixa"
        return {
            "kind": "linear_regression",
            "coefficients": {
                "serrinha_weight": round(float(coefficients[0]), 6),
                "moura_weight": round(float(coefficients[1]), 6),
                "intercept": round(float(coefficients[2]), 6),
            },
            "overlap_days": len(overlap_dates),
            "mean_absolute_error_m": round(mae, 3),
            "confidence": confidence,
        }

    if len(overlap_dates) >= 2:
        offsets = [b[d]["level_avg_m"] - ((s[d]["level_avg_m"] + m[d]["level_avg_m"]) / 2) for d in overlap_dates]
        offset = float(np.mean(offsets))
        mae = float(np.mean(np.abs(offsets - offset))) if len(offsets) > 1 else None
        return {
            "kind": "average_with_offset",
            "offset_m": round(offset, 3),
            "overlap_days": len(overlap_dates),
            "mean_absolute_error_m": None if mae is None else round(mae, 3),
            "confidence": "baixa",
        }

    return {
        "kind": "simple_average_no_calibration",
        "overlap_days": len(overlap_dates),
        "mean_absolute_error_m": None,
        "confidence": "baixa",
    }


def estimate_level(model, serrinha_value, moura_value):
    if model["kind"] == "linear_regression":
        c = model["coefficients"]
        return (
            c["serrinha_weight"] * serrinha_value
            + c["moura_weight"] * moura_value
            + c["intercept"]
        )
    if model["kind"] == "average_with_offset":
        return ((serrinha_value + moura_value) / 2) + model["offset_m"]
    return (serrinha_value + moura_value) / 2


def build_estimated(barcelos_daily, serrinha_daily, moura_daily, generated_at):
    s = {row["date"]: row for row in serrinha_daily if row.get("date")}
    m = {row["date"]: row for row in moura_daily if row.get("date")}
    common_dates = sorted(set(s) & set(m))
    model = fit_model(barcelos_daily, serrinha_daily, moura_daily)

    records = []
    for day in common_dates[-14:]:
        serrinha_value = float(s[day]["level_avg_m"])
        moura_value = float(m[day]["level_avg_m"])
        estimated = estimate_level(model, serrinha_value, moura_value)
        records.append({
            "date": day,
            "level_estimated_m": round(float(estimated), 3),
            "serrinha_level_m": round(serrinha_value, 3),
            "moura_level_m": round(moura_value, 3),
            "serrinha_samples": s[day].get("samples"),
            "moura_samples": m[day].get("samples"),
            "source": "estimated_from_serrinha_moura",
        })

    latest = records[-1] if records else None
    previous = records[-2] if len(records) >= 2 else None
    first = records[0] if records else None

    d1 = round(latest["level_estimated_m"] - previous["level_estimated_m"], 3) if latest and previous else None
    d7 = round(latest["level_estimated_m"] - first["level_estimated_m"], 3) if latest and first else None
    trend = "estável"
    if d1 is not None and d1 > 0:
        trend = "subindo"
    elif d1 is not None and d1 < 0:
        trend = "secando"

    return {
        "station": {
            "id": BARCELOS_ID,
            "label": "BARCELOS estimado",
            "name": "BARCELOS",
        },
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": "ok" if records else "sem_dados",
        "official_warning": "Estimativa operacional. Não substitui a medição oficial da estação Barcelos 14480002.",
        "method": {
            "upstream_station": {"id": SERRINHA_ID, "label": SERRINHA_LABEL},
            "downstream_station": {"id": MOURA_ID, "label": MOURA_LABEL},
            "model": model,
        },
        "latest": latest,
        "variation": {
            "last_24h_m": d1,
            "last_7d_m": d7,
            "trend": trend,
            "trend_basis": "estimated_daily_change",
        },
        "records": records,
    }


def main():
    generated_at = now_iso()
    token = get_token()

    serrinha_raw = fetch_station_raw(token, SERRINHA_ID, SERRINHA_LABEL)
    moura_raw = fetch_station_raw(token, MOURA_ID, MOURA_LABEL)

    serrinha_daily = aggregate_daily(serrinha_raw)
    moura_daily = aggregate_daily(moura_raw)
    barcelos_daily = read_json(BARCELOS_DAILY_JSON, {"records": []}).get("records", [])

    write_json(SERRINHA_DAILY_JSON, station_payload(SERRINHA_ID, SERRINHA_LABEL, serrinha_daily, generated_at))
    write_json(MOURA_DAILY_JSON, station_payload(MOURA_ID, MOURA_LABEL, moura_daily, generated_at))
    write_json(ESTIMATED_JSON, build_estimated(barcelos_daily, serrinha_daily, moura_daily, generated_at))

    print(f"Serrinha: {len(serrinha_raw)} leituras brutas; {len(serrinha_daily)} dias.")
    print(f"Moura: {len(moura_raw)} leituras brutas; {len(moura_daily)} dias.")
    print("Estimativa de Barcelos gerada em data/barcelos-estimado.json.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Aviso: estimativa de Barcelos não foi atualizada: {exc}")
        raise SystemExit(0)
