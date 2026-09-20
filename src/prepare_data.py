from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

SOURCE_COLUMNS = [
    "Número",
    "Aberto",
    "Categoria",
    "Subcategoria",
    "Prioridade",
    "Grupo designado",
    "Item de configuração",
]

RENAME = {
    "Número": "incident_id",
    "Aberto": "opened_at",
    "Categoria": "category",
    "Subcategoria": "subcategory",
    "Prioridade": "priority",
    "Grupo designado": "assigned_group",
    "Item de configuração": "configuration_item",
}


def _summary_table(series: pd.Series, name: str) -> pd.DataFrame:
    clean = series.astype("string").fillna("Não informado").str.strip().replace("", "Não informado")
    out = clean.value_counts(dropna=False).rename_axis(name).reset_index(name="incident_count")
    out["share"] = out["incident_count"] / out["incident_count"].sum()
    return out


def prepare_dataset(config_path: str | Path = "config/project.yaml") -> dict:
    config_path = Path(config_path).resolve()
    root = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_path = root / config["source"]["raw_file"]
    processed = root / "data/processed"
    evidence = root / "evidence"
    processed.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    raw = pd.read_excel(
        raw_path,
        sheet_name=config["source"]["sheet_name"],
        usecols=SOURCE_COLUMNS,
        engine="openpyxl",
    )
    raw = raw.rename(columns=RENAME)
    raw["opened_at"] = pd.to_datetime(raw["opened_at"], errors="coerce")

    raw_rows = len(raw)
    invalid_rows = int((raw["incident_id"].isna() | raw["opened_at"].isna()).sum())
    valid = raw.dropna(subset=["incident_id", "opened_at"]).copy()
    duplicate_ids = int(valid["incident_id"].duplicated().sum())
    valid = valid.sort_values("opened_at").drop_duplicates("incident_id", keep="first")

    start = pd.Timestamp(config["analysis_window"]["start_date"])
    end = pd.Timestamp(config["analysis_window"]["end_date"])
    if start > end:
        raise ValueError("A data inicial da janela deve ser anterior à data final.")
    selected = valid[
        (valid["opened_at"] >= start) & (valid["opened_at"] < end + pd.Timedelta(days=1))
    ].copy()
    if selected.empty:
        raise ValueError("A janela configurada não contém incidentes válidos.")
    selected = selected.sort_values(["opened_at", "incident_id"])

    for column in ["category", "subcategory", "assigned_group", "configuration_item"]:
        selected[column] = (
            selected[column]
            .astype("string")
            .fillna("Não informado")
            .str.strip()
            .replace("", "Não informado")
        )
    selected["priority"] = pd.to_numeric(
        selected["priority"].astype("string").str.extract(r"^\s*(\d+)", expand=False),
        errors="coerce",
    ).astype("Int64")
    selected["opened_date"] = selected["opened_at"].dt.floor("D")

    minimal_columns = [
        "incident_id",
        "opened_at",
        "opened_date",
        "category",
        "subcategory",
        "priority",
        "assigned_group",
        "configuration_item",
    ]
    minimal = selected[minimal_columns].copy()
    minimal.to_csv(
        processed / "incidents_minimal.csv", index=False, date_format="%Y-%m-%d %H:%M:%S"
    )

    calendar = pd.date_range(start, end, freq="D")
    daily = (
        minimal.groupby("opened_date")["incident_id"]
        .nunique()
        .reindex(calendar, fill_value=0)
        .rename("incident_count")
        .rename_axis("date")
        .reset_index()
    )
    daily["incident_count"] = daily["incident_count"].astype(int)
    daily.to_csv(processed / "incident_count_daily.csv", index=False, date_format="%Y-%m-%d")

    _summary_table(minimal["category"], "category").to_csv(
        processed / "category_summary.csv", index=False
    )
    _summary_table(minimal["priority"], "priority").to_csv(
        processed / "priority_summary.csv", index=False
    )
    _summary_table(minimal["assigned_group"], "assigned_group").to_csv(
        processed / "assignment_group_summary.csv", index=False
    )

    weekday = daily.assign(
        weekday_number=daily["date"].dt.dayofweek,
        weekday=daily["date"].dt.day_name(),
    )
    weekday_summary = (
        weekday.groupby(["weekday_number", "weekday"])["incident_count"]
        .agg(days="count", mean="mean", median="median", minimum="min", maximum="max")
        .reset_index()
        .sort_values("weekday_number")
    )
    weekday_summary.to_csv(processed / "weekday_summary.csv", index=False)

    hourly_summary = (
        minimal.assign(hour=minimal["opened_at"].dt.hour)
        .groupby("hour")["incident_id"]
        .nunique()
        .reindex(range(24), fill_value=0)
        .rename("incident_count")
        .rename_axis("hour")
        .reset_index()
    )
    hourly_summary["share"] = (
        hourly_summary["incident_count"] / hourly_summary["incident_count"].sum()
    )
    hourly_summary.to_csv(processed / "hourly_summary.csv", index=False)

    weekend = minimal["opened_at"].dt.dayofweek >= 5
    outside_08_18 = (minimal["opened_at"].dt.hour < 8) | (minimal["opened_at"].dt.hour >= 18)

    missing = {
        col: int(
            (
                minimal[col].isna()
                | minimal[col].astype(str).str.strip().isin(["", "Não informado"])
            ).sum()
        )
        for col in ["category", "subcategory", "priority", "assigned_group", "configuration_item"]
    }
    report = {
        "dataset": config["source"]["name"],
        "source_file": config["source"]["raw_file"],
        "source_sheet": config["source"]["sheet_name"],
        "source_rows": raw_rows,
        "invalid_or_empty_rows_removed": invalid_rows,
        "duplicate_incident_ids_removed": duplicate_ids,
        "valid_unique_incidents_full_source": int(len(valid)),
        "full_source_start": valid["opened_at"].min().date().isoformat(),
        "full_source_end": valid["opened_at"].max().date().isoformat(),
        "valid_source_rows_excluded_from_analysis_window": int(len(valid) - len(selected)),
        "analysis_window_start": start.date().isoformat(),
        "analysis_window_end": end.date().isoformat(),
        "analysis_incidents": int(len(minimal)),
        "analysis_days": int(len(daily)),
        "days_without_incidents": int((daily["incident_count"] == 0).sum()),
        "daily_mean": round(float(daily["incident_count"].mean()), 2),
        "daily_median": round(float(daily["incident_count"].median()), 2),
        "daily_minimum": int(daily["incident_count"].min()),
        "daily_maximum": int(daily["incident_count"].max()),
        "weekend_incidents": int(weekend.sum()),
        "outside_08_18_incidents": int(outside_08_18.sum()),
        "weekend_or_outside_08_18_share": round(float((weekend | outside_08_18).mean()), 4),
        "category_missing_share": round(float((minimal["category"] == "Não informado").mean()), 4),
        "missing_by_field": missing,
        "window_rationale": config["analysis_window"]["rationale"],
    }
    (evidence / "01_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Relatório de qualidade dos dados",
        "",
        f"- Fonte: {config['source']['name']}.",
        f"- Proveniência: {config['source']['provenance']}.",
        f"- Arquivo/aba: `{config['source']['raw_file']}` / `{config['source']['sheet_name']}`.",
        f"- Linhas no arquivo-fonte: {raw_rows:,}.",
        f"- Incidentes únicos válidos na fonte: {len(valid):,}.",
        f"- Janela analítica: {start.date()} a {end.date()}.",
        f"- Incidentes usados: {len(minimal):,}.",
        f"- Dias: {len(daily)}; dias sem incidentes: {(daily['incident_count'] == 0).sum()}.",
        f"- Volume diário: média {daily['incident_count'].mean():.2f}, mediana {daily['incident_count'].median():.0f}, máximo {daily['incident_count'].max()}.",
        f"- Incidentes em fim de semana ou fora de 08h–18h: {(weekend | outside_08_18).sum():,} ({100 * (weekend | outside_08_18).mean():.2f}%).",
        "",
        "## Decisão sobre a janela",
        "",
        config["analysis_window"]["rationale"],
        "",
        "## Observação metodológica",
        "",
        "Os atributos categóricos são usados somente para análise descritiva. A previsão de volume usa a série diária agregada e variáveis temporais conhecidas no momento da previsão.",
        f"A base registra aberturas em todos os dias e horários de 2025; {100 * (weekend | outside_08_18).mean():.2f}% ocorrem em fins de semana ou fora de 08h–18h, comportamento compatível com o contexto operacional 24x7 do MVP.",
        "Atributos ausentes são identificados como 'Não informado'; nenhum valor categórico é fabricado para substituir informação inexistente.",
    ]
    (evidence / "01_quality_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(prepare_dataset(), ensure_ascii=False, indent=2))
