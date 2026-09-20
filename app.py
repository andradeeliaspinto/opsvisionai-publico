from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

from src.configuration import database_path
from src.serving_repository import ServingRepository
from src.visualization import (
    LOGO_PATH,
    OPSVISION_COLORS,
    STATUS_COLORS,
    STREAMLIT_ICON_PATH,
    apply_plotly_theme,
    get_streamlit_css,
    validate_visual_assets,
)

ROOT = Path(__file__).resolve().parent
DATABASE = database_path(ROOT / "config/project.yaml")
OBSERVED_COLOR = OPSVISION_COLORS["navy"]
MODEL_COLOR = OPSVISION_COLORS["primary_blue"]
BASELINE_COLOR = OPSVISION_COLORS["violet"]
METHOD_LABELS = {
    "seasonal_naive_lag_7": "Baseline sazonal (D-7)",
    "ridge": "Ridge",
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting",
}
WEEKDAY_LABELS = {
    "Monday": "Seg",
    "Tuesday": "Ter",
    "Wednesday": "Qua",
    "Thursday": "Qui",
    "Friday": "Sex",
    "Saturday": "Sáb",
    "Sunday": "Dom",
}


validate_visual_assets()
with Image.open(STREAMLIT_ICON_PATH) as icon_file:
    PAGE_ICON = icon_file.copy()

