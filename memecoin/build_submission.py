"""
Build the submission for memecoins-pump-or-dump Kaggle challenge.
Uses the deterministic top-N model predictions from the re-analysis.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold

DATA = "/home/sudosudo/.openclaw/workspace/memecoin_data"
N_PREDICT = 100  # number of tokens to predict as hits

def load():
    pc = pd.read_csv(f"{DATA}/pumpfun_token_creation.csv")
    pm = pd.read_csv(f"{DATA}/pfamm_migrations.csv")
    tr = pd.read_csv(f"{DATA}/train.csv")
    ta = pd.read_csv(f"{DATA}/train_archive.csv")
    ts = pd.read_csv(f"{DATA}/test.csv")
    return pc, pm, tr, ta, ts

def build_features(pc, pm, tr, ta, ts):
    from reanalysis import build_features as bf
    return bf(pc, pm, tr, ta, ts)

def main():
    pc, pm, tr, ta, ts = load()
    feats = build_features(pc, pm, tr, ta, ts)
    print("debug: feats shape:", feats.shape, "| label in feats:", 'label' in feats.columns)

    labeled = feats[feats['label'].notna()].copy()
    drop_cols = ['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']
    X = labeled.drop(columns=drop_cols).fillna(0).values
    y = labeled['label'].values

    # Fit on all labeled data (for final predictions) - use the same model
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_pred = np.zeros(len(labeled))
    for tr_idx, va_idx in skf.split(X, y):
        m = HistGradientBoostingClassifier(max_iter=80, learning_rate=0.05, max_depth=4, random_state=42)
        m.fit(X[tr_idx], y[tr_idx])
        oof_pred[va_idx] = m.predict_proba(X[va_idx])[:,1]
    oof_label = y.copy()

    # Top N predictions on the full labeled set (for the ranking basis)
    labeled['oof_pred'] = oof_pred
    top_n = labeled.nlargest(N_PREDICT, 'oof_pred')
    print(f"Top {N_PREDICT} predictions: {top_n['label'].sum()} hits, precision@{N_PREDICT} = {top_n['label'].mean():.4f}")

    # Build submission for the test set
    # Map test mints to the ranked predictions (use the same features; prediction for test = ranking based on training)
    # Drop the same identifier columns used in training
    X_test = feats[feats['mint'].isin(ts['mint'])].drop(columns=drop_cols).fillna(0).values
    # Retrain on all labeled data for test prediction
    final_model = HistGradientBoostingClassifier(max_iter=80, learning_rate=0.05, max_depth=4, random_state=42)
    final_model.fit(X, y)
    test_pred = final_model.predict_proba(X_test)[:, 1]
    feats.loc[feats['mint'].isin(ts['mint']), 'test_pred'] = test_pred

    # Top N test predictions
    test_top = feats[feats['mint'].isin(ts['mint'])].nlargest(N_PREDICT, 'test_pred')
    print(f"Test top {N_PREDICT}: {test_top['label'].sum()} hits (known, proxy)")
    print(f"Test top {N_PREDICT} hit rate: {test_top['label'].mean():.4f}")

    # Build submission
    submission = pd.DataFrame({'mint': ts['mint'], 'tp': 0})
    submission.loc[submission['mint'].isin(test_top['mint']), 'tp'] = 1
    # Ensure tp is int
    submission['tp'] = submission['tp'].astype(int)
    submission = submission[['mint', 'tp']]

    # Verify
    assert len(submission) == len(ts), f"Row count mismatch: {len(submission)} vs {len(ts)}"
    assert list(submission['mint']) == list(ts['mint']), "Mint order mismatch"
    assert (submission['tp'].isin([0,1])).all(), "tp values not 0/1"
    assert submission['tp'].sum() == N_PREDICT, f"tp count = {submission['tp'].sum()}"

    submission.to_csv('memecoin_submission.csv', index=False)
    print(f"\nSubmission saved: memecoin_submission.csv")
    print(f"Rows: {len(submission)}")
    print(f"tp=1: {N_PREDICT}, tp=0: {len(submission) - N_PREDICT}")
    print("\nFirst 10 rows:")
    print(submission.head(10).to_string())

    # Distribution of predictions
    print(f"\ntp=1 distribution check: {submission['tp'].sum()} ones")

if __name__ == '__main__':
    main()
