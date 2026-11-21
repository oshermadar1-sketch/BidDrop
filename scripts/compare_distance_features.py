"""
Does the delivery-time model get better with road distance instead of the straight line?

Trains the same model (ml_model.build_model) on the same 80/20 split with different
distance features and reports the test error in the three situations ml_model.py reports:
all features, what the app collects with a courier profile, and without a profile.
Also a 5-fold cross-validation MAE on the full data, to make sure the split is not lucky.

Needs Zomato_Final_Preprocessed.csv with the Road_* columns (preprocess.py after
scripts/road_distances.py).

Run from the project root:
    python scripts/compare_distance_features.py
Writes docs/distance_feature_comparison.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ml_model as mm  # noqa: E402

OUT = os.path.join(ROOT, "docs", "distance_feature_comparison.json")

BASE = [c for c in mm.FEATURE_COLUMNS if c != "Distance_km"]
VARIANTS = {
    "air distance (current)": BASE + ["Distance_km"],
    "road distance": BASE + ["Road_Distance_km"],
    "road distance + driving time": BASE + ["Road_Distance_km", "Road_Duration_min"],
    "air + road distance": BASE + ["Distance_km", "Road_Distance_km"],
}


def load():
    df = pd.read_csv(mm.DATA_PATH).dropna(subset=[mm.TARGET]).copy()
    df["Order_Date"] = pd.to_datetime(df["Order_Date"], errors="coerce")
    df["Order_DayOfWeek"] = df["Order_Date"].dt.day_name()
    return df


def evaluate(df, cols):
    X, y = df[cols], df[mm.TARGET]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = mm.build_model(X)
    model.fit(X_train, y_train)
    X_profile = X_test.assign(**mm.NOT_COLLECTED_IN_APP)
    X_app = X_profile.assign(**mm.COURIER_PROFILE_DEFAULTS)
    cv = []
    for tr, te in KFold(n_splits=5, shuffle=True, random_state=42).split(X):
        m = mm.build_model(X)
        m.fit(X.iloc[tr], y.iloc[tr])
        cv.append(float(np.mean(np.abs(m.predict(X.iloc[te]) - y.iloc[te]))))
    return {
        "features": cols,
        "test_all_features": mm.metrics(y_test, model.predict(X_test)),
        "test_app_with_profile": mm.metrics(y_test, model.predict(X_profile)),
        "test_app_without_profile": mm.metrics(y_test, model.predict(X_app)),
        "cv5_MAE_min": round(float(np.mean(cv)), 2),
        "cv5_MAE_std": round(float(np.std(cv)), 2),
    }


def main():
    df = load()
    report = {"rows": int(len(df)),
              "road_source_counts": df["Road_Source"].value_counts().to_dict(),
              "road_over_air_median_ratio": round(float((df["Road_Distance_km"] / df["Distance_km"]).median()), 3),
              "variants": {}}
    print(f"{'variant':32s} {'MAE all':>8s} {'MAE profile':>12s} {'MAE no-profile':>15s} {'CV5 MAE':>9s}")
    for name, cols in VARIANTS.items():
        r = evaluate(df, cols)
        report["variants"][name] = r
        print(f"{name:32s} {r['test_all_features']['MAE_min']:8.2f} "
              f"{r['test_app_with_profile']['MAE_min']:12.2f} "
              f"{r['test_app_without_profile']['MAE_min']:15.2f} "
              f"{r['cv5_MAE_min']:6.2f}±{r['cv5_MAE_std']:.2f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("written", OUT)


if __name__ == "__main__":
    main()