st.set_page_config(
    page_title="OpsVisionAI",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(get_streamlit_css(), unsafe_allow_html=True)
st.title("OpsVisionAI")
st.markdown('<div class="opsvision-accent"></div>', unsafe_allow_html=True)
st.caption("Planejamento operacional apoiado por previsão de volume de incidentes — D+1 a D+7")
st.info(
    "Demonstração com base histórica: dados encerrados em 31/12/2025. As previsões são relativas a esse corte, não à data de hoje."
)

if not DATABASE.exists():
    st.error("Serving store ausente. Execute `python run_pipeline.py` antes de abrir a aplicação.")
    st.stop()

repository = ServingRepository(DATABASE)
metadata = repository.metadata()
metrics = repository.model_metrics()
actuals = repository.daily_actuals()
forecasts = repository.latest_forecasts()
recommended = repository.recommended_forecast()

actuals["actual_date"] = pd.to_datetime(actuals["actual_date"])
forecasts["forecast_date"] = pd.to_datetime(forecasts["forecast_date"])
recommended["forecast_date"] = pd.to_datetime(recommended["forecast_date"])
forecasts["method_label"] = (
    forecasts["forecast_method"].map(METHOD_LABELS).fillna(forecasts["forecast_method"])
)
recommended["method_label"] = (
    recommended["forecast_method"].map(METHOD_LABELS).fillna(recommended["forecast_method"])
)

historical_p75 = float(actuals["actual_incidents"].quantile(0.75))
recommended["operational_signal"] = recommended["predicted_incidents"].apply(
    lambda value: "Atenção" if value >= historical_p75 else "Normal"
)
peak_row = recommended.loc[recommended["predicted_incidents"].idxmax()]
forecast_total = float(recommended["predicted_incidents"].sum())
recommended_is_baseline = recommended.iloc[0]["forecast_method"] == "seasonal_naive_lag_7"
recommended_color = BASELINE_COLOR if recommended_is_baseline else MODEL_COLOR
recommended_dash = "dash" if recommended_is_baseline else "solid"
recommended_marker = "square" if recommended_is_baseline else "circle"

with st.sidebar:
    st.image(str(LOGO_PATH), width=220)
    st.subheader("Contexto da execução")
    st.write(f"**Dados até:** {metadata['data_cutoff_date']}")
    st.write(f"**Inferência:** {metadata['prediction_generated_at']}")
    st.write(f"**Método recomendado:** {recommended.iloc[0]['method_label']}")
    st.markdown(
        '<p class="opsvision-sidebar-note">O dashboard consulta somente o serving store SQLite. '
        "Treinamento e inferência executam fora da interface.</p>",
        unsafe_allow_html=True,
    )

overview_tab, forecast_tab, history_tab, model_tab, monitoring_tab, operations_tab = st.tabs(
    [
        "Visão Geral",
        "Previsão D+1 a D+7",
        "Histórico e Incidentes",
        "Qualidade e Modelo",
        "Monitoramento do Modelo",
        "Operações e Alertas",
    ]
)

with overview_tab:
    st.subheader("Situação prevista para os próximos sete dias")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Volume previsto D+1–D+7", f"{forecast_total:,.0f}")
    col2.metric("Pico previsto", f"{peak_row['predicted_incidents']:,.0f}")
    col3.metric("Data do pico", peak_row["forecast_date"].strftime("%d/%m/%Y"))
    col4.metric("Referência de atenção", f"P75 = {historical_p75:,.0f}")

    if peak_row["predicted_incidents"] >= historical_p75:
        st.warning(
            f"Ação sugerida: revisar capacidade para {peak_row['forecast_date'].strftime('%d/%m')} "
            f"(D+{int(peak_row['horizon'])}), quando o volume previsto atinge "
            f"{peak_row['predicted_incidents']:.0f} incidentes."
        )
    else:
        st.success(
            "Nenhum dia previsto supera o percentil 75 do histórico; manter acompanhamento diário."
        )

    recent = actuals.tail(35)
    overview_figure = go.Figure()
    overview_figure.add_trace(
        go.Scatter(
            x=recent["actual_date"],
            y=recent["actual_incidents"],
            mode="lines+markers",
            name="Realizado",
            line={"color": OBSERVED_COLOR, "width": 2.5},
            marker={"symbol": "circle"},
        )
    )
    overview_figure.add_trace(
        go.Scatter(
            x=recommended["forecast_date"],
            y=recommended["predicted_incidents"],
            mode="lines+markers",
            name="Previsão recomendada",
            line={"color": recommended_color, "width": 3, "dash": recommended_dash},
            marker={"symbol": recommended_marker},
        )
    )
    overview_figure.add_hline(
        y=historical_p75,
        line_dash="dot",
        line_color=STATUS_COLORS["warning"],
        annotation_text="P75 histórico",
    )
    overview_figure.update_layout(
        title="Últimos 35 dias realizados e horizonte previsto",
        xaxis_title="Data",
        yaxis_title="Incidentes",
        legend_title="Série",
        hovermode="x unified",
    )
    apply_plotly_theme(overview_figure)
    st.plotly_chart(overview_figure, width="stretch")

    attention = recommended[recommended["operational_signal"] == "Atenção"]
    st.markdown("#### Dias que exigem atenção")
    if attention.empty:
        st.write("Nenhum dia classificado acima do P75 histórico.")
    else:
        attention_display = attention[
            ["forecast_date", "horizon", "predicted_incidents", "operational_signal"]
        ].copy()
        attention_display.columns = ["Data", "Horizonte", "Incidentes previstos", "Sinal"]
        st.dataframe(attention_display, width="stretch", hide_index=True)

with forecast_tab:
    st.subheader("Previsão diária e comparação de métodos")
    st.caption(
        "A recomendação operacional usa o método de menor MAE no teste cronológico; os dois métodos permanecem visíveis para auditoria."
    )

    forecast_figure = px.line(
        forecasts,
        x="forecast_date",
        y="predicted_incidents",
        color="method_label",
        markers=True,
        labels={
            "forecast_date": "Data prevista",
            "predicted_incidents": "Incidentes previstos",
            "method_label": "Método",
        },
        color_discrete_map={
            "Baseline sazonal (D-7)": BASELINE_COLOR,
            "Ridge": MODEL_COLOR,
            "Random Forest": MODEL_COLOR,
            "Gradient Boosting": MODEL_COLOR,
        },
        title="Previsões persistidas por método",
    )
    for trace in forecast_figure.data:
        if trace.name == "Baseline sazonal (D-7)":
            trace.update(line={"dash": "dash"}, marker={"symbol": "square"})
        else:
            trace.update(line={"dash": "solid"}, marker={"symbol": "circle"})
    forecast_figure.update_layout(hovermode="x unified")
    apply_plotly_theme(forecast_figure)
    st.plotly_chart(forecast_figure, width="stretch")

    forecast_table = recommended[
        ["forecast_date", "horizon", "predicted_incidents", "method_label", "operational_signal"]
    ].copy()
    forecast_table.columns = ["Data", "Horizonte", "Previsão recomendada", "Método", "Sinal"]
    st.dataframe(forecast_table, width="stretch", hide_index=True)

    st.markdown("#### Previsto × realizado no backtest")
    selected_horizon = st.selectbox("Horizonte avaliado", options=list(range(1, 8)), index=0)
    backtest = repository.backtest()
    backtest["target_date"] = pd.to_datetime(backtest["target_date"])
    selected_backtest = backtest[backtest["horizon"] == selected_horizon]
    backtest_figure = go.Figure()
    for column, label, color, dash, symbol in [
        ("actual", "Realizado", OBSERVED_COLOR, "solid", "circle"),
        ("baseline_forecast", "Baseline", BASELINE_COLOR, "dash", "square"),
        ("model_forecast", "Modelo", MODEL_COLOR, "dot", "diamond"),
    ]:
        backtest_figure.add_trace(
            go.Scatter(
                x=selected_backtest["target_date"],
                y=selected_backtest[column],
                mode="lines+markers",
                name=label,
                line={"color": color, "dash": dash},
                marker={"symbol": symbol},
            )
        )
    backtest_figure.update_layout(
        title=f"Backtest cronológico — horizonte D+{selected_horizon}",
        xaxis_title="Data-alvo",
        yaxis_title="Incidentes",
        hovermode="x unified",
    )
    apply_plotly_theme(backtest_figure)
    st.plotly_chart(backtest_figure, width="stretch")

with history_tab:
    st.subheader("Histórico, sazonalidade e composição dos incidentes")
    date_range = st.date_input(
        "Período histórico",
        value=(actuals["actual_date"].min().date(), actuals["actual_date"].max().date()),
        min_value=actuals["actual_date"].min().date(),
        max_value=actuals["actual_date"].max().date(),
    )
    if isinstance(date_range, (tuple, list)):
        if date_range:
            start_date, end_date = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[-1])
        else:
            start_date, end_date = actuals["actual_date"].min(), actuals["actual_date"].max()
    else:
        start_date = end_date = pd.Timestamp(date_range)
    filtered = actuals[actuals["actual_date"].between(start_date, end_date, inclusive="both")]
    history_figure = px.line(
        filtered,
        x="actual_date",
        y="actual_incidents",
        labels={"actual_date": "Data", "actual_incidents": "Incidentes"},
        title="Volume diário realizado",
    )
    history_figure.update_traces(line_color=OBSERVED_COLOR)
    apply_plotly_theme(history_figure)
    st.plotly_chart(history_figure, width="stretch")

    left, right = st.columns(2)
    weekday = repository.weekday_summary()
    weekday["weekday_label"] = weekday["weekday"].map(WEEKDAY_LABELS)
    weekday_figure = px.bar(
        weekday,
        x="weekday_label",
        y="mean",
        labels={"weekday_label": "Dia", "mean": "Média diária"},
        title="Sazonalidade semanal",
    )
    weekday_figure.update_traces(marker_color=OBSERVED_COLOR)
    apply_plotly_theme(weekday_figure)
    left.plotly_chart(weekday_figure, width="stretch")

    hourly = repository.hourly_summary()
    hourly_figure = px.bar(
        hourly,
        x="hour",
        y="incident_count",
        labels={"hour": "Hora", "incident_count": "Incidentes"},
        title="Distribuição por hora de abertura",
    )
    hourly_figure.update_traces(marker_color=OBSERVED_COLOR)
    apply_plotly_theme(hourly_figure)
    right.plotly_chart(hourly_figure, width="stretch")

    col_category, col_priority, col_group = st.columns(3)
    with col_category:
        st.markdown("#### Categorias")
        st.dataframe(repository.category_summary().head(10), width="stretch", hide_index=True)
    with col_priority:
        st.markdown("#### Prioridades")
        st.dataframe(repository.priority_summary(), width="stretch", hide_index=True)
    with col_group:
        st.markdown("#### Grupos designados")
        st.dataframe(
            repository.assignment_group_summary().head(10), width="stretch", hide_index=True
        )

