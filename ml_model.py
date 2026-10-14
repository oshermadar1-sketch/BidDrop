"""
Train the delivery-time prediction model.

Data:   Zomato_Final_Preprocessed.csv (real historical deliveries, created by preprocess.py)
Target: Time_taken (min)
Output: Backend/delivery_time_model.pkl  (model 1: delivery time in minutes)
        Backend/rating_model.pkl         (model 2: customer rating expected from how a delivery went)
        Backend/ml_metrics.json          (test-set metrics, written for the project report)

Model 2 learns, from the courier ratings in the same data, how customers rate a delivery
given how late or early it was compared with model 1's prediction. It scores every courier
delivery in the app and is the ML part of the trust score (Backend/trust_score.py).

Run from the project root:
    python ml_model.py
"""
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from Backend.trust_score import RATING_FEATURES, rating_features

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "Zomato_Final_Preprocessed.csv")
MODEL_PATH = os.path.join(ROOT, "Backend", "delivery_time_model.pkl")
RATING_MODEL_PATH = os.path.join(ROOT, "Backend", "rating_model.pkl")
METRICS_PATH = os.path.join(ROOT, "Backend", "ml_metrics.json")

# Must match FEATURE_COLUMNS in Backend/ml_predictor.py
FEATURE_COLUMNS = [
    "Delivery_person_Age",
    "Delivery_person_Ratings",
    "Weather_conditions",
    "Road_traffic_density",
    "Vehicle_condition",
    "Type_of_order",
    "Type_of_vehicle",
    "multiple_deliveries",
    "Festival",
    "City",
    "Distance_km",
    "Order_DayOfWeek",
]
TARGET = "Time_taken (min)"

# Features the app never collects: in the app they get these defaults
# (same values as DEFAULT_FEATURES in Backend/ml_predictor.py). Used for the realistic evaluation.
NOT_COLLECTED_IN_APP = {
    "multiple_deliveries": 1.0,
    "Festival": "No",
    "City": "Metropolitian",
    "Type_of_order": "Snack",
}
# Courier profile: known when the courier filled in age and vehicle, otherwise these defaults.
COURIER_PROFILE_DEFAULTS = {
    "Delivery_person_Age": 30.0,
    "Vehicle_condition": 1,
    "Type_of_vehicle": "motorcycle",
}


def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=[TARGET]).copy()
    df["Order_Date"] = pd.to_datetime(df["Order_Date"], errors="coerce")
    df["Order_DayOfWeek"] = df["Order_Date"].dt.day_name()
    return df[FEATURE_COLUMNS], df[TARGET]


def build_model(X):
    numeric_features = X.select_dtypes(include="number").columns.tolist()
    categorical_features = [c for c in X.columns if c not in numeric_features]

    preprocessor = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), numeric_features),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), categorical_features),
    ])

    return Pipeline([
        ("preprocessor", preprocessor),
        ("regressor", HistGradientBoostingRegressor(random_state=42)),
    ])


def yardstick_inputs(X):
    """
    Inputs of the courier-neutral prediction the app judges deliveries against
    (features_for_request without courier details): typical courier, app defaults.
    """
    return X.assign(Delivery_person_Ratings=4.7, **NOT_COLLECTED_IN_APP, **COURIER_PROFILE_DEFAULTS)


def rating_metrics(y_true, y_pred):
    return {
        "MAE_stars": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "R2": round(float(r2_score(y_true, y_pred)), 4),
    }


def train_rating_model(X_train, y_train, X_test, y_test, time_model):
    """
    Model 2. Features: delay (actual - predicted minutes) and actual / predicted, where the
    prediction is the app's courier-neutral yardstick. On the training rows the prediction is
    out-of-fold (5 folds), so the rating model never sees predictions of rows the time model
    trained on. Label: the courier rating in the data. Returns (model, report, test predictions).
    """
    oof = np.zeros(len(X_train))
    for tr, va in KFold(5, shuffle=True, random_state=42).split(X_train):
        fold_model = build_model(X_train).fit(X_train.iloc[tr], y_train.iloc[tr])
        oof[va] = fold_model.predict(yardstick_inputs(X_train.iloc[va]))
    test_pred = time_model.predict(yardstick_inputs(X_test))

    F_train = np.array([rating_features(p, a) for p, a in zip(oof, y_train)])
    F_test = np.array([rating_features(p, a) for p, a in zip(test_pred, y_test)])
    r_train = X_train["Delivery_person_Ratings"].to_numpy()
    r_test = X_test["Delivery_person_Ratings"].to_numpy()

    # Monotonic: a later delivery can never earn a higher expected rating
    rating_model = HistGradientBoostingRegressor(monotonic_cst=[-1, -1], random_state=42)
    rating_model.fit(F_train, r_train)
    pred = np.clip(rating_model.predict(F_test), 1, 5)

    linear = LinearRegression().fit(F_train, r_train)
    report = {
        "model": "HistGradientBoostingRegressor (monotonic: later -> lower)",
        "features": RATING_FEATURES,
        "label": "Delivery_person_Ratings (courier rating, 1..5)",
        "test_metrics": rating_metrics(r_test, pred),
        "linear_regression": rating_metrics(r_test, linear.predict(F_test)),
        "baseline_predict_mean": rating_metrics(r_test, np.full(len(r_test), r_train.mean())),
    }
    return rating_model, report, pred


