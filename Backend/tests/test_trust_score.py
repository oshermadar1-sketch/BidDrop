import pytest

from Backend.trust_score import (
    CUSTOMER_WEIGHT_MAX,
    PRIORS,
    calculate_trust_score,
    customer_weight,
    model_part,
    rating_features,
)


def test_rating_features():
    assert rating_features(25, 30) == [5.0, 1.2]
    assert rating_features(25, 20)[0] == -5.0  # early = negative delay


def test_customer_weight_ramps_then_stops_at_70_percent():
    assert customer_weight(0) == 0
    assert customer_weight(10) == pytest.approx(0.35)
    assert customer_weight(20) == pytest.approx(0.7)
    assert customer_weight(400) == pytest.approx(CUSTOMER_WEIGHT_MAX)


def test_new_courier_starts_at_typical_courier():
    t = calculate_trust_score()
    assert t["trust_score"] == pytest.approx(PRIORS["typical_model_score"], abs=0.01)
    assert t["customer_weight"] == 0
    assert t["model_weight"] == 1
    assert t["is_new_courier"]


def test_one_five_star_rating_does_not_beat_a_proven_veteran():
    # Model scores are realistic model-2 outputs (on time ~4.7, a bit late ~4.6)
    newbie = calculate_trust_score(avg_rating=5, num_ratings=1, delivery_scores=[4.7])
    veteran = calculate_trust_score(avg_rating=4.8, num_ratings=100, delivery_scores=[4.6] * 100)
    assert veteran["trust_score"] > newbie["trust_score"]


def test_newbie_who_keeps_getting_five_stars_overtakes_veteran():
    newbie = calculate_trust_score(avg_rating=5, num_ratings=30, delivery_scores=[4.7] * 30)
    veteran = calculate_trust_score(avg_rating=4.8, num_ratings=100, delivery_scores=[4.6] * 100)
    assert newbie["trust_score"] > veteran["trust_score"]


def test_veteran_score_is_70_customers_30_model():
    t = calculate_trust_score(avg_rating=4.0, num_ratings=400, delivery_scores=[5] * 400)
    expected = 0.7 * 4.0 + 0.3 * model_part([5] * 400)
    assert t["trust_score"] == pytest.approx(expected, abs=0.01)
    assert not t["is_new_courier"]


def test_courier_with_low_model_scores_scores_lower():
    late = calculate_trust_score(avg_rating=4.5, num_ratings=20, delivery_scores=[1] * 20)
    punctual = calculate_trust_score(avg_rating=4.5, num_ratings=20, delivery_scores=[5] * 20)
    assert punctual["trust_score"] > late["trust_score"]


def test_score_stays_in_range():
    for t in (calculate_trust_score(1, 400, [1] * 400), calculate_trust_score(5, 400, [5] * 400)):
        assert 1 <= t["trust_score"] <= 5
        assert 20 <= t["trust_percent"] <= 100
