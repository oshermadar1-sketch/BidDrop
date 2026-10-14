import math
import os
from datetime import datetime, timezone

import joblib
import pandas as pd

from .services.conditions import estimate_traffic, get_weather
from .trust_score import rating_features

MODEL_PATH = os.path.join(os.path.dirname(__file__), "delivery_time_model.pkl")
RATING_MODEL_PATH = os.path.join(os.path.dirname(__file__), "rating_model.pkl")

# Model 1: delivery time in minutes. Model 2: expected customer rating of a delivery
# from how late/early it was against model 1 (both trained in ml_model.py).
model = joblib.load(MODEL_PATH)
rating_model = joblib.load(RATING_MODEL_PATH)

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

# Values the model was trained on (Zomato_Final_Preprocessed.csv).
# A value outside these lists is silently ignored by the model, so inputs are checked against them.
ALLOWED_VALUES = {
    "Weather_conditions": {"Sunny", "Cloudy", "Fog", "Windy", "Stormy", "Sandstorms"},
    "Road_traffic_density": {"Low", "Medium", "High", "Jam"},
    "Type_of_order": {"Snack", "Drinks", "Meal", "Buffet"},
    "Type_of_vehicle": {"motorcycle", "scooter", "electric_scooter"},
    "Festival": {"No", "Yes"},
    "City": {"Metropolitian", "Urban", "Semi-Urban"},  # "Metropolitian" is the dataset's spelling
    "Order_DayOfWeek": {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"},
}

# Used when the app has no real value for a feature (a courier who did not fill in age and
# vehicle; weather when the weather service is unavailable). Numbers are the medians and
# categories the most common values in the training data, so a missing value pulls the
# prediction toward a typical delivery.
DEFAULT_FEATURES = {
    "Delivery_person_Age": 30.0,
    "Delivery_person_Ratings": 4.7,
    "Weather_conditions": "Fog",
    "Road_traffic_density": "Low",
    "Vehicle_condition": 1,
    "Type_of_order": "Snack",
    "Type_of_vehicle": "motorcycle",
    "multiple_deliveries": 1.0,
    "Festival": "No",
    "City": "Metropolitian",
    "Distance_km": 9.3,
    "Order_DayOfWeek": "Wednesday",
}


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between two points (same formula as preprocess.py)."""
    lat1, lon1, lat2, lon2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def build_features(**known):
    """
    Return a full feature dict: DEFAULT_FEATURES overridden by the known values.
    None values are ignored (the default stays). Unknown names or invalid categories raise ValueError.
    """
    features = dict(DEFAULT_FEATURES)
    for name, value in known.items():
        if name not in features:
            raise ValueError(f"Unknown feature: {name}")
        if value is None:
            continue
        if name in ALLOWED_VALUES and value not in ALLOWED_VALUES[name]:
            raise ValueError(f"Invalid value for {name}: {value!r}")
        features[name] = value
    return features


def courier_features(courier) -> dict:
    """
    Model inputs from a courier's profile (Users row: age, vehicle_type, vehicle_condition).
    Missing or out-of-training-range values are left out, so the defaults are used.
    """
    if courier is None:
        return {}
    out = {}
    age = getattr(courier, "age", None)
    if age is not None and 16 <= int(age) <= 65:  # age range of the training data
        out["Delivery_person_Age"] = float(age)
    vehicle = getattr(courier, "vehicle_type", None)
    if vehicle in ALLOWED_VALUES["Type_of_vehicle"]:
        out["Type_of_vehicle"] = vehicle
    condition = getattr(courier, "vehicle_condition", None)
    if condition in (0, 1, 2):
        out["Vehicle_condition"] = int(condition)
    return out


def features_for_request(req, courier_rating=None, courier_lat=None, courier_lon=None,
                         when=None, courier=None):
    """
    Build model inputs from a Request row:
    - distance from its coordinates (plus courier start point -> pickup, if known)
    - day of week, weather (Open-Meteo, real) and traffic (estimated) at `when`
      (default: the request's window start, else now)
    - age, vehicle type and condition from the courier's profile, if given
    Everything else the app does not collect falls back to DEFAULT_FEATURES.
    """
    distance = None
    pickup = (getattr(req, "from_lat", None), getattr(req, "from_lon", None))
    dropoff = (getattr(req, "to_lat", None), getattr(req, "to_lon", None))
    if None not in pickup and None not in dropoff:
        distance = haversine_km(*pickup, *dropoff)
        if courier_lat is not None and courier_lon is not None:
            distance += haversine_km(courier_lat, courier_lon, *pickup)

    if when is None:
        when = getattr(req, "window_start", None)
    if not isinstance(when, datetime):
        when = datetime.now(timezone.utc)

    rating = float(courier_rating) if courier_rating is not None else None

    return build_features(
        Distance_km=distance,
        Order_DayOfWeek=when.strftime("%A"),
        Weather_conditions=get_weather(*pickup, when),
        Road_traffic_density=estimate_traffic(when),
        Delivery_person_Ratings=rating,
        **courier_features(courier),
    )


def predict_delivery_time(features):
    """
    Predict delivery time in minutes.
    `features` is a dict (preferably from build_features) or a list in FEATURE_COLUMNS order.
    """
    if isinstance(features, dict):
        row = [features[c] for c in FEATURE_COLUMNS]
    else:
        row = list(features)
    features_df = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    return float(model.predict(features_df)[0])


def predict_delivery_rating(predicted_min, actual_min):
    """Model 2: the rating (1..5) customers are expected to give for this delivery time."""
    features = [rating_features(predicted_min, actual_min)]
    return float(min(max(rating_model.predict(features)[0], 1.0), 5.0))
