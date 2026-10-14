"""
Compare learning algorithms for both models, on the same data and split as ml_model.py.

Model 1 (delivery time) and model 2 (expected rating from the delay) are each trained with:
HistGradientBoosting (used in the app), XGBoost, CatBoost, RandomForest (the project's original
model 1) and LinearRegression, plus the predict-the-mean baseline. For model 2 the table also
says whether a later delivery can ever get a higher expected rating (unfair to couriers);
the unconstrained models fit better but break that rule, which is why the app uses the
monotonic HistGradientBoosting.

Run from the project root:  python scripts/compare_algorithms.py
Writes docs/algorithm_comparison.csv
"""
import os
import sys
import time

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ml_model  # noqa: E402
from Backend.trust_score import rating_features  # noqa: E402

OUT = os.path.join(ROOT, "docs", "algorithm_comparison.csv")


def scores(y_true, y_pred):
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "R2": float(r2_score(y_true, y_pred)),
    }


def one_hot_pipeline(X, regressor):
    numeric = X.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in X.columns if c not in numeric]
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), numeric),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), categorical),
    ])
    return Pipeline([("pre", pre), ("reg", regressor)])


class CatBoostNative:
    """CatBoost on the raw columns, with its own categorical handling (no one-hot)."""

    def __init__(self, **kw):
        self.kw = kw

    def fit(self, X, y):
        self.cat = [c for c in X.columns if X[c].dtype == object or str(X[c].dtype).startswith("str")]
        self.model = CatBoostRegressor(verbose=0, random_seed=42, allow_writing_files=False, **self.kw)
        self.model.fit(self._prep(X), y, cat_features=self.cat)
        return self

    def _prep(self, X):
        X = X.copy()
        for c in self.cat:  # CatBoost needs plain strings; missing becomes its own category
            X[c] = X[c].map(lambda v: "missing" if pd.isna(v) else str(v)).astype(object)
        return X

    def predict(self, X):
        return self.model.predict(self._prep(X))


def time_models(X):
    return {
        "HistGradientBoosting (app)": one_hot_pipeline(X, HistGradientBoostingRegressor(random_state=42)),
        "XGBoost": one_hot_pipeline(X, XGBRegressor(n_estimators=400, learning_rate=0.08, max_depth=6,
                                                    random_state=42, n_jobs=-1)),
        "CatBoost": CatBoostNative(iterations=600, learning_rate=0.1, depth=6),
        "RandomForest (original)": one_hot_pipeline(X, RandomForestRegressor(n_estimators=100, random_state=42,
                                                                            n_jobs=-1)),
        "LinearRegression": one_hot_pipeline(X, LinearRegression()),
    }


def rating_models():
    # Monotonic where supported: a later delivery never gets a higher expected rating
    return {
        "HistGradientBoosting (app)": HistGradientBoostingRegressor(monotonic_cst=[-1, -1], random_state=42),
        "XGBoost": XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=4,
                                monotone_constraints="(-1,-1)", random_state=42, n_jobs=-1),
        "CatBoost": CatBoostRegressor(iterations=400, learning_rate=0.05, depth=4, verbose=0, allow_writing_files=False,
                                      random_seed=42, monotone_constraints=[-1, -1]),
        "HistGradientBoosting, no constraint": HistGradientBoostingRegressor(random_state=42),
        "RandomForest (no constraint)": RandomForestRegressor(n_estimators=200, min_samples_leaf=20,
                                                              random_state=42, n_jobs=-1),
        "LinearRegression": LinearRegression(),
    }


def is_monotonic(model):
    """True if the expected rating never rises as the delivery gets later (predicted 25 min)."""
    grid = np.array([rating_features(25.0, a) for a in np.arange(8.0, 90.0, 0.5)])
    return bool(np.all(np.diff(model.predict(grid)) <= 1e-9))


def main():
    X, y = ml_model.load_data()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    X_test_app = X_test.assign(**ml_model.NOT_COLLECTED_IN_APP, **ml_model.COURIER_PROFILE_DEFAULTS)
    rows = []

    # ---- Model 1: delivery time (minutes)
    for name, model in time_models(X).items():
        t0 = time.time()
        model.fit(X_train, y_train)
        secs = time.time() - t0
        rows.append({"model": "1: delivery time (min)", "algorithm": name, "inputs": "all features",
                     **scores(y_test, model.predict(X_test)), "train_sec": secs})
        rows.append({"model": "1: delivery time (min)", "algorithm": name, "inputs": "app inputs",
                     **scores(y_test, model.predict(X_test_app)), "train_sec": secs})
        print(f"model 1  {name:28s} done ({secs:.1f}s)")
    rows.append({"model": "1: delivery time (min)", "algorithm": "Baseline (predict mean)", "inputs": "-",
                 **scores(y_test, np.full(len(y_test), y_train.mean())), "train_sec": 0.0})

    # ---- Model 2: expected rating from the delay against the app's yardstick (as in ml_model.py)
    oof = np.zeros(len(X_train))
    for tr, va in KFold(5, shuffle=True, random_state=42).split(X_train):
        fold = ml_model.build_model(X_train).fit(X_train.iloc[tr], y_train.iloc[tr])
        oof[va] = fold.predict(ml_model.yardstick_inputs(X_train.iloc[va]))
    yard = ml_model.build_model(X_train).fit(X_train, y_train)
    test_pred = yard.predict(ml_model.yardstick_inputs(X_test))
    F_train = np.array([rating_features(p, a) for p, a in zip(oof, y_train)])
    F_test = np.array([rating_features(p, a) for p, a in zip(test_pred, y_test)])
    r_train = X_train["Delivery_person_Ratings"].to_numpy()
    r_test = X_test["Delivery_person_Ratings"].to_numpy()
    for name, model in rating_models().items():
        t0 = time.time()
        model.fit(F_train, r_train)
        secs = time.time() - t0
        pred = np.clip(model.predict(F_test), 1, 5)
        rows.append({"model": "2: rating (stars)", "algorithm": name, "inputs": "delay features",
                     **scores(r_test, pred), "train_sec": secs, "later_never_scores_higher": is_monotonic(model)})
        print(f"model 2  {name:28s} done ({secs:.1f}s)")
    rows.append({"model": "2: rating (stars)", "algorithm": "Baseline (predict mean)", "inputs": "-",
                 **scores(r_test, np.full(len(r_test), r_train.mean())), "train_sec": 0.0})

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.round(4).to_csv(OUT, index=False)
    pd.set_option("display.width", 200)
    print()
    print(df.round({"MAE": 3, "RMSE": 3, "R2": 3, "train_sec": 1}).to_string(index=False))
    print(f"\nSaved {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
