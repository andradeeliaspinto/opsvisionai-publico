-- Referencia estrutural, sem registros. Use migrations + pipeline para inicializar.

CREATE TABLE alert_threshold_snapshots (
            threshold_set_id TEXT PRIMARY KEY,
            computed_at TEXT NOT NULL,
            history_start_date TEXT NOT NULL,
            history_end_date TEXT NOT NULL,
            observations INTEGER NOT NULL,
            method TEXT NOT NULL,
            p75 REAL NOT NULL,
            p90 REAL NOT NULL,
            p97 REAL NOT NULL,
            policy_version INTEGER NOT NULL
        );

CREATE TABLE "assignment_group_summary" (
"assigned_group" TEXT,
  "incident_count" INTEGER,
  "share" REAL
);

CREATE TABLE "backtest_predictions" (
"origin_date" TEXT,
  "target_date" TEXT,
  "horizon" INTEGER,
  "actual" REAL,
  "model_forecast" REAL,
  "baseline_forecast" REAL
);

CREATE TABLE "category_summary" (
"category" TEXT,
  "incident_count" INTEGER,
  "share" REAL
);

CREATE TABLE "daily_actuals" (
"actual_date" TEXT,
  "actual_incidents" INTEGER
);

CREATE TABLE forecast_monitoring_metrics (
            metric_id TEXT PRIMARY KEY,
            source_signature TEXT NOT NULL,
            evaluation_source TEXT NOT NULL CHECK (evaluation_source IN ('LIVE', 'BACKTEST')),
            computed_at TEXT NOT NULL,
            inference_run_id TEXT,
            model_version TEXT NOT NULL,
            forecast_method TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            metric_scope TEXT NOT NULL CHECK (metric_scope IN ('AGGREGATE', 'HORIZON')),
            horizon INTEGER,
            observations INTEGER NOT NULL CHECK (observations >= 0),
            mae REAL,
            mean_signed_error REAL,
            mean_actual REAL,
            CHECK (
                (metric_scope = 'AGGREGATE' AND horizon IS NULL)
                OR (metric_scope = 'HORIZON' AND horizon BETWEEN 1 AND 7)
            )
        );

CREATE TABLE "forecast_predictions" (
"prediction_generated_at" TEXT,
  "origin_date" TEXT,
  "forecast_date" TEXT,
  "horizon" INTEGER,
  "predicted_incidents" REAL,
  "forecast_method" TEXT,
  "model_version" TEXT,
  "data_cutoff_date" TEXT,
  "is_recommended" INTEGER,
  "inference_run_id" TEXT
);

CREATE TABLE "horizon_metrics" (
"horizon" INTEGER,
  "model_mae" REAL,
  "baseline_mae" REAL
);

CREATE TABLE "hourly_summary" (
"hour" INTEGER,
  "incident_count" INTEGER,
  "share" REAL
);

CREATE TABLE integration_delivery_log (
            delivery_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            alert_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            adapter_name TEXT NOT NULL,
            payload_format TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('DRY_RUN', 'LIVE')),
            status TEXT NOT NULL CHECK (status IN ('DRY_RUN', 'SUCCESS', 'FAILED', 'SKIPPED')),
            attempts INTEGER NOT NULL CHECK (attempts >= 0),
            http_status INTEGER,
            error_message TEXT,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (alert_id) REFERENCES operational_alerts(alert_id)
        );

CREATE TABLE "metadata" (
"key" TEXT,
  "value" TEXT
);

CREATE TABLE "model_metrics" (
"selected_model" TEXT,
  "model_version" TEXT,
  "model_test_mae" REAL,
  "baseline_test_mae" REAL,
  "relative_mae_reduction" REAL,
  "horizons_model_wins" INTEGER,
  "recommended_method" TEXT,
  "recommended_method_code" TEXT,
  "predictive_hypothesis_confirmed" INTEGER,
  "test_start_date" TEXT,
  "test_end_date" TEXT,
  "test_rolling_origins" INTEGER,
  "test_predictions" INTEGER
);

CREATE TABLE model_promotion_history (
            promotion_id TEXT PRIMARY KEY,
            evaluated_at TEXT NOT NULL,
            candidate_version TEXT NOT NULL,
            champion_version TEXT,
            candidate_mae REAL NOT NULL,
            champion_mae REAL NOT NULL,
            baseline_mae REAL NOT NULL,
            candidate_mean_bias REAL NOT NULL,
            candidate_mean_actual REAL NOT NULL,
            horizons_won_against_baseline INTEGER NOT NULL,
            new_actuals_count INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('PROMOTED', 'REJECTED')),
            reason TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            evaluation_start_date TEXT NOT NULL,
            evaluation_end_date TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

