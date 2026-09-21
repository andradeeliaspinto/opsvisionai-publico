# Banco e contratos

O SQLite possui tabelas de serving e operação. `src/database.py` aplica migrations idempotentes nas tabelas operacionais; `src/serving.py` publica o serving em transação. O DDL disponibilizado é uma referência sem dados, não um substituto para esse fluxo.

## Objetos

| Tipo | Nome |
|---|---|
| table | `alert_threshold_snapshots` |
| table | `assignment_group_summary` |
| table | `backtest_predictions` |
| table | `category_summary` |
| table | `daily_actuals` |
| table | `forecast_monitoring_metrics` |
| table | `forecast_predictions` |
| table | `horizon_metrics` |
| table | `hourly_summary` |
| table | `integration_delivery_log` |
| table | `metadata` |
| table | `model_metrics` |
| table | `model_promotion_history` |
| table | `operational_alerts` |
| table | `pipeline_job_runs` |
| table | `priority_summary` |
| table | `registered_models` |
| table | `schema_migrations` |
| table | `validation_candidates` |
| table | `weekday_summary` |
| view | `v_backtest_comparison` |
| view | `v_forecast_vs_actual` |
| view | `v_latest_inference_run` |
| view | `v_recommended_forecast` |

## Prediction storage

Cada previsão guarda lote (`inference_run_id`), instante de geração (`prediction_generated_at`), origem, data alvo, horizonte, valor previsto, método, versão, corte e indicador de recomendação. A chave única de lote/método/horizonte impede duplicação dentro do lote. Repetir o pipeline cria outro lote e preserva o anterior.

`v_latest_inference_run` seleciona o lote mais recente; `v_recommended_forecast` filtra o método recomendado; `v_forecast_vs_actual` faz o relacionamento com realizados; `v_backtest_comparison` expõe erros do teste histórico. A elegibilidade temporal LIVE é aplicada no monitoramento e no repository.

`registered_models` permite no máximo um ACTIVE por índice único. `model_promotion_history` registra decisão e comparações. `pipeline_job_runs`, `forecast_monitoring_metrics`, `alert_threshold_snapshots`, `operational_alerts` e `integration_delivery_log` registram a operação. `schema_migrations` controla alterações de estrutura.

Os tipos e constraints exatos estão em [ESQUEMA_SQLITE.sql](ESQUEMA_SQLITE.sql). As [consultas de demonstração](19_consultas_pos_mvp.sql) devem ser executadas apenas no banco autorizado. O repository utiliza URI SQLite `mode=ro`; o dashboard não escreve no banco.
