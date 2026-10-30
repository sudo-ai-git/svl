"""
Re-analysis of memecoins-pump-or-dump Kaggle challenge.
Re-verifies the all-skip EV-optimal conclusion on the current 320-row test set,
and probes under-used creation-metadata features.
"""
import numpy as np
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, precision_recall_curve

DATA = "/home/sudosudo/.openclaw/workspace/memecoin_data"

def load():
    pc = pd.read_csv(f"{DATA}/pumpfun_token_creation.csv")
    pm = pd.read_csv(f"{DATA}/pfamm_migrations.csv")
    tr = pd.read_csv(f"{DATA}/train.csv")          # 17490 rows, tape features (train period)
    ta = pd.read_csv(f"{DATA}/train_archive.csv")  # 21875 rows (larger tape archive)
    ts = pd.read_csv(f"{DATA}/test.csv")           # 320 rows (current live test set)
    return pc, pm, tr, ta, ts

def build_features(pc, pm, tr, ta, ts):
    """Build mint-level features from creation + migration data. NO tape features for test."""
    feats = pd.DataFrame({'mint': pc['mint']})
    feats['creator'] = pc['creator']
    feats['created_ts'] = pc['created_ts']
    feats['name'] = pc['name'].fillna('').str.lower()
    feats['symbol'] = pc['symbol'].fillna('').str.lower()
    feats['url'] = pc['url'].fillna('')
    feats['bundle_size'] = pc['bundle_size'].fillna(0)
    feats['gas_used'] = pc['gas_used'].fillna(0)
    feats['amount_of_instructions'] = pc['amount_of_instructions'].fillna(0)
    feats['amount_of_lookup_reads'] = pc['amount_of_lookup_reads'].fillna(0)
    feats['amount_of_lookup_writes'] = pc['amount_of_lookup_writes'].fillna(0)
    feats['bundle_structure'] = pc['bundle_structure'].fillna('').str.lower()
    feats['bundled_buys'] = pc['bundled_buys'].fillna(0)
    feats['bundled_buys_count'] = pc['bundled_buys_count'].fillna(0)
    feats['dev_balance'] = pc['dev_balance'].fillna(0)
    feats['creation_ix_index'] = pc['creation_ix_index'].fillna(0)
    feats['direct_pf_invocation'] = pc['direct_pf_invocation'].fillna(0).astype(int)
    feats['mayhem_mode'] = pc['mayhem_mode'].fillna(0).astype(int)
    feats['is_cashback_enabled'] = pc['is_cashback_enabled'].fillna(0).astype(int)

    # Tape features from train OR archive (only for training tokens)
    tape_feats = pd.concat([tr[['mint','max_x','final_x']], ta[['mint','max_x','final_x']]], axis=0)
    tape_feats = tape_feats.drop_duplicates('mint')
    feats = feats.merge(tape_feats, on='mint', how='left')

    # Name/symbol keyword flags (1-gram + 2-gram)
    kw_list = ['pepe','bonk','dog','cat','moon','doge','shiba','wojak','pump','meme','coin','token','swap','ton','solana','ripple','ada','matic','link','ai','x','io','bnbtok','v2','crypto','coin','token','soon','coin','token','go','buy','sell','pump','dump','moon','wave','pop','up','down','flip','gap','coin','token']
    for kw in kw_list:
        feats[f'kw_{kw}'] = feats['name'].str.contains(kw) | feats['symbol'].str.contains(kw)
    feats['kw_pepe'] = feats['name'].str.contains('pepe') | feats['symbol'].str.contains('pepe')
    feats['kw_bonk'] = feats['name'].str.contains('bonk') | feats['symbol'].str.contains('bonk')
    feats['kw_doge'] = feats['name'].str.contains('doge') | feats['symbol'].str.contains('doge')
    feats['kw_shiba'] = feats['name'].str.contains('shiba') | feats['symbol'].str.contains('shiba')
    feats['kw_wow'] = feats['name'].str.contains('wow') | feats['symbol'].str.contains('wow')
    feats['kw_elon'] = feats['name'].str.contains('elon') | feats['symbol'].str.contains('elon')
    feats['kw_ton'] = feats['name'].str.contains('ton') | feats['symbol'].str.contains('ton')

    # URL presence + top domains
    feats['has_url'] = (feats['url'] != '').astype(int)
    url_domains = feats['url'].str.extract(r'https?://(?:www\.)?([a-z0-9\-\.]+)\.[a-z]{2,}')
    top_domains = ['pump','sol','coin','token','crypto','fin','dex','swap','defi','net','org','io','com','xyz','space','link','github','discord','twitter','x','telegram','medium','blog','coin','market','pumpfun','dex','exchange','wallet','sonic','hamster','cat','dog','pepe','bonk','doge','shib','koge','floki','triton']
    for d in top_domains:
        feats[f'url_{d}'] = url_domains[0].fillna('').str.contains(d)
    feats['url_pump'] = feats['url'].str.contains('pump')
    feats['url_sol'] = feats['url'].str.contains('sol')
    feats['url_coingecko'] = feats['url'].str.contains('coingecko')
    feats['url_coinmarketcap'] = feats['url'].str.contains('coinmarketcap')

    # Tape data from train + archive; the source of the pump-5x label for creators
    tape_all = pd.concat([tr[['mint','max_x','final_x']], ta[['mint','max_x','final_x']]], axis=0).drop_duplicates('mint')
    tape_all['label'] = (tape_all['max_x'] >= 5.0).astype(int)
    tape_with_creator = tape_all.reset_index().merge(
        pc[['mint','creator']].drop_duplicates('mint'), on='mint', how='left')
    creator_hu = tape_with_creator.groupby('creator').agg(
        cr_hit=('label', 'sum'),
        cr_n=('label', 'count')
    ).reset_index()
    creator_hu['cr_rate_eb'] = creator_hu['cr_hit'] / np.maximum(creator_hu['cr_n'], 1)
    creator_hu.rename(columns={'cr_n':'cr_n_tape','cr_hit':'cr_hit_tape','cr_rate_eb':'cr_rate_eb_tape'}, inplace=True)
    # Count of creator's tokens in full creation data (39,734 tokens)
    feats['cr_n'] = feats['creator'].map(feats['creator'].value_counts())
    feats = feats.merge(creator_hu, on='creator', how='left')
    feats['cr_n'] = feats['cr_n'].fillna(0).astype(int)
    feats['cr_n_tape'] = feats['cr_n_tape'].fillna(0).astype(int)
    feats['cr_hit_tape'] = feats['cr_hit_tape'].fillna(0).astype(int)
    # Merge tape labels into feats (needed for prior-hit-rate computation)
    feats = feats.merge(tape_all[['mint','label']], on='mint', how='left')
    # Prior hit rate EXCLUDING current token: (cr_hit - label) / (cr_n - 1) -- the core wallet-reputation feature
    feats['cr_n_prior'] = (feats['cr_n_tape'] - 1).clip(lower=0)
    feats['cr_hit_prior'] = feats['cr_hit_tape'] - feats['label']
    feats['w_hit_mean'] = np.where(feats['cr_n_prior'] > 0,
                                   feats['cr_hit_prior'] / feats['cr_n_prior'].clip(lower=1), 0.0)
    # NOTE: cr_rate_eb_tape (tape hit rate incl. current token) and cr_hit_tape (count incl. current token)
    # are LABEL LEAKS for single-token creators (cr_n_tape==1 => cr_rate_eb_tape == label) and must NOT be used.
    return feats

