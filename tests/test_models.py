"""Small synthetic fixtures for ML isolation, preprocessing and artifact contracts."""

from pathlib import Path
import sys
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from train_models import (CONFIGS, make_pipeline, partition, select_models, fit_frozen, predict_bundle,
                          compare_baselines, SERIES_FIELDS)

FEATURES = ["modal_price_lag_1", "previous_price_change"]


def fixture():
    rows = []
    for identity, offset in [("A", 0), ("B", 100)]:
        for i, date in enumerate(pd.date_range("2024-01-01", periods=30)):
            rows.append({"state": "Gujarat", "district": "TEST", "market": identity, "commodity": "Onion",
                         "variety": "TEST", "grade": "FAQ", "series_id": identity, "date": date,
                         "split": "train" if i < 20 else ("validation" if i < 25 else "test"),
                         "modal_price_lag_1": float(100 + offset + i), "previous_price_change": float((i % 3) - 1),
                         "modal_price": float(102 + offset + i)})
    return pd.DataFrame(rows)


class ModelTests(unittest.TestCase):
    def test_partition_and_selection_reject_test_regions(self):
        frame = fixture()
        parts = partition(frame)
        with self.assertRaisesRegex(ValueError, "never TEST"):
            select_models(parts['train'], parts['test'], FEATURES, CONFIGS[:1])
        with self.assertRaisesRegex(ValueError, "excludes test"):
            fit_frozen(parts['train'], parts['test'], pd.DataFrame(), FEATURES, CONFIGS[:1])
        frame.loc[frame.split.eq('test'), 'date'] -= pd.Timedelta(days=100)
        with self.assertRaisesRegex(ValueError, "overlap"):
            partition(frame)

    def test_training_only_scaler_encoder_and_unknown_categories(self):
        frame = fixture()
        train = frame.loc[frame.split.eq('train') & frame.series_id.eq('A')]
        pipe = make_pipeline(CONFIGS[0], FEATURES)
        pipe.fit(train[SERIES_FIELDS+FEATURES], train.modal_price)
        transform = pipe.named_steps['preprocess']
        np.testing.assert_allclose(transform.named_transformers_['numeric'].mean_, train[FEATURES].mean())
        self.assertEqual(transform.named_transformers_['identity'].categories_[2].tolist(), ['A'])
        unknown = train.iloc[[0]].copy(); unknown['market'] = 'UNSEEN'
        self.assertTrue(np.isfinite(pipe.predict(unknown[SERIES_FIELDS+FEATURES])).all())
        with self.assertRaisesRegex(ValueError, "target"):
            make_pipeline(CONFIGS[0], FEATURES + ['modal_price'])

    def test_test_mutation_cannot_change_selection_or_preprocessing(self):
        frame = fixture(); parts = partition(frame)
        first = select_models(parts['train'], parts['validation'], FEATURES, CONFIGS[:2])
        frame.loc[frame.split.eq('test'), ['modal_price', *FEATURES]] = 999999
        mutated = partition(frame)
        second = select_models(mutated['train'], mutated['validation'], FEATURES, CONFIGS[:2])
        for a,b in zip(first, second):
            pd.testing.assert_frame_equal(a,b)

    def test_all_model_families_are_finite_and_deterministic(self):
        parts = partition(fixture())
        for config in [CONFIGS[0], CONFIGS[2], CONFIGS[4], CONFIGS[5], CONFIGS[6]]:
            with self.subTest(model=config['model']):
                first = make_pipeline(config, FEATURES)
                second = make_pipeline(config, FEATURES)
                first.fit(parts['train'][SERIES_FIELDS+FEATURES], parts['train'].modal_price)
                second.fit(parts['train'][SERIES_FIELDS+FEATURES], parts['train'].modal_price)
                a=first.predict(parts['validation'][SERIES_FIELDS+FEATURES]); b=second.predict(parts['validation'][SERIES_FIELDS+FEATURES])
                self.assertTrue(np.isfinite(a).all())
                np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-10)

    def test_other_market_future_outcomes_cannot_change_local_selection(self):
        frame=fixture(); parts=partition(frame)
        first=select_models(parts['train'],parts['validation'],FEATURES,CONFIGS[:2])[1]
        frame.loc[frame.series_id.eq('B'),'modal_price'] *= 100
        altered=partition(frame)
        second=select_models(altered['train'],altered['validation'],FEATURES,CONFIGS[:2])[1]
        pd.testing.assert_frame_equal(first.loc[first.series_id.eq('A')].reset_index(drop=True),
                                      second.loc[second.series_id.eq('A')].reset_index(drop=True))

    def test_saved_bundle_reload_identity_and_targets_excluded(self):
        parts = partition(fixture())
        _, selected = select_models(parts['train'], parts['validation'], FEATURES, CONFIGS[:1])
        bundle = fit_frozen(parts['train'], parts['validation'], selected, FEATURES, CONFIGS[:1])
        original = predict_bundle(bundle, parts['test'])
        altered = parts['test'].copy(); altered['modal_price'] = 0
        np.testing.assert_allclose(original,predict_bundle(bundle,altered))
        with tempfile.TemporaryDirectory(prefix='agrisense-model-test-') as folder:
            path=Path(folder)/'model.joblib'; joblib.dump(bundle,path)
            np.testing.assert_allclose(original,predict_bundle(joblib.load(path),parts['test']))
        self.assertEqual(set(bundle['models']),{'A','B'})
        bad = parts['test'].copy(); bad['grade']='Non-FAQ'
        with self.assertRaisesRegex(ValueError,'identity'):
            predict_bundle(bundle,bad)

    def test_baseline_comparison_exact_identity_metrics_and_mismatch(self):
        frame=fixture().query("split == 'test'").copy()
        predicted=frame[SERIES_FIELDS+['series_id','date']].copy()
        predicted['actual_modal_price']=100.; predicted['predicted_modal_price']=105.
        predicted['absolute_error']=5.; predicted['signed_error']=5.
        baseline=predicted.copy(); baseline['phase']='test'; baseline['baseline']='naive'
        baseline['predicted_modal_price']=110.; baseline['absolute_error']=10.; baseline['gap_days']=1
        best=pd.DataFrame({'series_id':['A','B'],'baseline':['naive','naive'],'mae':[10.,10.]})
        selected=pd.DataFrame({'series_id':['A','B'],'model':['Ridge','Ridge'],'config_id':['ridge_1','ridge_1']})
        joined, comparison=compare_baselines(predicted,baseline,best,selected)
        self.assertEqual(len(joined),10)
        self.assertTrue(comparison.ml_mae.eq(5).all())
        self.assertTrue(comparison.absolute_improvement.eq(5).all())
        self.assertTrue(comparison.percentage_improvement.eq(50).all())
        self.assertTrue(comparison.winner.eq('ML').all())
        baseline.loc[baseline.index[0],'actual_modal_price']=101.
        with self.assertRaisesRegex(ValueError,'match exactly'):
            compare_baselines(predicted,baseline,best,selected)


if __name__ == '__main__':
    unittest.main()
