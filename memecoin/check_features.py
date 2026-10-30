import sys; sys.path.insert(0,'.')
from reanalysis import load, build_features
import numpy as np, pandas as pd
pc, pm, tr, ta, ts = load()
feats = build_features(pc, pm, tr, ta, ts)

# Build X (train) and X_test (test) the same way build_submission.py does
drop_cols = ['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']

labeled = feats[feats['label'].notna()].copy()
X = labeled.drop(columns=drop_cols).fillna(0).values
y = labeled['label'].values
print("X shape:", X.shape, "| y shape:", y.shape)
print("labeled shape:", labeled.shape)

# Test features
test_mints = ts['mint'].unique()
X_test = feats[feats['mint'].isin(test_mints)].drop(columns=drop_cols).fillna(0).values
print("X_test shape:", X_test.shape)
print("X_test columns:", list(feats.drop(columns=drop_cols).columns))
