from django.urls import path

from trips import views

urlpatterns = [
    path("api/v1/health/", views.health, name="health"),
    path("api/v1/trips/plan/", views.TripPlanView.as_view(), name="trip-plan"),
]
