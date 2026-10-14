from types import SimpleNamespace
from unittest import mock

from Backend.services import geocoding
from Backend.services.geocoding import _candidates, geocode_address


def test_candidates_go_from_exact_to_city():
    assert _candidates("בן גוריון 10, תל אביב") == [
        "בן גוריון 10, תל אביב",
        "בן גוריון, תל אביב",
        "תל אביב",
    ]
    assert _candidates("הרצל 5א, חולון")[1] == "הרצל, חולון"
    assert _candidates("ירושלים") == ["ירושלים"]


def _fake(found):
    """A geocoder that only knows the queries in `found`."""
    def geocode(query, **_):
        if query in found:
            return SimpleNamespace(latitude=found[query][0], longitude=found[query][1])
        return None
    return geocode


def test_exact_address_found():
    with mock.patch.object(geocoding, "_geocode", _fake({"בן גוריון 10, תל אביב": (32.08, 34.78)})):
        assert geocode_address("בן גוריון 10, תל אביב") == (32.08, 34.78)


def test_falls_back_to_street_then_city():
    with mock.patch.object(geocoding, "_geocode", _fake({"בן גוריון, תל אביב": (32.08, 34.78)})):
        assert geocode_address("בן גוריון 999, תל אביב") == (32.08, 34.78)
    with mock.patch.object(geocoding, "_geocode", _fake({"תל אביב": (32.07, 34.79)})):
        assert geocode_address("רחוב שלא קיים 3, תל אביב") == (32.07, 34.79)


def test_nothing_found_returns_none():
    with mock.patch.object(geocoding, "_geocode", _fake({})):
        assert geocode_address("blabla") is None


def test_service_error_does_not_raise():
    def boom(**_):
        raise geocoding.GeocoderServiceError("down")
    with mock.patch.object(geocoding, "_geocode", boom):
        assert geocode_address("הרצל 1, חיפה") is None
