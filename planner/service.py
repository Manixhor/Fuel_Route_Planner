import csv
import math
import os
from functools import lru_cache
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent / "data"
MILES_PER_METER = 0.000621371192
RANGE_MILES = 500.0
MPG = 10.0
TANK_GALLONS = RANGE_MILES / MPG
CORRIDOR_MILES = 10.0
US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())


class PlanError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=1)
def places():
    with (DATA_DIR / "places.csv").open(newline="", encoding="utf-8") as source:
        return {(row["city"], row["state"]): (float(row["latitude"]), float(row["longitude"]))
                for row in csv.DictReader(source)}


@lru_cache(maxsize=1)
def stations():
    with (DATA_DIR / "stations.csv").open(newline="", encoding="utf-8") as source:
        return [dict(row, latitude=float(row["latitude"]), longitude=float(row["longitude"]),
                     price_per_gallon=float(row["price_per_gallon"])) for row in csv.DictReader(source)]


def location(value, label):
    if not isinstance(value, dict):
        raise PlanError(f"{label} must be an object containing city and state, or latitude and longitude")
    if "city" in value and "state" in value:
        city = " ".join(str(value["city"]).upper().replace(".", "").replace("'", "").split())
        state = str(value["state"]).strip().upper()
        if state not in US_STATES:
            raise PlanError(f"{label}.state must be a US state abbreviation")
        point = places().get((city, state))
        if point is None:
            raise PlanError(f"Unknown US city/state for {label}: {city}, {state}")
        return point, {"city": city.title(), "state": state, "latitude": point[0], "longitude": point[1]}
    try:
        lat, lon = float(value["latitude"]), float(value["longitude"])
    except (KeyError, TypeError, ValueError):
        raise PlanError(f"{label} must contain city/state or numeric latitude/longitude") from None
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise PlanError(f"{label} coordinates must be finite")
    # Coarse US extents. City/state inputs give stronger country validation.
    lower_48 = 24.3 <= lat <= 49.5 and -125 <= lon <= -66
    alaska = 51 <= lat <= 72 and -180 <= lon <= -129
    hawaii = 18.8 <= lat <= 22.4 and -161 <= lon <= -154
    if not (lower_48 or alaska or hawaii):
        raise PlanError(f"{label} coordinates must be in the USA")
    return (lat, lon), {"latitude": lat, "longitude": lon}


@lru_cache(maxsize=128)
def route(start_lat, start_lon, finish_lat, finish_lon):
    base = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
    url = f"{base}/route/v1/driving/{start_lon:.6f},{start_lat:.6f};{finish_lon:.6f},{finish_lat:.6f}"
    try:
        response = requests.get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"}, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PlanError(f"Routing service unavailable: {exc}", 503) from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise PlanError("No drivable route found between these locations", 422)
    result = data["routes"][0]
    if not result.get("geometry", {}).get("coordinates") or result.get("distance", 0) <= 0:
        raise PlanError("Routing service returned an invalid route", 502)
    return result


def haversine(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))


def sampled_route(coordinates):
    """Reduce a detailed route to roughly 5-mile segments for fast station projection."""
    points = [(lat, lon) for lon, lat in coordinates]
    sample = [(points[0], 0.0)]
    total = 0.0
    for previous, point in zip(points, points[1:]):
        total += haversine(previous, point)
        if total - sample[-1][1] >= 5:
            sample.append((point, total))
    if sample[-1][0] != points[-1]:
        sample.append((points[-1], total))
    return sample, total


def project(point, a, b):
    """Closest point on a short segment, in local miles."""
    mean_lat = math.radians((point[0] + a[0] + b[0]) / 3)
    cos_lat = math.cos(mean_lat)
    x = (point[1] - a[1]) * 69.172 * cos_lat
    y = (point[0] - a[0]) * 69.0
    dx = (b[1] - a[1]) * 69.172 * cos_lat
    dy = (b[0] - a[0]) * 69.0
    denominator = dx * dx + dy * dy
    fraction = max(0.0, min(1.0, (x * dx + y * dy) / denominator)) if denominator else 0.0
    return math.hypot(x - fraction * dx, y - fraction * dy), fraction


def candidate_stations(route_geometry, route_miles):
    sample, geometric_miles = sampled_route(route_geometry)
    if not geometric_miles:
        return []
    min_lat = min(point[0][0] for point in sample) - 0.2
    max_lat = max(point[0][0] for point in sample) + 0.2
    min_lon = min(point[0][1] for point in sample) - 0.3
    max_lon = max(point[0][1] for point in sample) + 0.3
    candidates = []
    for station in stations():
        lat, lon = station["latitude"], station["longitude"]
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            continue
        nearest = (float("inf"), 0.0)
        for (a, a_miles), (b, b_miles) in zip(sample, sample[1:]):
            if not (min(a[0], b[0]) - 0.17 <= lat <= max(a[0], b[0]) + 0.17 and
                    min(a[1], b[1]) - 0.27 <= lon <= max(a[1], b[1]) + 0.27):
                continue
            distance, fraction = project((lat, lon), a, b)
            if distance < nearest[0]:
                nearest = (distance, a_miles + fraction * (b_miles - a_miles))
        if nearest[0] <= CORRIDOR_MILES:
            mile = nearest[1] * route_miles / geometric_miles
            if 0.01 < mile < route_miles - 0.01:
                candidates.append(dict(station, mile_marker=mile, off_route_miles=nearest[0]))
    # Station addresses lack coordinates. A place centroid is shared by all stops in that city;
    # retain the least expensive one at each city position.
    cheapest = {}
    for item in candidates:
        key = (item["city"].upper(), item["state"], round(item["mile_marker"], 1))
        if key not in cheapest or item["price_per_gallon"] < cheapest[key]["price_per_gallon"]:
            cheapest[key] = item
    return sorted(cheapest.values(), key=lambda item: item["mile_marker"])


