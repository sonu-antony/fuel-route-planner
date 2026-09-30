import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from config.env import non_negative_integer, non_negative_number, positive_number

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-jl^o55lqe0^9jsq6=w7f9wv2ne@5h7o6f$u1*@t_nl^sl2_@z&"
)

DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [host for host in os.environ.get("ALLOWED_HOSTS", "").split(",") if host]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "stations",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

ORS_API_KEY = os.environ.get("ORS_API_KEY")
ORS_PROFILE = os.environ.get("ORS_PROFILE", "driving-hgv")
VEHICLE_RANGE_MILES = positive_number("VEHICLE_RANGE_MILES", 500)
VEHICLE_MILES_PER_GALLON = positive_number("VEHICLE_MILES_PER_GALLON", 10)
CORRIDOR_MILES = positive_number("CORRIDOR_MILES", 10)
ROUTE_SAMPLE_MILES = positive_number("ROUTE_SAMPLE_MILES", 2)
ROUTING_TIMEOUT_SECONDS = positive_number("ROUTING_TIMEOUT_SECONDS", 10)
TRIP_CACHE_SECONDS = non_negative_integer("TRIP_CACHE_SECONDS", 86400)
FUEL_STOP_COST = non_negative_number("FUEL_STOP_COST", 0)
FUEL_RESERVE_GALLONS = non_negative_number("FUEL_RESERVE_GALLONS", 5)
if FUEL_RESERVE_GALLONS >= VEHICLE_RANGE_MILES / VEHICLE_MILES_PER_GALLON:
    raise ImproperlyConfigured(
        f"FUEL_RESERVE_GALLONS must be smaller than the "
        f"{VEHICLE_RANGE_MILES / VEHICLE_MILES_PER_GALLON:g}-gallon tank, "
        f"got {FUEL_RESERVE_GALLONS:g}"
    )
