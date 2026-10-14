import pytest
from fastapi import HTTPException

from Backend.routes_users import validate_courier_profile


def test_valid_profile():
    assert validate_courier_profile({"age": "27", "vehicle_type": "scooter", "vehicle_condition": 2}) == {
        "age": 27, "vehicle_type": "scooter", "vehicle_condition": 2,
    }


@pytest.mark.parametrize("payload", [
    {"age": "abc", "vehicle_type": "scooter", "vehicle_condition": 1},
    {"age": 12, "vehicle_type": "scooter", "vehicle_condition": 1},
    {"age": 30, "vehicle_type": "truck", "vehicle_condition": 1},
    {"age": 30, "vehicle_type": "scooter", "vehicle_condition": 5},
    {"age": 30, "vehicle_type": "scooter"},
])
def test_invalid_profile_is_rejected(payload):
    with pytest.raises(HTTPException) as e:
        validate_courier_profile(payload)
    assert e.value.status_code == 400
