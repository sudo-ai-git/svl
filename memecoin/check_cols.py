import sys; sys.path.insert(0,'.')
from reanalysis import load, build_features
import numpy as np, pandas as pd
pc, pm, tr, ta, ts = load()
feats = build_features(pc, pm, tr, ta, ts)
print("feats columns:")
for i, c in enumerate(feats.columns):
    print(f"  [{i}] {c}")
print("feats shape:", feats.shape)
print("drop_cols:", ['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x'])
print("n_drop_cols:", len(['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']))
print("number of columns after dropping drop_cols:", feats.shape[1] - len(['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']))
