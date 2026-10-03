import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .service import PlanError, plan


def map_page(request):
    return render(request, "planner/map.html")


def health(request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
def plan_route(request):
    if request.method != "POST":
        response = JsonResponse({"error": "Use POST with a JSON body"}, status=405)
        response["Allow"] = "POST"
        return response
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise PlanError("JSON body must be an object")
        initial = float(payload.get("initial_fuel_gallons", 50))
        if not (initial == initial and abs(initial) != float("inf")):
            raise ValueError
        result = plan(payload.get("start"), payload.get("finish"), initial)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    except (TypeError, ValueError):
        return JsonResponse({"error": "initial_fuel_gallons must be numeric"}, status=400)
    except PlanError as error:
        return JsonResponse({"error": str(error)}, status=error.status)
    return JsonResponse(result)
