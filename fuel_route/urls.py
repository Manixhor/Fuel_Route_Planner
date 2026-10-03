from django.urls import path
from planner.views import cities, health, map_page, plan_route

urlpatterns = [
    path("", map_page),
    path("api/health/", health),
    path("api/cities/", cities),
    path("api/route/", plan_route),
]
