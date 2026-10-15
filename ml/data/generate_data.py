"""Generate realistic sample landslide data for the NER region.

This is DEMO/SAMPLE data used to train the prototype model. It is clearly
labelled as such. In production, replace with real observations from weather
stations, satellites and ground sensors.

Usage:
    python -m ml.data.generate_data          (from project root)
    python generate_data.py                  (from ml/data)
"""
import csv
import json
import math
import os
import random
from datetime import datetime, timedelta

random.seed(42)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ML_DATA_DIR = os.path.join(PROJECT_ROOT, "ml", "data")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ML_DATA_DIR, exist_ok=True)


# Northeast India states
STATES = [
    "Arunachal Pradesh",
    "Assam",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Sikkim",
    "Tripura",
]


def generate_locations():
    """Generate a realistic set of monitoring locations across NER states."""
    locations = [
        # name, state, district, lat, lon, elevation, slope
        ("Churachandpur", "Manipur", "Churachandpur", 24.3343, 93.6766, 914, 32.4),
        ("Senapati", "Manipur", "Senapati", 25.2680, 94.0090, 1061, 35.1),
        ("Tuensang", "Nagaland", "Tuensang", 26.2670, 94.8250, 1371, 38.0),
        ("Mokokchung", "Nagaland", "Mokokchung", 26.3240, 94.5260, 1325, 33.5),
        ("Aizawl", "Mizoram", "Aizawl", 23.7271, 92.7176, 1132, 30.2),
        ("Lunglei", "Mizoram", "Lunglei", 22.8820, 92.7330, 1222, 34.7),
        ("Tawang", "Arunachal Pradesh", "Tawang", 27.5854, 91.8600, 2669, 42.0),
        ("Itanagar", "Arunachal Pradesh", "Papum Pare", 27.0844, 93.6053, 750, 25.3),
        ("Shillong", "Meghalaya", "East Khasi Hills", 25.5788, 91.8933, 1496, 28.8),
        ("Cherrapunji", "Meghalaya", "East Khasi Hills", 25.3005, 91.7042, 1484, 27.9),
        ("Gangtok", "Sikkim", "East Sikkim", 27.3389, 88.6065, 1436, 31.5),
        ("Namchi", "Sikkim", "South Sikkim", 27.1774, 88.3490, 550, 22.1),
        ("Dima Hasao", "Assam", "Dima Hasao", 25.1650, 93.6500, 750, 26.8),
        ("Karbi Anglong", "Assam", "Karbi Anglong", 26.0000, 93.5000, 400, 20.5),
        ("Agartala", "Tripura", "West Tripura", 23.8315, 91.2868, 13, 8.2),
        ("Rangamati", "Tripura", "Dhalai", 23.9000, 92.0500, 200, 15.6),
        ("Kolasib", "Mizoram", "Kolasib", 24.2220, 92.6790, 900, 29.4),
        ("Ziro", "Arunachal Pradesh", "Lower Subansiri", 27.5500, 93.8300, 1588, 25.6),
        ("Yuksom", "Sikkim", "West Sikkim", 27.3745, 88.2238, 1780, 36.2),
        ("Lakhimpur", "Assam", "Lakhimpur", 27.2350, 94.1083, 101, 12.4),
        ("Ukhrul", "Manipur", "Ukhrul", 25.1030, 94.3690, 1662, 40.3),
        ("Mon", "Nagaland", "Mon", 26.7250, 95.0400, 898, 24.8),
        ("Tura", "Meghalaya", "West Garo Hills", 25.5142, 90.2022, 649, 26.3),
        ("North Sikkim", "Sikkim", "Mangan", 27.5167, 88.5333, 1550, 34.0),
        ("Haflong", "Assam", "Dima Hasao", 25.1648, 93.0173, 680, 25.9),
        ("Champai", "Mizoram", "Champhai", 23.4600, 93.3300, 1600, 28.6),
        ("Kohima", "Nagaland", "Kohima", 25.6751, 94.1078, 1444, 24.7),
        ("Daporijo", "Arunachal Pradesh", "Upper Subansiri", 27.9990, 94.2220, 908, 23.4),
        ("Khowai", "Tripura", "Khowai", 24.0833, 91.6000, 100, 11.2),
        ("Thenzawl", "Mizoram", "Mamit", 23.7600, 92.8400, 1210, 31.8),
    ]
    return locations


