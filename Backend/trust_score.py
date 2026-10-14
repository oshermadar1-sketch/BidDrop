"""
Courier trust score (1..5, also given as 0..100%).

    trust = w * customer_part + (1 - w) * model_part

customer_part  average of the courier's customer ratings (1..5).
model_part     machine-learning score of the courier's deliveries. After each delivery, model 2
               (Backend/rating_model.pkl, trained in ml_model.py) predicts the rating customers
               give for a delivery that took this long compared with model 1's predicted time for
               that route, weather and hour. The courier's model_part is the average of these
               scores, blended with MODEL_CUSHION deliveries of a typical courier, so a new
               courier starts at the typical score and each real delivery moves it.
w              customer weight. 0 for a new courier (no ratings yet), grows linearly with the
               number of ratings and stops at CUSTOMER_WEIGHT_MAX after RAMP_RATINGS ratings,
               so from then on the score is 70% customers / 30% model.

Kept free of database and model imports so the math can be unit-tested on its own.
"""
import json
import os

CUSTOMER_WEIGHT_MAX = 0.7
RAMP_RATINGS = 20
MODEL_CUSHION = 5

# Inputs of model 2 (the rating model); built by rating_features()
RATING_FEATURES = ["delay_min", "actual_over_predicted"]

_METRICS_PATH = os.path.join(os.path.dirname(__file__), "ml_metrics.json")


def _load_priors():
    """Typical-courier values computed by ml_model.py from the Zomato data."""
    defaults = {"global_mean_rating": 4.63, "typical_model_score": 4.63}
    try:
        with open(_METRICS_PATH, encoding="utf-8") as f:
            priors = json.load(f).get("trust_priors", {})
        return {k: float(priors.get(k, v)) for k, v in defaults.items()}
    except (OSError, ValueError):
        return defaults


PRIORS = _load_priors()


def rating_features(predicted_min, actual_min):
    """Model 2 inputs for one delivery: minutes late (negative = early) and actual / predicted."""
    predicted_min, actual_min = float(predicted_min), float(actual_min)
    return [actual_min - predicted_min, actual_min / predicted_min if predicted_min > 0 else 1.0]


def customer_weight(num_ratings):
    n = max(0, int(num_ratings or 0))
    return CUSTOMER_WEIGHT_MAX * min(n, RAMP_RATINGS) / RAMP_RATINGS


def model_part(scores, prior=None):
    """Average model-2 score of the courier's deliveries, blended with MODEL_CUSHION typical ones."""
    prior = PRIORS["typical_model_score"] if prior is None else float(prior)
    scores = list(scores or [])
    return (MODEL_CUSHION * prior + sum(scores)) / (MODEL_CUSHION + len(scores))


def calculate_trust_score(avg_rating=None, num_ratings=0, delivery_scores=None):
    """
    avg_rating       average customer rating (1..5) or None
    num_ratings      how many customer ratings it is based on
    delivery_scores  model-2 scores (1..5) of the courier's completed, timed deliveries
    """
    w = customer_weight(num_ratings) if avg_rating is not None else 0.0
    customer = float(avg_rating) if avg_rating is not None else PRIORS["global_mean_rating"]
    model = model_part(delivery_scores)

    score = min(max(w * customer + (1 - w) * model, 1.0), 5.0)
    return {
        "trust_score": round(score, 2),
        "trust_percent": round(score / 5 * 100),
        "customer_weight": round(w, 2),
        "model_weight": round(1 - w, 2),
        "customer_part": round(customer, 2),
        "model_part": round(model, 2),
        "num_ratings": int(num_ratings or 0),
        "num_timed_deliveries": len(delivery_scores or []),
        "is_new_courier": int(num_ratings or 0) < RAMP_RATINGS,
    }
