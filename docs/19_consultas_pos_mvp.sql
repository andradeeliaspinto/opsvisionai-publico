-- Somente leitura. Execute contra data/serving/opsvision_serving.db.
SELECT job_id, job_type, started_at, finished_at, duration_seconds, status,
       records_processed, model_version, error_message
FROM pipeline_job_runs ORDER BY started_at DESC;

SELECT model_version, algorithm, status, training_end_date,
       evaluation_mae, baseline_mae, decision_reason
FROM registered_models ORDER BY trained_at DESC;

SELECT candidate_version, champion_version, candidate_mae, champion_mae,
       baseline_mae, new_actuals_count, decision, reason
FROM model_promotion_history ORDER BY evaluated_at DESC;

SELECT evaluation_source, model_version, horizon, observations, mae,
       mean_signed_error, period_start, period_end
FROM forecast_monitoring_metrics ORDER BY evaluation_source,model_version,horizon;

SELECT forecast_date,horizon,predicted_incidents,forecast_method,model_version
FROM v_recommended_forecast ORDER BY horizon;

SELECT alert_id,forecast_date,horizon,alert_level,threshold_value,status,model_version
FROM operational_alerts ORDER BY generated_at DESC,horizon;

SELECT mode,status,attempts,payload_format,payload_json FROM integration_delivery_log;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
