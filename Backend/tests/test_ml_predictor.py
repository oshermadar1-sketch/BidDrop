from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from Backend.ml_predictor import (
    DEFAULT_FEATURES,
    build_features,
    features_for_request,
    haversine_km,
    predict_delivery_time,
)

# Tel Aviv (Azrieli) -> Ramat Gan (Bursa), about 3 km
REQ = SimpleNamespace(
    from_lat=32.0745, from_lon=34.7917, to_lat=32.0838, to_lon=34.8013,
    window_start=datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc),  # a Tuesday
)


def test_haversine_known_distance():
    # Tel Aviv -> Jerusalem is about 54 km in a straight line
    assert haversine_km(32.0853, 34.7818, 31.7683, 35.2137) == pytest.approx(54, abs=2)


def test_invalid_category_is_rejected():
    with pytest.raises(ValueError):
        build_features(Weather_conditions="Clear")  # not a value the model was trained on
    with pytest.raises(ValueError):
        build_features(Type_of_vehicle="Bike")


def test_unknown_feature_is_rejected():
    with pytest.raises(ValueError):
        build_features(Speed=10)


def test_none_keeps_default():
    assert build_features(Distance_km=None)["Distance_km"] == DEFAULT_FEATURES["Distance_km"]


def test_features_from_request():
    f = features_for_request(REQ, courier_rating=4.9)
    assert f["Distance_km"] == pytest.approx(1.35, abs=0.1)
    assert f["Order_DayOfWeek"] == "Tuesday"
    assert f["Road_traffic_density"] == "High"  # 13:00 Israel time
    assert f["Delivery_person_Ratings"] == 4.9


def test_courier_start_point_adds_distance():
    near = features_for_request(REQ)
    far = features_for_request(REQ, courier_lat=32.1663, courier_lon=34.8436)  # Herzliya
    assert far["Distance_km"] > near["Distance_km"] + 5


def test_prediction_is_plausible_and_longer_for_far_trips():
    short = predict_delivery_time(build_features(Distance_km=2))
    long = predict_delivery_time(build_features(Distance_km=20))
    assert 5 < short < 60 and 5 < long < 60
    assert long > short


def test_courier_profile_feeds_the_model():
    from Backend.ml_predictor import courier_features

    young_good = SimpleNamespace(age=22, vehicle_type="electric_scooter", vehicle_condition=2)
    old_poor = SimpleNamespace(age=38, vehicle_type="motorcycle", vehicle_condition=0)
    assert courier_features(young_good) == {
        "Delivery_person_Age": 22.0, "Type_of_vehicle": "electric_scooter", "Vehicle_condition": 2,
    }
    fast = predict_delivery_time(features_for_request(REQ, courier=young_good))
    slow = predict_delivery_time(features_for_request(REQ, courier=old_poor))
    assert slow > fast


def test_incomplete_or_invalid_profile_uses_defaults():
    from Backend.ml_predictor import courier_features

    assert courier_features(None) == {}
    assert courier_features(SimpleNamespace(age=None, vehicle_type=None, vehicle_condition=None)) == {}
    assert courier_features(SimpleNamespace(age=90, vehicle_type="truck", vehicle_condition=7)) == {}


def test_rating_model_gives_lower_rating_for_later_delivery():
    from Backend.ml_predictor import predict_delivery_rating

    on_time = predict_delivery_rating(25, 25)
    late = predict_delivery_rating(25, 45)
    very_late = predict_delivery_rating(25, 70)
    assert 1 <= very_late <= late < on_time <= 5

