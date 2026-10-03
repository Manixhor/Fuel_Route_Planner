"""One-time offline join of the supplied price CSV to GeoNames postal places."""
import csv
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "fuel_prices_original.csv"
POSTAL = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "geonames_US_postal.zip"
OUTPUT = ROOT / "planner" / "data" / "stations.csv"
PLACES_OUTPUT = ROOT / "planner" / "data" / "places.csv"

def clean(value):
    return " ".join(value.upper().replace(".", "").replace("'", "").split())

places = defaultdict(list)
with zipfile.ZipFile(POSTAL) as archive:
    rows = csv.reader(archive.open("US.txt").read().decode("utf-8").splitlines(), delimiter="\t")
    for row in rows:
        if len(row) >= 11 and row[9] and row[10]:
            places[(clean(row[2]), row[4].strip().upper())].append((float(row[9]), float(row[10])))

coordinates = {
    key: (statistics.median(point[0] for point in points), statistics.median(point[1] for point in points))
    for key, points in places.items()
}
PLACES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with PLACES_OUTPUT.open("w", newline="", encoding="utf-8") as target:
    writer = csv.writer(target)
    writer.writerow(["city", "state", "latitude", "longitude"])
    for (city, state), (latitude, longitude) in coordinates.items():
        writer.writerow([city, state, f"{latitude:.6f}", f"{longitude:.6f}"])
unmatched = defaultdict(int)
deduplicated = {}
with SOURCE.open(newline="", encoding="utf-8-sig") as source:
    for row in csv.DictReader(source):
        city = " ".join(row["City"].split())
        state = row["State"].strip().upper()
        location = coordinates.get((clean(city), state))
        if not location:
            unmatched[(city, state)] += 1
            continue
        price = float(row["Retail Price"])
        if price <= 0:
            continue
        station_id = row["OPIS Truckstop ID"].strip()
        record = {
            "id": station_id,
            "name": " ".join(row["Truckstop Name"].split()),
            "address": " ".join(row["Address"].split()),
            "city": city,
            "state": state,
            "latitude": f"{location[0]:.6f}",
            "longitude": f"{location[1]:.6f}",
            "price_per_gallon": f"{price:.5f}",
        }
        # Duplicate OPIS IDs in the source can have several names/prices; keep the lowest priced record.
        if station_id not in deduplicated or price < float(deduplicated[station_id]["price_per_gallon"]):
            deduplicated[station_id] = record

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with OUTPUT.open("w", newline="", encoding="utf-8") as target:
    writer = csv.DictWriter(target, fieldnames=list(next(iter(deduplicated.values()))))
    writer.writeheader()
    writer.writerows(deduplicated.values())
print(f"Wrote {len(deduplicated)} stations; {sum(unmatched.values())} unmatched rows")
print("Top unmatched:", sorted(unmatched.items(), key=lambda item: -item[1])[:15])