CREATE TABLE operational_alerts (
            alert_id TEXT PRIMARY KEY,
            inference_run_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            horizon INTEGER NOT NULL CHECK (horizon BETWEEN 1 AND 7),
            predicted_incidents REAL NOT NULL CHECK (predicted_incidents >= 0),
            alert_level TEXT NOT NULL CHECK (alert_level IN ('ATENCAO', 'ALTO', 'CRITICO')),
            rule_triggered TEXT NOT NULL,
            threshold_value REAL NOT NULL,
            threshold_set_id TEXT NOT NULL,
            model_version TEXT NOT NULL,
            forecast_method TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')),
            acknowledged_at TEXT,
            closed_at TEXT,
            UNIQUE (inference_run_id, forecast_method, horizon),
            FOREIGN KEY (threshold_set_id) REFERENCES alert_threshold_snapshots(threshold_set_id)
        );

CREATE TABLE pipeline_job_runs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_seconds REAL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
            records_processed INTEGER,
            model_version TEXT,
            error_message TEXT,
            stack_trace TEXT,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

CREATE TABLE "priority_summary" (
"priority" INTEGER,
  "incident_count" INTEGER,
  "share" REAL
);

CREATE TABLE registered_models (
            model_version TEXT PRIMARY KEY,
            algorithm TEXT NOT NULL,
            model_code TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            training_start_date TEXT NOT NULL,
            training_end_date TEXT NOT NULL,
            evaluation_start_date TEXT,
            evaluation_end_date TEXT,
            evaluation_mae REAL,
            baseline_mae REAL,
            mean_signed_error REAL,
            mean_actual REAL,
            horizons_won_against_baseline INTEGER,
            artifact_path TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('CANDIDATE', 'ACTIVE', 'ARCHIVED', 'REJECTED')),
            decision_reason TEXT NOT NULL,
            feature_names_json TEXT NOT NULL,
            hyperparameters_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

CREATE TABLE "validation_candidates" (
"candidate" TEXT,
  "validation_mae" REAL,
  "validation_baseline_mae" REAL
);

CREATE TABLE "weekday_summary" (
"weekday_number" INTEGER,
  "weekday" TEXT,
  "days" INTEGER,
  "mean" REAL,
  "median" REAL,
  "minimum" INTEGER,
  "maximum" INTEGER
);

CREATE INDEX idx_actual_date ON daily_actuals(actual_date);

CREATE INDEX idx_alerts_status_date
            ON operational_alerts(status, forecast_date);

CREATE INDEX idx_delivery_attempted
            ON integration_delivery_log(attempted_at DESC);

CREATE INDEX idx_forecast_date ON forecast_predictions(forecast_date);

CREATE INDEX idx_forecast_generated ON forecast_predictions(prediction_generated_at);

CREATE INDEX idx_forecast_run ON forecast_predictions(inference_run_id);

CREATE INDEX idx_monitoring_lookup
            ON forecast_monitoring_metrics(
                evaluation_source, computed_at DESC, model_version, forecast_method, horizon
            );

CREATE INDEX idx_pipeline_job_started
            ON pipeline_job_runs(started_at DESC);

CREATE INDEX idx_pipeline_job_status
            ON pipeline_job_runs(status, started_at DESC);

CREATE INDEX idx_promotion_evaluated
            ON model_promotion_history(evaluated_at DESC);

CREATE INDEX idx_registered_models_status
            ON registered_models(status, trained_at DESC);

CREATE UNIQUE INDEX ux_actual_date ON daily_actuals(actual_date);

CREATE UNIQUE INDEX ux_forecast_run_method_horizon
            ON forecast_predictions(inference_run_id, forecast_method, horizon);

CREATE UNIQUE INDEX ux_registered_models_one_active
            ON registered_models(status) WHERE status = 'ACTIVE';

CREATE VIEW v_backtest_comparison AS
            SELECT origin_date, target_date, horizon, actual,
                   model_forecast, baseline_forecast,
                   ABS(actual - model_forecast) AS model_absolute_error,
                   ABS(actual - baseline_forecast) AS baseline_absolute_error
            FROM backtest_predictions;

CREATE VIEW v_forecast_vs_actual AS
            SELECT p.inference_run_id, p.prediction_generated_at, p.origin_date,
                   p.forecast_date, p.horizon,
                   p.predicted_incidents, p.forecast_method, p.model_version,
                   p.data_cutoff_date,
                   a.actual_incidents,
                   p.predicted_incidents - a.actual_incidents AS signed_error,
                   CASE WHEN a.actual_incidents IS NULL THEN NULL
                        ELSE ABS(a.actual_incidents - p.predicted_incidents) END AS absolute_error
            FROM forecast_predictions p
            LEFT JOIN daily_actuals a ON a.actual_date = p.forecast_date;

CREATE VIEW v_latest_inference_run AS
            SELECT *
            FROM forecast_predictions
            WHERE inference_run_id = (
                SELECT inference_run_id
                FROM forecast_predictions
                ORDER BY prediction_generated_at DESC, inference_run_id DESC
                LIMIT 1
            );

CREATE VIEW v_recommended_forecast AS
            SELECT inference_run_id, prediction_generated_at, origin_date, forecast_date, horizon,
                   predicted_incidents, forecast_method, model_version, data_cutoff_date
            FROM v_latest_inference_run
            WHERE is_recommended = 1
            ORDER BY horizon;
