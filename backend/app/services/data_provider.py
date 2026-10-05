"""Environmental data provider abstraction.

Supports LIVE weather via OpenWeatherMap (free tier) or DEMO simulated data.
If the live API is unavailable (no key, offline, error), it transparently falls
back to demo data and reports the source so the UI can show LIVE vs DEMO.

Demo data is deterministic within a 15-minute time window per location, so it
is reproducible for judges yet still simulates changing conditions over time.
"""
import json
import random
from datetime import datetime

import requests

from app.config import settings

_BUCKET_MINUTES = 15


class WeatherProvider:
    def __init__(self):
        self.source = "DEMO"
        self.api_key = settings.OPENWEATHER_API_KEY

    def get_conditions(self, location) -> dict:
        """Return weather conditions for a location dict.

        location: dict with name, lat, lon, elevation, slope.
        Returns dict with rainfall, soil_moisture, temperature, humidity,
                wind_speed, pressure and data_source.
        """
        if self.api_key and settings.DATA_MODE == "LIVE":
            try:
                live = self._fetch_live(location)
                if live is not None:
                    return live
            except Exception:
                pass  # fall through to demo
        demo = self._simulate(location)
        demo["data_source"] = "DEMO"
        return demo

    def _fetch_live(self, location) -> dict | None:
        url = (
            f"{settings.OPENWEATHER_BASE_URL}/weather"
            f"?lat={location['latitude']}&lon={location['longitude']}"
            f"&appid={self.api_key}&units=metric"
        )
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        rainfall = 0.0
        if "rain" in data and data["rain"]:
            rainfall = data["rain"].get("1h", 0) or 0
        conditions = {
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "wind_speed": data["wind"]["speed"],
            "rainfall": rainfall,
            "rainfall_intensity": rainfall,
            "soil_moisture": min(100, max(0, 40 + rainfall * 0.6)),
            "data_source": "LIVE",
            "weather_main": data.get("weather", [{}])[0].get("main", "Unknown"),
        }
        return conditions

    def _simulate(self, location) -> dict:
        """Deterministic demo weather for (location, time window)."""
        now = datetime.now()
        bucket = now.replace(
            minute=(now.minute // _BUCKET_MINUTES) * _BUCKET_MINUTES, second=0, microsecond=0
        )
        seed = f"{location['name']}|{location['state']}|{bucket.isoformat()}"
        rng = random.Random(seed)

        month = now.month
        slopeness = location.get("slope", 0)

        # Seasonally driven rainfall
        if month in (6, 7, 8):
            base_rain = rng.uniform(60, 160)
            rain_intensity = rng.uniform(15, 45)
            humidity = rng.uniform(78, 96)
            season = "Monsoon"
        elif month in (4, 5, 9, 10):
            base_rain = rng.uniform(20, 80)
            rain_intensity = rng.uniform(5, 22)
            humidity = rng.uniform(60, 88)
            season = "Transition"
        else:
            base_rain = rng.uniform(0, 35)
            rain_intensity = rng.uniform(0, 10)
            humidity = rng.uniform(40, 68)
            season = "Winter/Dry"

        # Southern / Meghalaya often wetter
        if location["state"] == "Meghalaya":
            base_rain *= 1.4

        temperature = rng.uniform(10, 26) - (location.get("elevation", 500) / 300)
        rainfall = max(0.0, base_rain * rng.uniform(0.7, 1.3))
        soil_moisture = min(100.0, max(10.0, rainfall * 0.5 + humidity * 0.35 + rng.uniform(-3, 3)))

        return {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
            "pressure": round(rng.uniform(950, 1010), 1),
            "wind_speed": round(rng.uniform(2, 12), 1),
            "rainfall": round(rainfall, 1),
            "rainfall_intensity": round(rain_intensity, 1),
            "soil_moisture": round(soil_moisture, 1),
            "data_source": "DEMO",
            "weather_main": "DEMO SIM",
            "season": season,
        }


weather_provider = WeatherProvider()
