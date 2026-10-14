# app/services/geocoding.py
from __future__ import annotations
from typing import List, Optional, Tuple
import os
import re
import logging

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderInsufficientPrivileges, GeocoderServiceError

log = logging.getLogger("geocoding")

# --------------------------- Config ---------------------------


USER_AGENT = os.getenv(
    "GEOCODE_USER_AGENT")

DEFAULT_COUNTRYCODES = os.getenv("GEOCODE_COUNTRYCODES", "il")
DEFAULT_LANGUAGE = os.getenv("GEOCODE_LANGUAGE", "he")

log.info("Nominatim USER_AGENT=%s", USER_AGENT)

#_geocoder = Nominatim(user_agent=USER_AGENT, timeout=5)
_geocoder = Nominatim(user_agent="auction-based-crowd-shipping", timeout=5)
_geocode = RateLimiter(
    _geocoder.geocode,
    min_delay_seconds=1.1,
    max_retries=1,
    swallow_exceptions=False 
)

# --------------------------- Public API ---------------------------

def _candidates(address: str) -> List[str]:
    """
    Queries to try, from exact to approximate: the full address, the address without
    house numbers (OpenStreetMap often lacks Hebrew house numbers), then the city alone
    (the last comma-separated part).
    """
    full = " ".join(address.split())
    no_numbers = " ".join(re.sub(r"\d+[א-תA-Za-z]?", " ", full).split())
    no_numbers = re.sub(r"\s+,", ",", no_numbers).strip(" ,")
    parts = [p.strip() for p in full.split(",") if p.strip()]
    city = parts[-1] if len(parts) > 1 else ""

    out: List[str] = []
    for q in (full, no_numbers, city):
        if q and q not in out:
            out.append(q)
    return out


def _geocode_one(query: str, countrycodes, language) -> Optional[Tuple[float, float]]:
    try:
        loc = _geocode(
            query=query,
            language=language,
            country_codes=countrycodes,
            addressdetails=False,
        )
    except GeocoderInsufficientPrivileges as e:
        log.error("geocode: InsufficientPrivileges (403) for %r: %s", query, e)
        return None
    except GeocoderServiceError as e:
        log.warning("geocode: service error for %r: %s", query, e)
        return None
    except Exception as e:
        log.warning("geocode: unexpected error for %r: %s", query, e)
        return None
    if not loc:
        return None
    return float(loc.latitude), float(loc.longitude)


def geocode_address(
    address: str,
    countrycodes: Optional[str] = DEFAULT_COUNTRYCODES,
    language: Optional[str] = DEFAULT_LANGUAGE,
) -> Optional[Tuple[float, float]]:
    """
    Geocode an address. Returns (lat, lon), or None if nothing matched.
    If the full address is not found, falls back to the street without house number,
    then to the city (approximate location). Never raises.
    """
    if not address or not address.strip():
        return None

    candidates = _candidates(address)
    for i, query in enumerate(candidates):
        result = _geocode_one(query, countrycodes, language)
        if result:
            if i > 0:
                log.warning("geocode: %r not found, using approximate match %r", address, query)
            return result

    log.warning("geocode: no result for %r (tried %s)", address, candidates)
    return None