def metrics(y_true, y_pred):
    return {
        "MAE_min": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "RMSE_min": round(float(mean_squared_error(y_true, y_pred) ** 0.5), 2),
        "R2": round(float(r2_score(y_true, y_pred)), 4),
    }


def main():
    X, y = load_data()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = build_model(X)
    model.fit(X_train, y_train)

    model_scores = metrics(y_test, model.predict(X_test))
    # Baseline: always predict the average training time. The model must beat this.
    baseline_scores = metrics(y_test, np.full(len(y_test), y_train.mean()))
    # Realistic: only the inputs the app really has (distance, day, weather, hour-based traffic,
    # courier rating, and the courier profile if filled in); the rest replaced by the app's defaults.
    X_test_profile = X_test.assign(**NOT_COLLECTED_IN_APP)
    X_test_app = X_test_profile.assign(**COURIER_PROFILE_DEFAULTS)
    app_scores = metrics(y_test, model.predict(X_test_app))
    profile_scores = metrics(y_test, model.predict(X_test_profile))

    joblib.dump(model, MODEL_PATH, compress=3)

    rating_model, rating_report, test_rating_pred = train_rating_model(
        X_train, y_train, X_test, y_test, model
    )
    joblib.dump(rating_model, RATING_MODEL_PATH, compress=3)

    # Starting values for a new courier's trust score (Backend/trust_score.py):
    # model 2's average score for deliveries it did not train on = a typical courier.
    trust_priors = {
        "global_mean_rating": round(float(X["Delivery_person_Ratings"].mean()), 2),
        "typical_model_score": round(float(np.mean(test_rating_pred)), 2),
    }

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": os.path.basename(DATA_PATH),
        "rows_total": int(len(X)),
        "rows_train": int(len(X_train)),
        "rows_test": int(len(X_test)),
        "split": "random 80/20, random_state=42",
        "model": "HistGradientBoostingRegressor",
        "sklearn_version": sklearn.__version__,
        "features": FEATURE_COLUMNS,
        "test_metrics": model_scores,
        "test_metrics_app_inputs": app_scores,
        "test_metrics_app_inputs_with_courier_profile": profile_scores,
        "app_inputs_note": (
            "features never collected by the app set to defaults: " + ", ".join(NOT_COLLECTED_IN_APP)
            + "; without courier profile also: " + ", ".join(COURIER_PROFILE_DEFAULTS)
        ),
        "baseline_predict_mean": baseline_scores,
        "rating_model": rating_report,
        "trust_priors": trust_priors,
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("Model training complete")
    print(f"Saved models:  {MODEL_PATH}, {RATING_MODEL_PATH}")
    print(f"Saved metrics: {METRICS_PATH}")
    print(f"Test set ({len(X_test)} deliveries):")
    print(f"  Model     MAE={model_scores['MAE_min']} min  RMSE={model_scores['RMSE_min']} min  R2={model_scores['R2']}")
    print(f"  App inputs MAE={app_scores['MAE_min']} min  RMSE={app_scores['RMSE_min']} min  R2={app_scores['R2']}")
    print(f"  + courier profile MAE={profile_scores['MAE_min']} min  RMSE={profile_scores['RMSE_min']} min  R2={profile_scores['R2']}")
    print(f"  Baseline  MAE={baseline_scores['MAE_min']} min  RMSE={baseline_scores['RMSE_min']} min  R2={baseline_scores['R2']}")
    rm = rating_report
    print(f"Rating model (model 2), test set:")
    print(f"  Model     MAE={rm['test_metrics']['MAE_stars']} stars  R2={rm['test_metrics']['R2']}")
    print(f"  Linear    MAE={rm['linear_regression']['MAE_stars']} stars  R2={rm['linear_regression']['R2']}")
    print(f"  Baseline  MAE={rm['baseline_predict_mean']['MAE_stars']} stars  R2={rm['baseline_predict_mean']['R2']}")
    print(f"Trust priors:  {trust_priors}")


if __name__ == "__main__":
    main()
