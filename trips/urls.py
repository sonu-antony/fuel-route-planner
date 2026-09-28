from django.urls import path

from trips import views

urlpatterns = [
    path("api/v1/health/", views.health, name="health"),
]
