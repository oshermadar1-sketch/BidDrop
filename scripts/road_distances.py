"""
Road distance and driving time for every restaurant -> customer route in the Zomato data.

preprocess.py uses the straight-line (haversine) distance. This script asks the
OpenStreetMap routing server (OSRM) for the road distance of the same routes, so the
delivery-time model can be trained on road distance as well (see preprocess.py).

The raw file has ~45k rows but only a few thousand distinct routes (703 restaurants, each
with a handful of customer points), so one table request per restaurant is enough.
Requests are spaced out to stay within the public server's fair-use limits.

Output (project root): Zomato_Road_Distances.csv
    Restaurant_latitude, Restaurant_longitude,
    Delivery_location_latitude, Delivery_location_longitude   (absolute values, 5 decimals)
    Road_Distance_km, Road_Duration_min, Road_Source ("osrm" or "air")

Safe to re-run: routes already in the output file are skipped.

Run from the project root:
    python scripts/road_distances.py
"""
import math
import os
import sys
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "Zomato Dataset.csv")
OUT = os.path.join(ROOT, "Zomato_Road_Distances.csv")
OSRM = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
PAUSE_SEC = float(os.getenv("ROUTING_PAUSE_SEC", "1.0"))
MAX_DEST = 99  # public server: at most 100 coordinates per table request

KEYS = ["Restaurant_latitude", "Restaurant_longitude",
        "Delivery_location_latitude", "Delivery_location_longitude"]


def air_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def unique_routes():
    df = pd.read_csv(RAW, low_memory=False)[KEYS].astype(float).abs().round(5)
    # Coordinates near (0, 0) are missing values in this file, not places.
    df = df[(df["Restaurant_latitude"] > 1) & (df["Restaurant_longitude"] > 1)]
    return df.drop_duplicates().reset_index(drop=True)


def table(src, dests):
    """One OSRM table request: distances/durations from src to every point in dests."""
    coords = ";".join(f"{lon},{lat}" for lat, lon in [src] + dests)
    params = {"sources": "0", "destinations": ";".join(str(i + 1) for i in range(len(dests))),
              "annotations": "distance,duration"}
    r = requests.get(f"{OSRM}/table/v1/driving/{coords}", params=params, timeout=30,
                     headers={"User-Agent": "biddrop-training-data"})
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("code"))
    return data["distances"][0], data["durations"][0]


def main():
    routes = unique_routes()
    done = set()
    if os.path.exists(OUT):
        prev = pd.read_csv(OUT)
        done = set(map(tuple, prev[KEYS].round(5).values.tolist()))
        print(f"resuming: {len(done)} routes already done")
    todo = routes[[tuple(x) not in done for x in routes[KEYS].values.tolist()]]
    print(f"routes: {len(routes)} total, {len(todo)} to fetch")

    header = not os.path.exists(OUT)
    fails = 0
    groups = list(todo.groupby(["Restaurant_latitude", "Restaurant_longitude"]))
    for gi, ((rlat, rlon), g) in enumerate(groups, 1):
        dests = g[["Delivery_location_latitude", "Delivery_location_longitude"]].values.tolist()
        rows = []
        for start in range(0, len(dests), MAX_DEST):
            chunk = dests[start:start + MAX_DEST]
            try:
                dist, dur = table((rlat, rlon), chunk)
                time.sleep(PAUSE_SEC)
            except Exception as e:
                fails += 1
                print(f"  restaurant {gi}: routing failed ({e}); using air distance", file=sys.stderr)
                time.sleep(5 * PAUSE_SEC)
                dist, dur = [None] * len(chunk), [None] * len(chunk)
            for (dlat, dlon), d, t in zip(chunk, dist, dur):
                if d is None or t is None:
                    km = air_km(rlat, rlon, dlat, dlon)
                    rows.append([rlat, rlon, dlat, dlon, round(km, 3), round(60 * km / 30.0, 1), "air"])
                else:
                    rows.append([rlat, rlon, dlat, dlon, round(d / 1000.0, 3), round(t / 60.0, 1), "osrm"])
        pd.DataFrame(rows, columns=KEYS + ["Road_Distance_km", "Road_Duration_min", "Road_Source"]) \
            .to_csv(OUT, mode="a", header=header, index=False)
        header = False
        if gi % 25 == 0 or gi == len(groups):
            print(f"  {gi}/{len(groups)} restaurants done, {fails} failures", flush=True)

    out = pd.read_csv(OUT)
    print(f"written {OUT}: {len(out)} routes, "
          f"{int((out['Road_Source'] == 'osrm').sum())} by road, "
          f"{int((out['Road_Source'] == 'air').sum())} fell back to air")


if __name__ == "__main__":
    main()
