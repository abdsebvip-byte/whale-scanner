"""Quick ML integration test on 20 tickers."""
import sys, json, numpy as np, time
import pandas as pd
from ml_engine import EnsemblePredictor, MODEL_PATH
from feature_pipeline import extract_features as extract_ml_features, FEATURE_COLUMNS, N_FEATURES

ML_ENGINE_FEATURES = ["price_at_scan", "volume_ratio", "gap_pct", "short_percent"]
ML_FEATURE_COLUMNS = list(FEATURE_COLUMNS) + ML_ENGINE_FEATURES
import yfinance as yf

predictor = EnsemblePredictor(MODEL_PATH)
print("ML ready:", predictor.is_ready())

test_tickers = [
    "SMCI", "SOFI", "PLTR", "NUVO", "YYAI", "OPEN", "WISH", "CLOV",
    "HIVE", "BTBT", "MARA", "RIOT", "HOOD", "AFRM", "UPST",
    "BYND", "RIVN", "LCID", "NKLA", "TELL",
]

results = []
for sym in test_tickers:
    try:
        df = yf.download(sym, period="3mo", interval="1d", progress=False)
        if df is None or len(df) < 30:
            print(f"  {sym}: skipped (< 30 bars)")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        base_features = extract_ml_features(df)
        last_row = base_features.iloc[[-1]].to_numpy(dtype=np.float64)
        price = float(df["close"].iloc[-1])
        vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else vol
        rv = vol / avg_vol if avg_vol > 0 else 0
        if last_row.shape[1] == len(FEATURE_COLUMNS):
            prob = float(predictor.predict_proba(last_row[0]))
            if prob > 0.7:
                upside = 30 + (prob - 0.7) * 233
            elif prob > 0.5:
                upside = 10 + (prob - 0.5) * 100
            else:
                upside = prob * 20
            upside = min(upside, 150)
            conf = "HIGH" if prob > 0.7 else "MED" if prob > 0.5 else "LOW"
            print(f"  {sym}: prob={prob:.3f} upside={upside:.1f}% [{conf}] price=${price:.2f}")
            results.append({"symbol": sym, "prob": prob, "upside": upside, "conf": conf, "price": price})
        else:
            print(f"  {sym}: feature mismatch {last_row.shape[1]} vs {len(FEATURE_COLUMNS)}")
        time.sleep(0.3)
    except Exception as e:
        print(f"  {sym}: ERROR {e}")

if results:
    results.sort(key=lambda x: x["prob"], reverse=True)
    print(f"\nTop 5 by probability:")
    for r in results[:5]:
        print(f"  {r['symbol']}: prob={r['prob']:.3f} upside={r['upside']:.1f}% [{r['conf']}] ${r['price']:.2f}")
print(f"\nTotal analyzed: {len(results)}/{len(test_tickers)}")
