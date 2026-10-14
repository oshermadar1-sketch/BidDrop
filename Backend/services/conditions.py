# services/conditions.py
# Road conditions for the delivery-time model: real weather from Open-Meteo, estimated traffic.
#
# Weather:  Open-Meteo (https://open-meteo.com), free, no API key. Hourly forecast for the
#           pickup point at the delivery hour, mapped to the categories of the training data.
#           One request per location covers the last 3 months and the next 2 weeks.
#           Any failure (no network, timeout, bad answer) returns None, so the model falls back
#           to its default value and matching never breaks because of the weather service.
# Traffic:  NOT measured. Estimated from the local hour with the training data's own hour rule.
#
# Set WEATHER_API_ENABLED=0 to turn the weather calls off (tests do this).
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

log = logging.getLogger("conditions")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SEC = 3
WINDY_KMH = 40  # wind at or above this counts as "Windy"

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Jerusalem"))
except Exception:  # Windows without the tzdata package
    LOCAL_TZ = timezone(timedelta(hours=2))

# One request per location covers PAST_DAYS back and FORECAST_DAYS ahead; kept for CACHE_TTL_SEC.
PAST_DAYS = 92
FORECAST_DAYS = 16
CACHE_TTL_SEC = 3600
# After a failure, no calls for this long, so a slow or blocked service never slows the app down.
FAILURE_BACKOFF_SEC = 60

_weather_cache: dict = {}   # (lat, lon) -> (fetched_at, {"YYYY-MM-DDTHH:00": (code, wind)})
_last_failure_at = 0.0


def _weather_enabled() -> bool:
    return os.getenv("WEATHER_API_ENABLED", "1") != "0"


def weather_category(weather_code: int, wind_kmh: float = 0.0) -> str:
    """
    Map an Open-Meteo WMO weather code to the training categories
    (Sunny, Cloudy, Fog, Windy, Stormy; the dataset's 'Sandstorms' has no WMO equivalent).
    """
    code = int(weather_code)
    if code >= 95 or code in (65, 67, 75, 82, 86):   # thunderstorm, heavy rain / snow / showers
        return "Stormy"
    if wind_kmh >= WINDY_KMH:
        return "Windy"
    if code in (45, 48):                              # fog
        return "Fog"
    if code >= 2:                                     # overcast, drizzle, light/moderate rain
        return "Cloudy"
    return "Sunny"                                    # clear / mainly clear


def _fetch_hourly(lat: float, lon: float) -> Optional[dict]:
    """Hourly weather around (lat, lon) for the last PAST_DAYS and next FORECAST_DAYS, or None."""
    global _last_failure_at
    key = (round(float(lat), 1), round(float(lon), 1))
    now = time.monotonic()

    cached = _weather_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SEC:
        return cached[1]
    if now - _last_failure_at < FAILURE_BACKOFF_SEC:
        return None

    try:
        resp = requests.get(OPEN_METEO_URL, params={
            "latitude": key[0],
            "longitude": key[1],
            "hourly": "weather_code,wind_speed_10m",
            "past_days": PAST_DAYS,
            "forecast_days": FORECAST_DAYS,
            "timezone": "GMT",
        }, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        h = resp.json()["hourly"]
        by_hour = {t: (c, w) for t, c, w in zip(h["time"], h["weather_code"], h["wind_speed_10m"])}
    except Exception as e:
        _last_failure_at = now
        log.warning("Weather lookup failed, using model default (retry in %ss): %s",
                    FAILURE_BACKOFF_SEC, e)
        return None

    _weather_cache[key] = (now, by_hour)
    return by_hour


def get_weather(lat, lon, when: datetime) -> Optional[str]:
    """Weather category at (lat, lon) for the hour of `when`, or None if unavailable."""
    if not _weather_enabled() or lat is None or lon is None or when is None:
        return None
    by_hour = _fetch_hourly(lat, lon)
    if not by_hour:
        return None

    when_utc = (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    hit = by_hour.get(when_utc.strftime("%Y-%m-%dT%H:00"))
    if not hit or hit[0] is None:
        return None  # outside the fetched range, or no data for that hour
    return weather_category(hit[0], hit[1] or 0.0)


def estimate_traffic(when: datetime) -> str:
    """
    Traffic category from the local hour, using the same hour -> category pattern as the
    training data. In the Zomato data, Road_traffic_density is fully determined by the order
    hour (08-10 Low, 11-14 High, 15-18 Medium, 19-21 Jam, 22-23 Low), so this is the input the
    model actually learned. Hours missing from the data (00-07) count as Low (night).
    """
    local = (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(LOCAL_TZ)
    hour = local.hour
    if 11 <= hour <= 14:
        return "High"
    if 15 <= hour <= 18:
        return "Medium"
    if 19 <= hour <= 21:
        return "Jam"
    return "Low"