def generate_historical_data(locations, n_years=8, rows_per_year=6):
    """Generate realistic historical environmental + landslide data."""
    rows = []
    start_date = datetime(2018, 1, 1)
    end_date = datetime(2026, 1, 1)

    land_cover_types = ["Dense Forest", "Open Forest", "Shrubland", "Agriculture", "Barren/Rocky"]
    soil_types = ["Clay Loam", "Sandy Loam", "Loam", "Clay", "Sandy Clay Loam"]
    rock_types = ["Soft Sedimentary", "Hard Sedimentary", "Metamorphic", "Igneous", "Mixed"]

    for (name, state, district, lat, lon, elev, slope) in locations:
        base_risk = 0.0
        # Geological base tendency
        if slope > 35:
            base_risk += 0.25
        elif slope > 28:
            base_risk += 0.18
        elif slope > 20:
            base_risk += 0.10
        if elev > 1200:
            base_risk += 0.15
        elif elev > 700:
            base_risk += 0.08

        current = start_date
        while current < end_date:
            # Monthly seasonality - monsoon Jun-Sep heavy
            month = current.month
            if month in (6, 7, 8):
                season = "Monsoon"
                rainfall = random.uniform(90, 220)
                rain_intensity = random.uniform(15, 55)
                humidity = random.uniform(80, 98)
            elif month in (4, 5, 9, 10):
                season = "Pre/Post Monsoon"
                rainfall = random.uniform(30, 110)
                rain_intensity = random.uniform(5, 25)
                humidity = random.uniform(65, 90)
            elif month in (11, 12, 1):
                season = "Winter"
                rainfall = random.uniform(0, 20)
                rain_intensity = random.uniform(0, 5)
                humidity = random.uniform(40, 65)
            else:
                season = "Spring"
                rainfall = random.uniform(15, 50)
                rain_intensity = random.uniform(2, 12)
                humidity = random.uniform(50, 75)

            temperature = random.uniform(8, 24) - (elev / 300)
            soil_moisture = min(100, max(10, rainfall * 0.55 + humidity * 0.35 + random.uniform(-5, 5)))
            wind_speed = random.uniform(2, 12)
            pressure = random.uniform(950, 1010)

            land_cover = random.choice(land_cover_types)
            soil_type = random.choice(soil_types)
            rock_type = random.choice(rock_types)

            # Distance from drain (km), higher = further from water
            dist_drain = random.uniform(0.2, 12.0)

            # Historical occurrence probability
            hist_occur = 1 if random.random() < (base_risk + 0.15) else 0

            # Build feature vector for label: strongly driven by rainfall + moisture + slope
            risk_input = (
                rainfall * 0.45
                + rain_intensity * 0.60
                + soil_moisture * 0.55
                + slope * 2.2
                + elev * 0.02
                + (hist_occur * 25)
                + (0 if dist_drain < 1.5 else 6)
            )
            noise = random.uniform(-8, 8)
            risk_input += noise

            # Determine label - landslide events are relatively rare overall.
            if risk_input > 185:
                landslide = random.choice([1, 1, 1, 1])
            elif risk_input > 140:
                landslide = random.choice([1, 1, 1, 0])
            elif risk_input > 95:
                landslide = random.choice([1, 0, 0, 0])
            else:
                landslide = 0

            rows.append({
                "location": name,
                "state": state,
                "district": district,
                "latitude": lat,
                "longitude": lon,
                "elevation": round(elev, 1),
                "slope": round(slope, 2),
                "rainfall": round(rainfall, 1),
                "rainfall_intensity": round(rain_intensity, 1),
                "soil_moisture": round(soil_moisture, 1),
                "temperature": round(temperature, 1),
                "humidity": round(humidity, 1),
                "wind_speed": round(wind_speed, 1),
                "pressure": round(pressure, 1),
                "land_cover": land_cover,
                "soil_type": soil_type,
                "rock_type": rock_type,
                "distance_to_drain": round(dist_drain, 2),
                "historical_occurrence": hist_occur,
                "season": season,
                "timestamp": current.strftime("%Y-%m-%d"),
                "landslide": landslide,
            })

            current += timedelta(days=int(365 / rows_per_year))

    return rows


def generate_realtime_sample(locations):
    """Generate a sample realtime JSON payload for the demo."""
    now = datetime.now()
    samples = []
    for (name, state, district, lat, lon, elev, slope) in locations:
        month = now.month
        if month in (6, 7, 8):
            rainfall = random.uniform(90, 220)
            rain_intensity = random.uniform(15, 55)
            humidity = random.uniform(80, 98)
        elif month in (4, 5, 9, 10):
            rainfall = random.uniform(30, 110)
            rain_intensity = random.uniform(5, 25)
            humidity = random.uniform(65, 90)
        else:
            rainfall = random.uniform(0, 50)
            rain_intensity = random.uniform(0, 12)
            humidity = random.uniform(40, 75)

        samples.append({
            "location": name,
            "state": state,
            "district": district,
            "latitude": lat,
            "longitude": lon,
            "elevation": round(elev, 1),
            "slope": round(slope, 2),
            "rainfall": round(rainfall, 1),
            "rainfall_intensity": round(rain_intensity, 1),
            "soil_moisture": round(min(100, rainfall * 0.55 + humidity * 0.35), 1),
            "temperature": round(random.uniform(10, 26) - (elev / 300), 1),
            "humidity": round(humidity, 1),
            "wind_speed": round(random.uniform(2, 12), 1),
            "pressure": round(random.uniform(950, 1010), 1),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return samples


def main():
    locations = generate_locations()

    # monitoring_locations.csv
    loc_file = os.path.join(DATA_DIR, "monitoring_locations.csv")
    with open(loc_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "state", "district", "latitude", "longitude", "elevation", "slope"])
        for row in locations:
            writer.writerow(row)
    print(f"Wrote {len(locations)} locations -> {loc_file}")

    # historical_landslide_data.csv
    hist = generate_historical_data(locations)
    hist_file = os.path.join(DATA_DIR, "historical_landslide_data.csv")
    fieldnames = list(hist[0].keys())
    with open(hist_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(hist)
    print(f"Wrote {len(hist)} historical rows -> {hist_file}")

    # sample_realtime_data.json
    samples = generate_realtime_sample(locations)
    realtime_file = os.path.join(DATA_DIR, "sample_realtime_data.json")
    with open(realtime_file, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now(), "source": "DEMO", "samples": samples}, f, indent=2)
    print(f"Wrote {len(samples)} realtime samples -> {realtime_file}")

    print("\nData generation complete (DEMO data).")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