def eval_oos(feats, labels, n_folds=15, seed=42, sample_n=None):
    """Evaluate OOS AUC and precision@5 on train set (tape-labeled)."""
    labeled = feats[feats['label'].notna()].copy()
    y = labeled['label'].values
    X = labeled.drop(columns=['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']).fillna(0).values

    if sample_n is not None and len(X) > sample_n:
        rng = np.random.RandomState(seed)
        idx = rng.choice(len(X), size=sample_n, replace=False)
        X, y = X[idx], y[idx]

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    aucs = []
    oof_pred = np.zeros(len(labeled))
    # Use HistGradientBoosting for speed
    from sklearn.ensemble import HistGradientBoostingClassifier
    for tr_idx, va_idx in skf.split(X, y):
        model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_depth=4, random_state=seed)
        model.fit(X[tr_idx], y[tr_idx])
        oof_pred[va_idx] = model.predict_proba(X[va_idx])[:,1]
        aucs.append(roc_auc_score(y[va_idx], model.predict_proba(X[va_idx])[:,1]))
    auc_mean = np.mean(aucs)
    oos_auc = roc_auc_score(y, oof_pred)

    prec5 = precision_at_k(oof_pred, y, k=5)
    prec1 = precision_at_k(oof_pred, y, k=1)
    prec10 = precision_at_k(oof_pred, y, k=10)
    return oos_auc, auc_mean, prec5, prec1, prec10

def precision_at_k(pred, y, k=5):
    """Precision at top-k predictions."""
    n = len(y)
    # Reorder by prediction
    order = np.argsort(-pred)
    topk = y[order[:k]]
    return topk.mean()

def main():
    pc, pm, tr, ta, ts = load()
    feats = build_features(pc, pm, tr, ta, ts)
    print("Features:", feats.shape)
    print("Test mints with tape features:", feats[feats['mint'].isin(ts['mint'])]['max_x'].notna().sum())

    labeled = feats[feats['label'].notna()].copy()
    print("Labeled tokens:", len(labeled), "| hit rate:", labeled['label'].mean())
    print("Test tokens:", len(ts), "| hit rate (unknown, proxy):", labeled['label'].mean())

    # OOS evaluation
    oos_auc, auc_mean, prec5, prec1, prec10 = eval_oos(labeled, ['label'])
    print(f"OOS AUC: {oos_auc:.4f} (fold mean {auc_mean:.4f}), precision@5: {prec5:.4f}, precision@1: {prec1:.4f}, precision@10: {prec10:.4f}")

    # Also try Ridge (linear) for comparison
    from sklearn.linear_model import RidgeClassifier
    X_l = labeled.drop(columns=['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']).fillna(0).values
    y_l = labeled['label'].values
    skf = StratifiedKFold(n_splits=23, shuffle=True, random_state=42)
    aucs_lin = []
    for tr_idx, va_idx in skf.split(X_l, y_l):
        m = RidgeClassifier(alpha=1.0, random_state=42)
        m.fit(X_l[tr_idx], y_l[tr_idx])
        aucs_lin.append(roc_auc_score(y_l[va_idx], m.decision_function(X_l[va_idx])))
    print(f"Linear Ridge OOS AUC: {np.mean(aucs_lin):.4f}")

    # Feature importance of GBM for the dominant features
    print("\nTop feature importances:")
    model_all = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
    X_all = labeled.drop(columns=['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']).fillna(0).values
    y_all = labeled['label'].values
    model_all.fit(X_all, y_all)
    feat_names = labeled.drop(columns=['mint','creator','label','name','symbol','url','bundle_structure','cr_rate_eb_tape','cr_hit_tape','max_x','final_x']).columns.tolist()
    imp = sorted(zip(feat_names, model_all.feature_importances_), key=lambda x: -x[1])
    for name, i in imp[:15]:
        print(f"  {name}: {i:.4f}")
    print(f"  ... total features: {len(feat_names)}")

if __name__ == '__main__':
    main()
