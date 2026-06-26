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
SOURCE_NAME = "SNIRH / ANA - Sistema HIDRO Telemetria"
TZ_OFFSET = timezone(timedelta(hours=-3))

RAW_JSON = DATA_DIR / "barcelos-nivel.json"
WEEKLY_JSON = DATA_DIR / "barcelos-semanal.json"


def now_iso():
    return datetime.now(TZ_OFFSET).isoformat(timespec="seconds")


def parse_level(value):
    if value is None:
        return None
    text = str(value).strip().replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def normalize_datetime(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def normalize_table(df):
    columns = {str(c).strip().lower(): c for c in df.columns}
    dt_col = None
    level_col = None

    for key, original in columns.items():
        if "data" in key and "hora" in key:
            dt_col = original
        if "nível adotado" in key or "nivel adotado" in key:
            level_col = original

    if dt_col is None or level_col is None:
        return []

    records = []
    for _, row in df.iterrows():
        dt = normalize_datetime(row.get(dt_col))
        level_cm = parse_level(row.get(level_col))
        if dt is None or level_cm is None:
            continue
        records.append({
            "datetime": dt.isoformat(sep=" "),
            "date": dt.date().isoformat(),
            "level_cm": round(level_cm, 2),
            "level_m": round(level_cm / 100, 3),
        })

    records.sort(key=lambda item: item["datetime"])
    return records


def try_fetch_from_official_api():
    """Tenta usar API oficial quando token/endpoint forem configurados.

    Configure secrets no GitHub, se a ANA liberar:
    - ANA_API_URL
    - ANA_API_TOKEN
    """
    api_url = os.getenv("ANA_API_URL")
    token = os.getenv("ANA_API_TOKEN")
    if not api_url:
        return []

    end = date.today()
    start = end - timedelta(days=220)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "codEstacao": STATION_ID,
        "dataInicio": start.isoformat(),
        "dataFim": end.isoformat(),
    }

    response = requests.get(api_url, params=params, headers=headers, timeout=60)
    response.raise_for_status()
    payload = response.json()

    rows = payload if isinstance(payload, list) else payload.get("items") or payload.get("dados") or []
    records = []
    for item in rows:
        dt = normalize_datetime(item.get("dataHora") or item.get("DataHora") or item.get("data_hora"))
        level_cm = parse_level(item.get("nivelAdotado") or item.get("NivelAdotado") or item.get("nivel_adotado") or item.get("nivel"))
        if dt is None or level_cm is None:
            continue
        records.append({
            "datetime": dt.isoformat(sep=" "),
            "date": dt.date().isoformat(),
            "level_cm": round(level_cm, 2),
            "level_m": round(level_cm / 100, 3),
        })
    records.sort(key=lambda item: item["datetime"])
    return records


def fetch_from_snirh_page():
    """Coleta a tabela pública da tela Sistema HIDRO - Telemetria.

    A tela é ASP.NET/WebForms. Por isso usamos Playwright para renderizar a página e
    depois pandas.read_html para localizar a tabela que contém Data/Hora e Nível adotado.
    """
    from playwright.sync_api import sync_playwright

    url = "https://snirh.gov.br/hidrotelemetria/serieHistorica.aspx"
    today = date.today()
    start = today - timedelta(days=220)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=120000)

        # Tenta escolher a estação em selects/listboxes, quando a página permitir.
        station_regex = re.compile(r"14480002|BARCELOS", re.I)
        for select in page.locator("select").all():
            try:
                options = select.locator("option").all()
                for option in options:
                    label = option.inner_text(timeout=1000)
                    if station_regex.search(label):
                        value = option.get_attribute("value")
                        if value:
                            select.select_option(value=value)
                            page.wait_for_timeout(500)
                        break
            except Exception:
                pass

        # Preenche campos de data quando encontrados.
        inputs = page.locator("input").all()
        date_values = [start.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")]
        date_index = 0
        for inp in inputs:
            try:
                typ = (inp.get_attribute("type") or "text").lower()
                value = inp.input_value(timeout=1000)
                if typ in ("text", "date") and re.search(r"\d{2}/\d{2}/\d{4}|^$", value or "") and date_index < 2:
                    inp.fill(date_values[date_index])
                    date_index += 1
            except Exception:
                pass

        # Tenta acionar botões de atualização/consulta.
        for selector in ["input[type=image]", "input[type=submit]", "button"]:
            try:
                buttons = page.locator(selector).all()
                for button in buttons:
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


def build_weekly(records):
    df = pd.DataFrame(records)
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
        .agg(level_m=("level_m", "mean"), samples=("level_m", "count"))
        .sort_values(["year", "week"])
    )

    result = []
    for _, row in grouped.iterrows():
        result.append({
            "year": int(row["year"]),
            "week": int(row["week"]),
            "level_m": round(float(row["level_m"]), 3),
            "samples": int(row["samples"]),
        })
    return result


def write_outputs(records, status="ok"):
    generated_at = now_iso()
    latest = records[-1] if records else None

    raw_payload = {
        "station": {"id": STATION_ID, "label": STATION_LABEL, "name": STATION_NAME},
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": status,
        "latest": latest,
        "records": records[-1500:],
    }

    weekly_payload = {
        "station": {"id": STATION_ID, "label": STATION_LABEL, "name": STATION_NAME},
        "source": SOURCE_NAME,
        "generated_at": generated_at,
        "status": status,
        "season": {
            "start_month": 6,
            "end_month": 10,
            "week_1_rule": "Semana 1 começa em 01/06 de cada ano",
        },
        "weekly": build_weekly(records),
    }

    RAW_JSON.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    WEEKLY_JSON.write_text(json.dumps(weekly_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    records = []
    errors = []

    try:
        records = try_fetch_from_official_api()
    except Exception as exc:
        errors.append(f"official_api: {exc}")

    if not records:
        try:
            records = fetch_from_snirh_page()
        except Exception as exc:
            errors.append(f"snirh_page: {exc}")

    if not records:
        write_outputs([], status="error: " + " | ".join(errors))
        raise SystemExit("Não foi possível coletar dados. " + " | ".join(errors))

    write_outputs(records, status="ok")
    print(f"Coleta concluída: {len(records)} registros. Último: {records[-1]}")


if __name__ == "__main__":
    main()
