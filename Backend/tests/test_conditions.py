from datetime import datetime, timezone
from unittest import mock

import pytest

from Backend.services import conditions
from Backend.services.conditions import estimate_traffic, get_weather, weather_category


@pytest.mark.parametrize("code,wind,expected", [
    (0, 5, "Sunny"),
    (1, 5, "Sunny"),
    (3, 5, "Cloudy"),
    (61, 5, "Cloudy"),    # light rain
    (45, 5, "Fog"),
    (0, 45, "Windy"),
    (95, 5, "Stormy"),    # thunderstorm
    (65, 50, "Stormy"),   # heavy rain beats wind
])
def test_weather_category(code, wind, expected):
    assert weather_category(code, wind) == expected


# Times in UTC; Israel is UTC+3 in October (summer time until late October).
@pytest.mark.parametrize("utc,expected", [
    (datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc), "Low"),      # 09:00 local
    (datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), "High"),    # 13:00 local
    (datetime(2026, 10, 13, 14, 30, tzinfo=timezone.utc), "Medium"), # 17:30 local
    (datetime(2026, 10, 13, 17, 0, tzinfo=timezone.utc), "Jam"),     # 20:00 local
    (datetime(2026, 10, 13, 21, 0, tzinfo=timezone.utc), "Low"),     # 00:00 local, night
])
def test_estimate_traffic(utc, expected):
    assert estimate_traffic(utc) == expected


FAKE_ANSWER = {"hourly": {
    "time": ["2026-10-13T09:00", "2026-10-13T10:00"],
    "weather_code": [0, 95],
    "wind_speed_10m": [10.0, 20.0],
}}


@pytest.fixture()
def weather_on(monkeypatch):
    monkeypatch.setenv("WEATHER_API_ENABLED", "1")
    conditions._weather_cache.clear()
    conditions._last_failure_at = -1e9
    yield
    conditions._weather_cache.clear()
    conditions._last_failure_at = -1e9


def _answer():
    resp = mock.Mock()
    resp.json.return_value = FAKE_ANSWER
    return resp


def test_get_weather_reads_the_right_hour(weather_on):
    with mock.patch.object(conditions.requests, "get", return_value=_answer()) as get:
        when = datetime(2026, 10, 13, 10, 20, tzinfo=timezone.utc)
        assert get_weather(32.07, 34.79, when) == "Stormy"
        assert get_weather(32.07, 34.79, when.replace(hour=9)) == "Sunny"
        assert get_weather(32.07, 34.79, when.replace(day=1)) is None  # not in the answer
    assert get.call_count == 1  # one call per place, then the cache


def test_get_weather_failure_returns_none_and_backs_off(weather_on):
    when = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
    with mock.patch.object(conditions.requests, "get", side_effect=OSError("no network")) as get:
        assert get_weather(32.07, 34.79, when) is None
        assert get_weather(31.77, 35.21, when) is None  # another place: no new call during backoff
    assert get.call_count == 1


def test_get_weather_disabled_makes_no_call():
    with mock.patch.object(conditions.requests, "get") as get:
        assert get_weather(32.07, 34.79, datetime(2026, 10, 13, 10, tzinfo=timezone.utc)) is None
    get.assert_not_called()
