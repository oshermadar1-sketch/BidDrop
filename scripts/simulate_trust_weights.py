"""
SIMULATION (synthetic couriers, not real data): which customer/model weight in the trust score
best identifies good couriers?

Each simulated courier has two hidden traits:
  lateness  - average minutes later than the predicted time (some couriers are always late)
  niceness  - how pleasant they are (what customers mostly rate)
Per delivery: the delay = lateness + noise; only RATED_SHARE of customers leave a 1..5 rating,
driven mostly by niceness and only a little by the delay (customers do not know the expected
time); the delivery always gets a model-2 score from the REAL rating model (Backend/rating_model.pkl).

For every customer-weight cap (the 70% in 70/30) we compute the trust score exactly like the app
(Backend/trust_score.py) after K deliveries and measure, with Spearman rank correlation, how well
it ranks couriers by their hidden quality. Hidden quality = PUNCTUALITY_SHARE * punctuality +
(1 - PUNCTUALITY_SHARE) * niceness (standardized), for several shares, because the best weight
depends on how much the platform cares about punctuality vs. pleasantness.

Run from the project root:  python scripts/simulate_trust_weights.py
Writes docs/trust_weight_simulation.csv and the charts docs/trust_weight_simulation.png
(English) and docs/trust_weight_simulation_he.png (Hebrew). Redraw only: --charts-only
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("WEATHER_API_ENABLED", "0")

import joblib  # noqa: E402

import Backend.trust_score as ts  # noqa: E402
from Backend.trust_score import calculate_trust_score, rating_features  # noqa: E402

RATING_MODEL = joblib.load(os.path.join(ROOT, "Backend", "rating_model.pkl"))
OUT_DIR = os.path.join(ROOT, "docs")

N_COURIERS = 200
SEEDS = range(20)
DELIVERIES = [5, 20, 60]            # evaluate after this many deliveries per courier
WEIGHT_CAPS = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
PUNCTUALITY_SHARES = [0.25, 0.5, 0.75]
RATED_SHARE = 0.3                   # share of deliveries that get a customer rating
PREDICTED_MIN = 25.0                # typical predicted time (minutes)
LATENESS_SD = 6.0                   # spread of couriers' average lateness (minutes)
DELAY_NOISE_SD = 6.0                # delivery-to-delivery noise (model 1 errs ~4.5 min on average)


def make_couriers(rng):
    return pd.DataFrame({
        "lateness": rng.normal(0, LATENESS_SD, N_COURIERS),
        "niceness": rng.normal(0, 1, N_COURIERS),
    })


def simulate_deliveries(rng, couriers, k):
    """Per courier: k delays, the customer ratings that were given, and the model-2 scores."""
    rows = []
    for c in couriers.itertuples():
        delays = c.lateness + rng.normal(0, DELAY_NOISE_SD, k)
        rated = rng.random(k) < RATED_SHARE
        # Customers: mostly niceness, a little lateness, lots of noise; integer stars 1..5
        latent = 4.75 + 0.45 * c.niceness - 0.02 * delays + rng.normal(0, 0.6, k)
        stars = np.clip(np.rint(latent), 1, 5)[rated]
        actual = np.maximum(PREDICTED_MIN + delays, 1.0)
        feats = [rating_features(PREDICTED_MIN, a) for a in actual]
        model_scores = np.clip(RATING_MODEL.predict(feats), 1, 5)
        rows.append((stars, model_scores))
    return rows


def trust_scores(deliveries, cap):
    ts.CUSTOMER_WEIGHT_MAX = cap
    out = []
    for stars, model_scores in deliveries:
        avg = float(stars.mean()) if len(stars) else None
        out.append(calculate_trust_score(avg, len(stars), list(model_scores))["trust_score"])
    return np.array(out)


def old_system(deliveries):
    """Before this project: plain average of ratings, 3.0 when there are none."""
    return np.array([float(s.mean()) if len(s) else 3.0 for s, _ in deliveries])


def zscore(x):
    return (x - x.mean()) / x.std()


def spearman(a, b):
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def main():
    original_cap = ts.CUSTOMER_WEIGHT_MAX
    results = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        couriers = make_couriers(rng)
        for k in DELIVERIES:
            deliveries = simulate_deliveries(rng, couriers, k)
            scores = {f"{int(c * 100)}/{int(round((1 - c) * 100))}": trust_scores(deliveries, c)
                      for c in WEIGHT_CAPS}
            scores["old (avg, 3 if none)"] = old_system(deliveries)
            for share in PUNCTUALITY_SHARES:
                truth = share * zscore(-couriers.lateness) + (1 - share) * zscore(couriers.niceness)
                for name, s in scores.items():
                    results.append({"seed": seed, "deliveries": k, "punctuality_share": share,
                                    "method": name, "spearman": spearman(s, truth)})
    ts.CUSTOMER_WEIGHT_MAX = original_cap

    df = pd.DataFrame(results)
    table = (df.groupby(["punctuality_share", "deliveries", "method"])["spearman"]
               .mean().round(3).unstack("method"))
    order = [f"{int(c * 100)}/{int(round((1 - c) * 100))}" for c in WEIGHT_CAPS] + ["old (avg, 3 if none)"]
    table = table[order]

    os.makedirs(OUT_DIR, exist_ok=True)
    table.to_csv(os.path.join(OUT_DIR, "trust_weight_simulation.csv"))
    pd.set_option("display.width", 200)
    print("SIMULATION (synthetic couriers). Spearman rank correlation with hidden quality,")
    print("mean of", len(SEEDS), "runs x", N_COURIERS, "couriers. Columns: customers/model weight cap.\n")
    print(table.to_string())
    print("\nBest weight per row:")
    print(table.drop(columns=["old (avg, 3 if none)"]).idxmax(axis=1).to_string())

    plot_charts(table)


LABELS = {
    "en": {
        "panel": "platform values punctuality {p}%",
        "x": "customer weight cap (%)",
        "y": "rank correlation with true quality",
        "line": "after {k} deliveries",
        "ours": "70/30 (our choice)",
        "title": "Simulation (synthetic couriers): trust score weight vs. ranking quality",
        "file": "trust_weight_simulation.png",
    },
    "he": {
        "panel": "לאפליקציה חשובה עמידה בזמנים: {p}%",
        "x": "משקל הלקוחות בציון (%)",
        "y": "התאמה לאיכות האמיתית",
        "line": "אחרי {k} משלוחים",
        "ours": "70/30 (הבחירה שלנו)",
        "title": "סימולציה (שליחים מדומים): משקל הלקוחות בציון מול דיוק הדירוג",
        "file": "trust_weight_simulation_he.png",
    },
}


def plot_charts(table):
    """English and Hebrew charts of the results table."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed: no chart)")
        return
    caps_pct = [int(c * 100) for c in WEIGHT_CAPS]
    for lang, L in LABELS.items():
        # Matplotlib >= 3.10 lays out right-to-left text itself (no python-bidi needed)
        t = lambda x: x  # noqa: E731

        fig, axes = plt.subplots(1, len(PUNCTUALITY_SHARES), figsize=(13, 4.2), sharey=True)
        for ax, share in zip(axes, PUNCTUALITY_SHARES):
            for k in DELIVERIES:
                row = table.loc[(share, k)]
                ax.plot(caps_pct, [row[f"{p}/{100 - p}"] for p in caps_pct], marker="o",
                        label=t(L["line"].format(k=k)))
            ax.axvline(70, color="gray", linestyle=":", linewidth=1, label=t(L["ours"]))
            ax.set_title(t(L["panel"].format(p=int(share * 100))))
            ax.set_xlabel(t(L["x"]))
            ax.grid(alpha=0.3)
        axes[0].set_ylabel(t(L["y"]))
        axes[0].legend(fontsize=8)
        fig.suptitle(t(L["title"]))
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, L["file"]), dpi=130)
        plt.close(fig)
        print(f"Saved docs/{L['file']}")


if __name__ == "__main__":
    if "--charts-only" in sys.argv:  # redraw from the saved results without re-running
        saved = pd.read_csv(os.path.join(OUT_DIR, "trust_weight_simulation.csv"),
                            index_col=["punctuality_share", "deliveries"])
        plot_charts(saved)
    else:
        main()
