import ast
import hashlib
import json
import os
import tempfile
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "opsvision-matplotlib-tests"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from PIL import Image

from src.configuration import database_path
from src.modeling import FEATURE_NAMES, build_features
from src.visualization import (
    LOGO_PATH,
    OPSVISION_COLORS,
    STREAMLIT_ICON_PATH,
    WATERMARK_PATH,
    add_matplotlib_watermark,
    add_plotly_watermark,
    validate_visual_assets,
)

ROOT = Path(__file__).resolve().parents[1]


class PipelineOutputTests(unittest.TestCase):
    def test_daily_series_is_complete(self):
        daily = pd.read_csv(ROOT / "data/processed/incident_count_daily.csv", parse_dates=["date"])
        config = yaml.safe_load((ROOT / "config/project.yaml").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "evidence/01_quality_report.json").read_text(encoding="utf-8"))
        expected_days = len(
            pd.date_range(
                config["analysis_window"]["start_date"],
                config["analysis_window"]["end_date"],
            )
        )
        self.assertEqual(len(daily), expected_days)
        self.assertEqual(int(daily["incident_count"].sum()), quality["analysis_incidents"])
        self.assertTrue((daily["date"].diff().dropna() == pd.Timedelta(days=1)).all())

    def test_forecast_has_seven_nonnegative_values(self):
        forecast = pd.read_csv(ROOT / "data/processed/forecast_7_days.csv")
        self.assertEqual(forecast["horizon"].tolist(), list(range(1, 8)))
        values = forecast[["baseline_forecast", "model_forecast", "recommended_forecast"]]
        self.assertTrue((values >= 0).all().all())

    def test_normalized_inference_store_has_metadata_and_two_methods(self):
        predictions = pd.read_csv(ROOT / "data/processed/forecast_predictions.csv")
        latest_run_id = predictions.sort_values(
            ["prediction_generated_at", "inference_run_id"]
        ).iloc[-1]["inference_run_id"]
        current = predictions[predictions["inference_run_id"] == latest_run_id]
        registry = json.loads((ROOT / "models/model_registry.json").read_text(encoding="utf-8"))
        required = {
            "inference_run_id",
            "prediction_generated_at",
            "origin_date",
            "forecast_date",
            "horizon",
            "predicted_incidents",
            "forecast_method",
            "model_version",
            "data_cutoff_date",
            "is_recommended",
        }
        self.assertTrue(required.issubset(current.columns))
        self.assertEqual(len(current), 14)
        self.assertEqual(
            set(current["forecast_method"]),
            {"seasonal_naive_lag_7", registry["active_model"]["model_code"]},
        )
        self.assertEqual(sorted(current["horizon"].unique().tolist()), list(range(1, 8)))
        self.assertEqual(int(current["is_recommended"].sum()), 7)
        self.assertTrue((current["predicted_incidents"] >= 0).all())

    def test_prediction_store_preserves_runs_without_duplicate_keys(self):
        predictions = pd.read_csv(ROOT / "data/processed/forecast_predictions.csv")
        self.assertGreaterEqual(predictions["inference_run_id"].nunique(), 2)
        run_sizes = predictions.groupby("inference_run_id").size()
        self.assertTrue((run_sizes == 14).all())
        self.assertFalse(
            predictions.duplicated(["inference_run_id", "forecast_method", "horizon"]).any()
        )

    def test_model_registry_and_materialized_features_exist(self):
        registry = json.loads((ROOT / "models/model_registry.json").read_text(encoding="utf-8"))
        active = registry["active_model"]
        self.assertTrue((ROOT / active["artifact_path"]).exists())
        features = pd.read_csv(ROOT / "data/processed/model_features.csv")
        daily = pd.read_csv(ROOT / "data/processed/incident_count_daily.csv")
        self.assertEqual(len(features), len(daily) - 28)
        self.assertIn("incident_count", features.columns)
        self.assertIn("lag_7", features.columns)

    def test_features_use_only_history_available_before_target_date(self):
        history = list(range(1, 29))
        values = dict(zip(FEATURE_NAMES, build_features(history, pd.Timestamp("2025-01-29"))))
        self.assertEqual(values["lag_1"], 28)
        self.assertEqual(values["lag_7"], 22)
        self.assertEqual(values["lag_14"], 15)
        self.assertEqual(values["lag_28"], 1)
        self.assertEqual(values["rolling_mean_7"], sum(range(22, 29)) / 7)
        self.assertEqual(values["rolling_mean_28"], sum(range(1, 29)) / 28)

    def test_baseline_and_model_share_origins_targets_and_horizons(self):
        predictions = pd.read_csv(
            ROOT / "evidence/03_test_predictions.csv",
            parse_dates=["origin_date", "target_date"],
        )
        daily = pd.read_csv(
            ROOT / "data/processed/incident_count_daily.csv",
            parse_dates=["date"],
        ).set_index("date")["incident_count"]
        expected_baseline = predictions["target_date"].map(
            lambda target: float(daily.loc[target - pd.Timedelta(days=7)])
        )
        self.assertTrue(predictions["baseline_forecast"].equals(expected_baseline))
        self.assertTrue(
            (
                predictions["target_date"]
                == predictions["origin_date"] + pd.to_timedelta(predictions["horizon"], unit="D")
            ).all()
        )

    def test_published_metrics_recompute_from_backtest(self):
        predictions = pd.read_csv(ROOT / "evidence/03_test_predictions.csv")
        summary = json.loads((ROOT / "evidence/05_model_summary.json").read_text(encoding="utf-8"))
        model_mae = (predictions["actual"] - predictions["model_forecast"]).abs().mean()
        baseline_mae = (predictions["actual"] - predictions["baseline_forecast"]).abs().mean()
        self.assertAlmostEqual(model_mae, summary["model_test_mae"], places=4)
        self.assertAlmostEqual(baseline_mae, summary["baseline_test_mae"], places=4)
        published = pd.read_csv(ROOT / "evidence/04_metrics_by_horizon.csv").set_index("horizon")
        for horizon, group in predictions.groupby("horizon"):
            self.assertAlmostEqual(
                (group["actual"] - group["model_forecast"]).abs().mean(),
                published.loc[horizon, "model_mae"],
            )
            self.assertAlmostEqual(
                (group["actual"] - group["baseline_forecast"]).abs().mean(),
                published.loc[horizon, "baseline_mae"],
            )

    def test_serving_layer_exposes_curated_views(self):
        database = database_path(ROOT / "config/project.yaml")
        self.assertTrue(database.exists())
        with closing(sqlite3.connect(database)) as connection:
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            self.assertTrue(
                {
                    "forecast_predictions",
                    "daily_actuals",
                    "assignment_group_summary",
                    "v_recommended_forecast",
                    "v_forecast_vs_actual",
                    "v_backtest_comparison",
                }.issubset(objects)
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM v_recommended_forecast").fetchone()[0], 7
            )
            indexes = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
            }
            self.assertIn("ux_forecast_run_method_horizon", indexes)

    def test_dashboard_uses_serving_contract_not_model_or_csv(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("ServingRepository", source)
        self.assertNotIn("read_csv", source)
        self.assertNotIn("joblib", source)

    def test_temporal_split_and_honest_result(self):
        summary = json.loads((ROOT / "evidence/05_model_summary.json").read_text(encoding="utf-8"))
        self.assertLess(summary["development_end_date"], summary["test_start_date"])
        expected_hypothesis = summary["model_test_mae"] < summary["baseline_test_mae"]
        self.assertEqual(summary["predictive_hypothesis_confirmed"], expected_hypothesis)
        expected_code = (
            summary["selected_model_code"] if expected_hypothesis else "seasonal_naive_lag_7"
        )
        self.assertEqual(summary["recommended_method_code"], expected_code)

    def test_official_dataset_is_packaged_and_validated(self):
        config = yaml.safe_load((ROOT / "config/project.yaml").read_text(encoding="utf-8"))
        source = ROOT / config["source"]["raw_file"]
        self.assertTrue(source.exists())
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            config["source"]["expected_sha256"],
        )
        metadata = json.loads((ROOT / "data/raw/source_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["sheet_name"], "Dataset Geral")

    def test_official_visual_assets_are_packaged_unchanged(self):
        expected = {
            LOGO_PATH: (
                "fe2c76de08229639ef26fe41ec21cba14f55fdedd7eec258eaa8816016a636c8",
                (1030, 622),
            ),
            WATERMARK_PATH: (
                "e049ae665a583a0e067fca3470764de84e56630ffcf056e4ac18dd2dd1bcaa50",
                (512, 512),
            ),
            STREAMLIT_ICON_PATH: (
                "8f3d6a983d488177cd03650bd56505e37961ab7b4907c44a718e7d97211ed86a",
                (512, 512),
            ),
        }
        self.assertEqual(set(validate_visual_assets().values()), set(expected))
        for path, (digest, size) in expected.items():
            self.assertTrue(path.is_absolute())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, size)
                self.assertEqual(image.mode, "RGBA")

    def test_reusable_watermark_helpers(self):
        figure, axis = plt.subplots(figsize=(4, 3))
        artist = add_matplotlib_watermark(axis)
        self.assertIn(artist, axis.images)
        plt.close(figure)

        class PlotlyLikeFigure:
            def __init__(self):
                self.images = []

            def add_layout_image(self, config):
                self.images.append(config)

        plotly_figure = PlotlyLikeFigure()
        add_plotly_watermark(plotly_figure)
        self.assertEqual(len(plotly_figure.images), 1)
        self.assertTrue(plotly_figure.images[0]["source"].startswith("data:image/png;base64,"))
        self.assertEqual(plotly_figure.images[0]["opacity"], 1.0)

    def test_dashboard_uses_official_branding_and_shared_theme(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Image.open(STREAMLIT_ICON_PATH)", source)
        self.assertIn("st.image(str(LOGO_PATH)", source)
        self.assertIn("apply_plotly_theme", source)
        for legacy_color in ["#0B6B57", "#1779BA", "#D97925", "#52606D", "#111827"]:
            self.assertNotIn(legacy_color, source)
        streamlit_calls = sorted(
            (
                node.lineno,
                node.func.attr,
            )
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "st"
        )
        self.assertEqual(streamlit_calls[0][1], "set_page_config")

    def test_dashboard_runtime_validator_is_packaged(self):
        source = (ROOT / "scripts/validate_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("streamlit.testing.v1", source)
        self.assertIn("evidence/17_dashboard_runtime_validation.json", source)
        for label in [
            "Visão Geral",
            "Previsão D+1 a D+7",
            "Histórico e Incidentes",
            "Qualidade e Modelo",
        ]:
            self.assertIn(label, source)

    def test_exported_charts_use_semantic_colors(self):
        def count_exact_rgb(path: Path, hex_color: str) -> int:
            rgb = tuple(bytes.fromhex(hex_color.removeprefix("#")))
            with Image.open(path) as image:
                converted = image.convert("RGB")
                colors = converted.getcolors(maxcolors=converted.width * converted.height)
                return {color: count for count, color in (colors or [])}.get(rgb, 0)

        self.assertGreater(
            count_exact_rgb(ROOT / "evidence/06_daily_series.png", OPSVISION_COLORS["navy"]),
            100,
        )
        self.assertGreater(
            count_exact_rgb(
                ROOT / "evidence/08_model_vs_baseline.png",
                OPSVISION_COLORS["primary_blue"],
            ),
            100,
        )
        self.assertGreater(
            count_exact_rgb(
                ROOT / "evidence/08_model_vs_baseline.png",
                OPSVISION_COLORS["violet"],
            ),
            100,
        )


if __name__ == "__main__":
    unittest.main()