def optimize(stops, route_miles, initial_gallons):
    """Optimal purchases on an ordered route with fixed 50-gallon capacity and prices."""
    remaining = initial_gallons
    previous_mile = 0.0
    chosen = []
    for index, station in enumerate(stops):
        distance = station["mile_marker"] - previous_mile
        if distance > remaining * MPG + 1e-6:
            raise PlanError("No priced fuel stop is reachable before the tank runs empty", 422)
        remaining -= distance / MPG
        previous_mile = station["mile_marker"]
        cheaper_mile = None
        for later in stops[index + 1:]:
            if later["mile_marker"] - previous_mile > RANGE_MILES:
                break
            if later["price_per_gallon"] < station["price_per_gallon"]:
                cheaper_mile = later["mile_marker"]
                break
        target_miles = min(route_miles - previous_mile, RANGE_MILES)
        if cheaper_mile is not None:
            target_miles = min(target_miles, cheaper_mile - previous_mile)
        gallons = max(0.0, target_miles / MPG - remaining)
        if gallons > 1e-8:
            remaining += gallons
            chosen.append(dict(station, gallons_purchased=round(gallons, 3),
                               cost_usd=round(gallons * station["price_per_gallon"], 2)))
    if route_miles - previous_mile > remaining * MPG + 1e-6:
        raise PlanError("No priced fuel stop is reachable before the tank runs empty", 422)
    return chosen


def starting_fuel_price(start_point):
    nearby = sorted(((haversine(start_point, (station["latitude"], station["longitude"])), station)
                     for station in stations()), key=lambda item: item[0])
    if not nearby:
        raise PlanError("No fuel prices available", 503)
    radius = max(10.0, nearby[0][0])
    selected = min((station for distance, station in nearby if distance <= radius),
                   key=lambda station: station["price_per_gallon"])
    return selected


def plan(start, finish, initial_gallons=TANK_GALLONS):
    if not 0 <= initial_gallons <= TANK_GALLONS:
        raise PlanError("initial_fuel_gallons must be between 0 and 50")
    start_point, start_details = location(start, "start")
    finish_point, finish_details = location(finish, "finish")
    if haversine(start_point, finish_point) < 0.1:
        raise PlanError("Start and finish must be different locations")
    itinerary = route(*start_point, *finish_point)
    miles = itinerary["distance"] * MILES_PER_METER
    candidates = candidate_stations(itinerary["geometry"]["coordinates"], miles)
    selected = optimize(candidates, miles, initial_gallons)
    purchased = sum(stop["gallons_purchased"] for stop in selected)
    total_cost = sum(stop["cost_usd"] for stop in selected)
    origin_station = starting_fuel_price(start_point)
    starting_fuel_used = min(initial_gallons, miles / MPG)
    starting_fuel_cost = starting_fuel_used * origin_station["price_per_gallon"]
    return {
        "start": start_details,
        "finish": finish_details,
        "route": {"distance_miles": round(miles, 2), "duration_hours": round(itinerary["duration"] / 3600, 2),
                  "geometry": itinerary["geometry"]},
        "fuel_stops": selected,
        "fuel_summary": {"tank_capacity_gallons": TANK_GALLONS, "maximum_range_miles": RANGE_MILES,
                         "miles_per_gallon": MPG, "initial_fuel_gallons": initial_gallons,
                         "fuel_consumed_gallons": round(miles / MPG, 3),
                         "fuel_purchased_gallons": round(purchased, 3),
                         "cash_spent_at_route_stops_usd": round(total_cost, 2),
                         "starting_fuel_used_gallons": round(starting_fuel_used, 3),
                         "starting_fuel_price_estimate_usd_per_gallon": origin_station["price_per_gallon"],
                         "starting_fuel_cost_estimate_usd": round(starting_fuel_cost, 2),
                         "total_money_spent_usd": round(total_cost + starting_fuel_cost, 2)},
        "assumptions": ["Vehicle starts with the stated fuel; consumed starting fuel is valued at a nearby listed station price.",
                        "Stations are located by city centroid because the provided CSV has no station coordinates.",
                        "Stop proximity and mile markers are approximate; detour mileage and cost are excluded.",
                        "Optimization minimizes purchases along the returned route, not route choice."],
        "routing_api_calls": 1,
    }
