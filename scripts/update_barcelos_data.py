import json
import os
import re
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

STATION_ID = os.getenv("ANA_STATION_ID", "14480002")
STATION_LABEL = os.getenv("ANA_STATION_LABEL", "5 - 14480002 - BARCELOS")
STATION_NAME = "BARCELOS"
SOURCE_NAME = "ANA HidroWebService / SNIRH"
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


def parse_number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "nan"}:
        return None
    text = text.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def normalize_datetime(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    for fmt in (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def station_meta():
    return {"id": STATION_ID, "label": STATION_LABEL, "name": STATION_NAME}


def normalize_api_item(item):
    dt = normalize_datetime(
        item.get("Data_Hora_Medicao")
        or item.get("dataHora")
        or item.get("DataHora")
        or item.get("data_hora")
    )
    level_cm = parse_number(
        item.get("Cota_Adotada")
        or item.get("NivelAdotado")
        or item.get("nivelAdotado")
        or item.get("nivel")
    )
    if dt is None or level_cm is None:
        return None

    rain_mm = parse_number(item.get("Chuva_Adotada") or item.get("chuva"))
    flow_m3s = parse_number(item.get("Vazao_Adotada") or item.get("vazao"))

    return {
        "datetime": dt.isoformat(sep=" "),
        "date": dt.date().isoformat(),
        "level_cm": round(level_cm, 2),
        "level_m": round(level_cm / 100, 3),
        "rain_mm": None if rain_mm is None else round(rain_mm, 2),
        "flow_m3s": None if flow_m3s is None else round(flow_m3s, 2),
        "level_status": str(item.get("Cota_Adotada_Status", "")),
        "station_id": str(item.get("codigoestacao", STATION_ID)),
        "source": "api",
    }


def normalize_table(df):
    columns = {str(c).strip().lower(): c for c in df.columns}
    dt_col = None
    level_col = None

    for key, original in columns.items():
        if "data" in key and "hora" in key:
            dt_col = original
        if "nível adotado" in key or "nivel adotado" in key or "cota" in key:
            level_col = original

    if dt_col is None or level_col is None:
        return []

    records = []
    for _, row in df.iterrows():
        dt = normalize_datetime(row.get(dt_col))
        level_cm = parse_number(row.get(level_col))
        if dt is None or level_cm is None:
            continue
        records.append({
            "datetime": dt.isoformat(sep=" "),
            "date": dt.date().isoformat(),
            "level_cm": round(level_cm, 2),
            "level_m": round(level_cm / 100, 3),
            "rain_mm": None,
            "flow_m3s": None,
            "level_status": "",
            "station_id": STATION_ID,
            "source": "snirh_page",
        })

    records.sort(key=lambda item: item["datetime"])
    return records


def get_ana_token():
    identificador = os.getenv("ANA_IDENTIFICADOR")
    senha = os.getenv("ANA_SENHA")
    base_url = os.getenv("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas")

    if not identificador or not senha:
        return None

    response = requests.get(
        f"{base_url}/OAUth/v1",
        headers={"Identificador": identificador, "Senha": senha},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    token = (payload.get("items") or {}).get("tokenautenticacao")
    if not token:
        raise RuntimeError("Token não encontrado na resposta da ANA")
    return token


def fetch_from_official_api():
    token = os.getenv("ANA_API_TOKEN") or get_ana_token()
    if not token:
        return []

    base_url = os.getenv("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas")
    end = date.today()
    start = end - timedelta(days=30)

    headers = {"Authorization": f"Bearer {token}"}
    all_records = []

    # A rota HidroinfoanaSerieTelemetricaAdotada aceita janela limitada.
    # Buscamos os últimos 30 dias e depois consolidamos para 1 registro por dia.
    current = start
    while current <= end:
        params = {
            "CodigoDaEstacao": STATION_ID,
            "TipoFiltroData": "DATA_LEITURA",
            "DataDeBusca": current.isoformat(),
            "RangeIntervaloDeBusca": "DIAS_30",
        }
        response = requests.get(
            f"{base_url}/HidroinfoanaSerieTelemetricaAdotada/v1",
            params=params,
            headers=headers,
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("items") or []
        for item in items:
            record = normalize_api_item(item)
            if record:
                all_records.append(record)
        break

    return sorted(deduplicate_raw(all_records), key=lambda item: item["datetime"])


def fetch_from_snirh_page():
    from playwright.sync_api import sync_playwright

    url = "https://snirh.gov.br/hidrotelemetria/serieHistorica.aspx"
    today = date.today()
    start = today - timedelta(days=30)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=120000)

        station_regex = re.compile(r"14480002|BARCELOS", re.I)
        for select in page.locator("select").all():
            try:
                for option in select.locator("option").all():
                    label = option.inner_text(timeout=1000)
                    if station_regex.search(label):
                        value = option.get_attribute("value")
                        if value:
                            select.select_option(value=value)
                            page.wait_for_timeout(500)
                        break
            except Exception:
                pass

        date_values = [start.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")]
        date_index = 0
        for inp in page.locator("input").all():
            try:
                typ = (inp.get_attribute("type") or "text").lower()
                value = inp.input_value(timeout=1000)
                if typ in ("text", "date") and re.search(r"\d{2}/\d{2}/\d{4}|^$", value or "") and date_index < 2:
                    inp.fill(date_values[date_index])
                    date_index += 1
            except Exception:
                pass

        for selector in ["input[type=image]", "input[type=submit]", "button"]:
            try:
                for button in page.locator(selector).all():
                    title = (button.get_attribute("title") or button.get_attribute("alt") or button.inner_text(timeout=1000) or "")
                    if re.search(r"consult|pesquis|visual|atual|ok|confirm", title, re.I):
                        button.click(timeout=3000)
                        page.wait_for_load_state("networkidle", timeout=60000)
                        break
            except Exception:
                pass

        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()

    tables = pd.read_html(html)
    for df in tables:
        records = normalize_table(df)
        if records:
            return records
    return []


def deduplicate_raw(records):
    by_key = {}
    for record in records:
        key = f"{record.get('station_id', STATION_ID)}|{record['datetime']}"
        by_key[key] = record
    return list(by_key.values())


def aggregate_daily(raw_records):
    if not raw_records:
        return []

    df = pd.DataFrame(raw_records)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.date.astype(str)
    df["level_m"] = pd.to_numeric(df["level_m"], errors="coerce")
    df["level_cm"] = pd.to_numeric(df["level_cm"], errors="coerce")
    df = df.dropna(subset=["level_m", "level_cm"])

    result = []
    for day, group in df.groupby("date", sort=True):
        group = group.sort_values("datetime")
        first = group.iloc[0]
        last = group.iloc[-1]
        result.append({
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
            "source": "+".join(sorted(set(str(x) for x in group.get("source", pd.Series(["unknown"])).dropna()))),
        })
    return result


def merge_daily(existing_daily, new_daily):
    by_date = {item["date"]: item for item in existing_daily if item.get("date")}
    for item in new_daily:
        by_date[item["date"]] = item
    return [by_date[key] for key in sorted(by_date.keys())]


def build_current(daily_records):
    if not daily_records:
        return None
    latest = daily_records[-1]
    previous = daily_records[-2] if len(daily_records) >= 2 else None
    week_ref = daily_records[-8] if len(daily_records) >= 8 else None

    def delta(ref):
        if not ref:
            return None
        return round(latest["level_last_m"] - ref["level_last_m"], 3)

    trend = "estável"
    d7 = delta(week_ref)
    if d7 is not None:
        if d7 > 0.05:
            trend = "subindo"
        elif d7 < -0.05:
            trend = "baixando"

    return {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": now_iso(),
        "latest": latest,
        "variation": {
            "last_24h_m": delta(previous),
            "last_7d_m": d7,
            "trend": trend,
        },
    }


def build_weekly(daily_records):
    df = pd.DataFrame(daily_records)
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

    grouped = (
        df.groupby(["year", "week"], as_index=False)
        .agg(
            level_avg_m=("level_avg_m", "mean"),
            level_min_m=("level_min_m", "min"),
            level_max_m=("level_max_m", "max"),
            days=("date", "count"),
            samples=("samples", "sum"),
        )
        .sort_values(["year", "week"])
    )

    result = []
    for _, row in grouped.iterrows():
        year = int(row["year"])
        week = int(row["week"])
        start = date(year, 6, 1) + timedelta(days=(week - 1) * 7)
        end = min(start + timedelta(days=6), date(year, 10, 31))
        result.append({
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
    return result


def save_outputs(existing_daily, fetched_raw, status="ok"):
    generated_at = now_iso()
    new_daily = aggregate_daily(fetched_raw)
    daily = merge_daily(existing_daily, new_daily)
    latest_raw = sorted(fetched_raw, key=lambda item: item["datetime"])[-1] if fetched_raw else None

    raw_payload = {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": status,
        "note": "Arquivo operacional com amostra recente. A base principal do projeto é diária.",
        "latest": latest_raw,
        "records": fetched_raw[-500:],
    }

    daily_payload = {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": status,
        "aggregation": "1 registro por dia; nível principal = média diária das leituras disponíveis",
        "records": daily,
    }

    current_payload = build_current(daily) or {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": "empty",
        "latest": None,
        "variation": {},
    }

    weekly_payload = {
        "station": station_meta(),
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": status,
        "season": {
            "start_month": 6,
            "end_month": 10,
            "week_1_rule": "Semana 1 começa em 01/06 de cada ano",
            "base": "média semanal calculada a partir da média diária",
        },
        "weekly": build_weekly(daily),
    }

    write_json(RAW_JSON, raw_payload)
    write_json(DAILY_JSON, daily_payload)
    write_json(CURRENT_JSON, current_payload)
    write_json(WEEKLY_JSON, weekly_payload)
    return daily


def main():
    existing_daily_payload = read_json(DAILY_JSON, {"records": []})
    existing_daily = existing_daily_payload.get("records", [])
    errors = []
    fetched_raw = []

    try:
        fetched_raw = fetch_from_official_api()
    except Exception as exc:
        errors.append(f"official_api: {exc}")

    if not fetched_raw:
        try:
            fetched_raw = fetch_from_snirh_page()
        except Exception as exc:
            errors.append(f"snirh_page: {exc}")

    if not fetched_raw:
        if existing_daily:
            print("Nenhum dado novo coletado; histórico diário existente preservado.")
            raise SystemExit(0)
        raise SystemExit("Não foi possível coletar dados e não há base diária existente. " + " | ".join(errors))

    daily = save_outputs(existing_daily, deduplicate_raw(fetched_raw), status="ok")
    print(f"Coleta concluída: {len(fetched_raw)} leituras brutas; {len(daily)} dias consolidados.")


if __name__ == "__main__":
    main()