with model_tab:
    st.subheader("Qualidade do modelo — visão técnica e acadêmica")
    st.caption("Avaliação histórica da Fase 4. O Champion atual consta em Monitoramento do Modelo.")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("MAE do modelo", f"{float(metrics['model_test_mae']):.2f}")
    col2.metric("MAE do baseline", f"{float(metrics['baseline_test_mae']):.2f}")
    delta = float(metrics["model_test_mae"]) - float(metrics["baseline_test_mae"])
    col3.metric("Diferença de MAE", f"{delta:+.2f}")
    col4.metric("Origens de teste", f"{int(metrics['test_rolling_origins'])}")

    if bool(metrics["predictive_hypothesis_confirmed"]):
        st.success(
            f"O {metrics['selected_model']} superou o baseline sazonal no teste cronológico; "
            "a hipótese preditiva foi confirmada para este recorte."
        )
    else:
        st.warning(
            f"O {metrics['selected_model']} não superou o baseline sazonal no teste final. "
            "A hipótese preditiva não foi confirmada e o baseline é o método recomendado."
        )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Seleção na validação")
        st.dataframe(repository.validation_candidates(), width="stretch", hide_index=True)
    with right:
        st.markdown("#### Erro por horizonte")
        horizon_metrics = repository.horizon_metrics().melt(
            id_vars="horizon",
            value_vars=["model_mae", "baseline_mae"],
            var_name="method",
            value_name="mae",
        )
        horizon_metrics["method"] = horizon_metrics["method"].map(
            {"model_mae": "Modelo", "baseline_mae": "Baseline"}
        )
        horizon_figure = px.line(
            horizon_metrics,
            x="horizon",
            y="mae",
            color="method",
            markers=True,
            labels={"horizon": "Horizonte", "mae": "MAE", "method": "Método"},
            color_discrete_map={"Modelo": MODEL_COLOR, "Baseline": BASELINE_COLOR},
            title="MAE por horizonte previsto",
        )
        for trace in horizon_figure.data:
            if trace.name == "Baseline":
                trace.update(line={"dash": "dash"}, marker={"symbol": "square"})
            else:
                trace.update(line={"dash": "solid"}, marker={"symbol": "circle"})
        apply_plotly_theme(horizon_figure)
        st.plotly_chart(horizon_figure, width="stretch")

    with st.expander("Fonte, recorte e limitações metodológicas"):
        st.markdown(
            f"""
            **Fonte:** {metadata["dataset"]} — {metadata["publisher"]}  
            **Proveniência:** {metadata["provenance"]}  
            **Arquivo/aba:** `{metadata["source_file"]}` / `{metadata["source_sheet"]}`  
            **Período:** {metadata["series_start"]} a {metadata["series_end"]}  
            **Teste cronológico:** {metrics["test_start_date"]} a {metrics["test_end_date"]}  
            **Versão do modelo:** `{metrics["model_version"]}`

            O arquivo oficial possui {int(metadata["source_rows"]):,} registros; o recorte contínuo de 2025
            usa {int(metadata["analysis_incidents"]):,} incidentes. Nesse recorte,
            {100 * float(metadata["weekend_or_outside_08_18_share"]):.2f}% das aberturas ocorrem em fins de
            semana ou fora de 08h–18h, comportamento compatível com o contexto 24x7. Categorias ausentes
            permanecem explicitamente como “Não informado”. Não há dados reais posteriores a
            {metadata["data_cutoff_date"]}; por isso, previsto × realizado é demonstrado no backtest.
            """
        )

