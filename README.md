# Fuel Route Planner

A Django 6.1.1 API that plans a US driving route, suggests cost-aware fuel stops, and estimates trip fuel cost for a vehicle with a 500-mile range and 10 mpg economy.

## Run locally

Requires Python 3.12 or newer.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the map, or use the API from Postman. No database migration or API key is needed. Internet access is needed for the OSRM demo route service and OpenFreeMap map tiles.

## API

`POST /api/route/` with JSON:

```json
{
  "start": {"city": "Dallas", "state": "TX"},
  "finish": {"city": "Atlanta", "state": "GA"},
  "initial_fuel_gallons": 50
}
```

`start` and `finish` may instead contain `latitude` and `longitude`. City/state inputs are validated against an offline US place list. Coordinate inputs receive coarse USA bounding checks. `initial_fuel_gallons` is optional, defaults to a full 50-gallon tank, and must be from 0 to 50. A 0-gallon start may be infeasible if no fuel stop is at the origin.

```bash
curl -sS http://127.0.0.1:8000/api/route/ \
  -H 'Content-Type: application/json' \
  -d '{"start":{"city":"Dallas","state":"TX"},"finish":{"city":"Atlanta","state":"GA"}}'
```

The response includes a GeoJSON `route.geometry` LineString, route distance and duration, `fuel_stops` with station details, map coordinates, mile markers, price and gallons to buy, and a `fuel_summary`. The latter reports both cash spent at route stops and `total_money_spent_usd`. The total includes an estimate for fuel consumed from the starting tank, priced using a nearby station in the supplied file. It is positive even when a short route needs no roadside stop. Error responses have an `error` field and an appropriate 400, 422 or 503 status. `GET /api/health/` is a simple readiness check.

Import [`postman/Fuel Route Planner.postman_collection.json`](postman/Fuel%20Route%20Planner.postman_collection.json) into Postman to run sample requests.

## How it works

1. Resolve each city/state locally. This makes geocoding require **zero API calls**.
2. Request the full GeoJSON route from OSRM in **one routing API call**. Identical routes are cached in process.
3. Match fuel stations to the route within a 10-mile corridor, using their offline place coordinates.
4. Traverse the ordered stations. At each station, buy enough to reach the first cheaper station within 500 miles; if none exists, fill only as much as needed for the next 500 miles or the destination. This minimizes fuel purchase cost on the fixed route, given the candidate stops and the starting fuel amount.

The price CSV has 8,151 rows, including Canadian entries and duplicate OPIS IDs. The offline build keeps the least expensive row for each matched US ID and yields 6,619 distinct US stations. `scripts/build_station_data.py` reproduces the files in `planner/data/` from `data/fuel_prices_original.csv` and `data/geonames_US_postal.zip`.

## Accuracy and scope

- The source price CSV has no station latitude/longitude. A station is plotted at its **city's median postal-code coordinate**, so its map marker, distance from the road, and route mile marker are approximate. This is the largest limitation. Accurate station addresses or coordinates would improve recommendations.
- Fuel calculations use the OSRM route mileage at 10 mpg. Extra driving to enter and leave a fuel stop is not included. A station within the 10-mile corridor may still require a different actual road detour.
- The optimizer chooses fuel purchases on the route returned by OSRM; it does not compare alternative driving routes. A few small purchases can appear when they save money, since no stop inconvenience charge is applied.
- Price data is a static snapshot supplied for the assignment, not current live fuel prices.
- OSRM's public demo is for reasonable non-commercial use and has no uptime guarantee; stay below one request per second. For production, configure `OSRM_BASE_URL` to a dedicated OSRM service and use proper shared caching and rate controls.

## Tests

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test
```

## Sources

- [Django downloads](https://www.djangoproject.com/download/) for the current stable version.
- [OSRM route API documentation](https://project-osrm.org/docs/v5.24.0/api/) and [demo server use policy](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server).
- [GeoNames US postal data](https://download.geonames.org/export/zip/US.zip), used offline under the [GeoNames attribution license](https://www.geonames.org/export/).
- [OpenFreeMap](https://openfreemap.org/) and [MapLibre GL JS](https://maplibre.org/maplibre-gl-js/docs/) for the interactive demo map.
- Fuel prices: assignment attachment, included unmodified in `data/fuel_prices_original.csv`.

## Five-minute demo outline

1. Show the map page at `http://127.0.0.1:8000/` with Dallas → Atlanta. Point out the route and fuel-stop markers.
2. Send the same JSON request in Postman. Show `route.geometry`, `fuel_stops`, `fuel_summary`, and `routing_api_calls: 1`.
3. Send Los Angeles → Las Vegas to show a one-tank trip with no roadside stops and a nonzero estimated trip cost.
4. Briefly show `planner/service.py`: offline station matching, the one OSRM request, and the purchasing algorithm.
5. Mention the city-centroid accuracy limit and that a production deployment would use real station coordinates.
