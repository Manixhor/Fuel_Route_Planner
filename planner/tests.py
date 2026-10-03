from unittest.mock import patch

from django.test import SimpleTestCase

from .service import PlanError, optimize, plan


def station(mile, price):
    return {"id": str(mile), "name": f"Station {mile}", "city": "Test", "state": "TX",
            "latitude": 32.0, "longitude": -97.0, "mile_marker": mile,
            "off_route_miles": 0.0, "price_per_gallon": price}


class OptimizerTests(SimpleTestCase):
    def test_cheaper_stop_gets_only_enough_fuel_to_reach_it(self):
        result = optimize([station(400, 4.0), station(700, 2.0)], 900, 50)
        self.assertEqual([item["id"] for item in result], ["400", "700"])
        self.assertAlmostEqual(result[0]["gallons_purchased"], 20)
        self.assertAlmostEqual(result[1]["gallons_purchased"], 20)

    def test_route_under_one_tank_needs_no_stop(self):
        self.assertEqual(optimize([station(100, 3)], 400, 50), [])

    def test_no_reachable_station_is_reported(self):
        with self.assertRaises(PlanError):
            optimize([station(510, 3)], 800, 50)

    def test_no_unnecessary_fuel_is_bought_near_destination(self):
        result = optimize([station(400, 3)], 600, 50)
        self.assertAlmostEqual(result[0]["gallons_purchased"], 10)


class ApiTests(SimpleTestCase):
    def test_map_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fuel Route Planner")

    @patch("planner.service.route")
    def test_route_response_has_map_stops_and_cost(self, mock_route):
        mock_route.return_value = {
            "distance": 600 / 0.000621371192,
            "duration": 36000,
            "geometry": {"type": "LineString", "coordinates": [[-97.0, 32.0], [-90.0, 32.0]]},
        }
        response = self.client.post("/api/route/", data='{"start":{"city":"Dallas","state":"TX"},"finish":{"city":"Atlanta","state":"GA"}}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["route"]["geometry"]["type"], "LineString")
        self.assertGreater(body["fuel_summary"]["total_money_spent_usd"], 0)
        self.assertEqual(body["routing_api_calls_per_uncached_request"], 1)
        mock_route.assert_called_once()

    def test_invalid_city_is_rejected_before_routing(self):
        response = self.client.post("/api/route/", data='{"start":{"city":"Madeup","state":"TX"},"finish":{"city":"Atlanta","state":"GA"}}', content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_is_rejected(self):
        response = self.client.post("/api/route/", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