with monitoring_tab:
    st.subheader("Monitoramento do Modelo")
    registered = repository.registry()
    active_model = registered[registered["status"] == "ACTIVE"].iloc[0]
    jobs = repository.jobs()
    a, b, c = st.columns(3)
    a.metric("Modelo ACTIVE", active_model["model_version"])
    b.metric("Última inferência", metadata["prediction_generated_at"])
    c.metric("Último job", jobs.iloc[0]["status"] if not jobs.empty else "Sem execução")
    source_label = st.selectbox(
        "Origem da avaliação",
        ["Operacional — realizados disponíveis", "Backtest histórico — Fase 4"],
    )
    evaluation = repository.monitoring_observations(
        "LIVE" if source_label.startswith("Operacional") else "BACKTEST"
    )
    st.caption(
        "Viés = previsto − realizado. Positivo indica superestimação. Replays emitidos após a data-alvo não entram nas métricas operacionais."
    )
    if evaluation.empty:
        st.info("Dados realizados ainda insuficientes para avaliação deste indicador.")
    else:
        version = st.selectbox("Versão avaliada", sorted(evaluation["model_version"].unique()))
        evaluation = evaluation[evaluation["model_version"] == version].copy()
        run = st.selectbox(
            "Lote de previsão", ["Todos"] + sorted(evaluation["inference_run_id"].unique())
        )
        if run != "Todos":
            evaluation = evaluation[evaluation["inference_run_id"] == run].copy()
        evaluation["target_date"] = pd.to_datetime(evaluation["target_date"])
        interval = st.date_input(
            "Período de avaliação",
            value=(evaluation.target_date.min().date(), evaluation.target_date.max().date()),
            key="monitoring_period",
        )
        if isinstance(interval, tuple) and len(interval) == 2:
            evaluation = evaluation[
                evaluation.target_date.between(pd.Timestamp(interval[0]), pd.Timestamp(interval[1]))
            ]
        if evaluation.empty:
            st.info("Dados realizados ainda insuficientes para avaliação deste indicador.")
        else:
            a, b, c = st.columns(3)
            a.metric("MAE da seleção", f"{evaluation.absolute_error.mean():.2f}")
            b.metric("Viés médio", f"{evaluation.signed_error.mean():+.2f}")
            c.metric("Previsões avaliadas", len(evaluation))
            by_horizon = (
                evaluation.groupby("horizon")
                .agg(
                    MAE=("absolute_error", "mean"),
                    Vies=("signed_error", "mean"),
                    Quantidade=("actual", "size"),
                )
                .reset_index()
            )
            st.dataframe(by_horizon, hide_index=True)
            st.plotly_chart(
                px.line(by_horizon, x="horizon", y="MAE", markers=True, title="Erro por horizonte"),
                width="stretch",
            )
            timeline = evaluation.groupby("target_date").absolute_error.mean().reset_index()
            st.plotly_chart(
                px.line(
                    timeline,
                    x="target_date",
                    y="absolute_error",
                    title="Evolução temporal do erro médio",
                ),
                width="stretch",
            )
    st.markdown("#### Registry e decisões de promoção")
    st.dataframe(registered, hide_index=True)
    st.dataframe(repository.promotion_history(), hide_index=True)

with operations_tab:
    st.subheader("Histórico de execuções")
    st.dataframe(jobs, hide_index=True)
    st.subheader("Alertas operacionais")
    st.caption(
        "P75: atenção; P90: alto; P97: crítico. Limites calculados somente com histórico disponível até a origem. Alertas deste pacote referem-se ao replay offline de janeiro/2026."
    )
    st.dataframe(repository.alerts(), hide_index=True)
    st.subheader("Integrações — evidência dry-run")
    st.caption("Payloads persistidos; nenhuma comunicação externa realizada.")
    st.dataframe(repository.deliveries(), hide_index=True)
