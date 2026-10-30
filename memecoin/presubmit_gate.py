"""
Presubmit gate for memecoins-pump-or-dump Kaggle submission.
Validates the submission on every axis:
- Row count matches live test set
- Schema (mint, tp)
- Mint order matches live test set
- Unique mints (no duplicates)
- tp int dtype
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np

TEST_CSV = "/home/sudosudo/.openclaw/workspace/memecoin_data/test.csv"
SAMPLE_SUB = "/home/sudosudo/.openclaw/workspace/memecoin_data/sample_submission.csv"
SUBMISSION = "/home/sudosudo/.openclaw/workspace/memecoin_submission.csv"

def main():
    print("=== Presubmit Gate ===")
    # 1. Load live test and sample submission
    print("\n1) Loading live test.csv and sample_submission.csv...")
    live_test = pd.read_csv(TEST_CSV)
    live_sample = pd.read_csv(SAMPLE_SUB)
    print(f"   Live test.csv: {len(live_test)} rows")
    print(f"   Sample submission: {len(live_sample)} rows")

    # 2. Load submission
    print("\n2) Loading submission...")
    sub = pd.read_csv(SUBMISSION)
    print(f"   Submission rows: {len(sub)}")

    # 3. Validate row count
    print("\n3) Row count match...")
    assert len(sub) == len(live_test), f"Row count mismatch: {len(sub)} vs {len(live_test)}"
    print(f"   PASS: {len(sub)} == {len(live_test)}")

    # 4. Validate schema
    print("\n4) Schema validation...")
    expected_cols = {'mint', 'tp'}
    assert set(sub.columns) == expected_cols, f"Columns: {set(sub.columns)}"
    assert list(sub.columns) == ['mint', 'tp'], f"Column order: {list(sub.columns)}"
    assert sub['mint'].dtype == live_test['mint'].dtype, f"mint dtype: {sub['mint'].dtype} vs {live_test['mint'].dtype}"
    assert sub['tp'].dtype in [np.int64, np.int32, np.int8], f"tp dtype: {sub['tp'].dtype}"
    print(f"   PASS: columns={list(sub.columns)}, tp dtype={sub['tp'].dtype}")

    # 5. Validate mint order matches live test
    print("\n5) Mint order match...")
    assert list(sub['mint']) == list(live_test['mint']), "Mint order mismatch"
    print("   PASS: mint order matches live test")

    # 6. Validate mint uniqueness
    print("\n6) Mint uniqueness...")
    assert sub['mint'].is_unique, "Duplicate mints found"
    print("   PASS: all mints unique")

    # 7. Validate tp dtype
    print("\n7) tp dtype...")
    assert sub['tp'].dtype in [np.int64, np.int32, np.int8], f"tp dtype: {sub['tp'].dtype}"
    print(f"   PASS: tp dtype = {sub['tp'].dtype}")

    # 8. Validate tp values
    print("\n8) tp value range...")
    assert sub['tp'].between(0, 1).all(), f"tp values out of range: {sub['tp'].unique()}"
    print(f"   PASS: tp values ∈ {{0,1}}, tp=1 count = {sub['tp'].sum()}")

    # 9. Cross-validate with sample submission
    print("\n9) Cross-validate with sample_submission.csv...")
    assert len(sub) == len(live_sample), f"Submission rows != sample submission rows"
    assert list(sub['mint']) == list(live_sample['mint']), "Mint order != sample submission"
    print("   PASS: matches sample_submission.csv")

    print("\n=== ALL PRESUBMIT CHECKS PASSED ===")
    print(f"Submission ready: {SUBMISSION}")

if __name__ == '__main__':
    main()
