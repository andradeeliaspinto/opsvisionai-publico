"""Testes sem dataset: fixtures artificiais apenas em memoria, nunca realizados reais."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from src.alerts import classify_alert, derive_thresholds
from src.modeling import build_features, rolling_evaluation
from src.monitoring import calculate_error_metrics
from src.retraining import decide_promotion
from src.configuration import model_policy
from src.integrations.webhook import WebhookAlertAdapter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicUnitTests(unittest.TestCase):
    def test_features_use_available_history(self):
        history = list(range(1,29))
        features = build_features(history, pd.Timestamp('2000-02-01'))
        np.testing.assert_allclose(features[:7], [28,22,15,1,25,21.5,14.5])
        self.assertEqual(history, list(range(1,29)))

    def test_baseline_matches_same_targets(self):
        class FixedModel:
            def predict(self, x):
                return np.array([5.0])
        series = pd.Series(range(50), index=pd.date_range('2000-01-01',periods=50))
        predictions = rolling_evaluation(FixedModel(),series,first_origin=40,last_origin=40,horizon=7)
        self.assertEqual(predictions.horizon.tolist(),list(range(1,8)))
        for row in predictions.itertuples():
            self.assertEqual(row.baseline_forecast,series.loc[row.target_date-pd.Timedelta(days=7)])

    def test_mae_and_signed_bias(self):
        result = calculate_error_metrics(pd.DataFrame({'actual':[10,20,30],'predicted':[12,17,34]}))
        self.assertEqual(result['mae'],3)
        self.assertEqual(result['mean_signed_error'],1)

    def test_alert_percentile_boundaries(self):
        thresholds = derive_thresholds(pd.Series(range(101)))
        self.assertEqual([classify_alert(v,thresholds)[0] for v in [74,75,90,97]],['NORMAL','ATENCAO','ALTO','CRITICO'])

    def test_promotion_requires_new_actuals(self):
        parameters = dict(candidate_mae=8,champion_mae=10,baseline_mae=11,candidate_mean_bias=1,candidate_mean_actual=100,horizons_won_against_baseline=7,new_actuals_count=90,days_since_last_training=90,temporal_evaluation_valid=True,policy=model_policy(ROOT/'config/project.yaml'))
        self.assertTrue(decide_promotion(**parameters).eligible)
        parameters['new_actuals_count']=0
        self.assertFalse(decide_promotion(**parameters).eligible)

    def test_dry_run_never_calls_network(self):
        alert = dict(alert_id='unit-fixture',forecast_date='2000-02-01',horizon=1,predicted_incidents=100,alert_level='ATENCAO',rule_triggered='unit test',model_version='unit-fixture',status='OPEN')
        with patch('urllib.request.urlopen') as request:
            result=WebhookAlertAdapter(webhook_url=None, dry_run=True).send(alert)
        request.assert_not_called()
        self.assertEqual(result.status,'DRY_RUN')


if __name__ == '__main__':
    unittest.main()
