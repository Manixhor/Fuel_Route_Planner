# Building a Fuel Route Planner with Django

## The idea

Imagine driving from Dallas to Atlanta. A map can show the road, but it does not tell you where to buy fuel at a good price. I built a Django API that combines a driving route with a supplied list of fuel prices to suggest fuel stops and estimate the trip cost.

The assessment sets two simple vehicle rules: the car can travel up to 500 miles on a full tank and gets 10 miles per gallon. A full tank therefore holds 50 gallons. The API accepts a start and finish location in the United States and returns the route, suggested fuel stops, and a cost summary.

## What the CSV file does

The supplied CSV is a list of fuel stations and their prices. It is the price source for the recommendations. Some rows are duplicates or outside the United States, so a preparation script cleans the data before the API uses it. The resulting local file contains 6,619 distinct US stations.

The CSV does not include GPS coordinates. For this assessment, the app places each station near its city's postal-code center. This makes the markers and road distances approximate, which is an important limitation of the results.

## How a request works

1. The user chooses a start and finish city, or sends coordinates to the API.
2. The app looks up city coordinates from local data, without calling a geocoding service.
3. It asks OSRM for the driving route. An uncached request makes one routing API call.
4. It finds stations close to that route and uses their prices to decide how much fuel to buy at each stop while keeping every leg within the 500-mile range.
5. It returns a GeoJSON route, fuel-stop details, and the estimated fuel cost. A small map page displays the same trip visually.

For example, a client can send:

```json
{
  "start": {"city": "Dallas", "state": "TX"},
  "finish": {"city": "Atlanta", "state": "GA"}
}
```

The cost summary separates money paid at roadside stops from the estimated value of fuel used from the starting tank. That distinction matters because fuel already in the tank was purchased before the trip.

## Tools used

The backend uses Django. OSRM supplies the driving route, while MapLibre GL JS and OpenFreeMap display it. The station and city data are prepared once and kept locally. A Postman collection contains example API requests.

## What I learned

The interesting part is turning a route into a fuel plan. A cheaper station can be worth waiting for, but the car must still have enough fuel to reach it. Data quality matters just as much as the algorithm: without exact station coordinates, a low price near the route may still involve a real-world detour. The current planner also focuses on fuel price, so it can recommend small extra purchases when they save a little money. Adding verified station coordinates and a cost for making each stop would make the recommendations more practical.

The [README](README.md) explains how to run the project and try the API.
