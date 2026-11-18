"""mod_weather.py  v0.2.0 — погода для превью и поиск городов: open-meteo.com (без ключа).

Журнал:
v0.2.0: первая версия — текущая погода и мин/макс за сегодня, поиск города по названию; сбой сети ≠ «нет погоды»:
        превью показывает пример и пишет об этом в журнал.
"""
import json
import ssl
import urllib.parse
import urllib.request

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
DEMO = {"valid": 1, "temp10": 50, "code": 2, "tmin10": 10, "tmax10": 80, "wind10": 30, "hum": 70, "is_day": 1}


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "LineStudio"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def current(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1, "wind_speed_unit": "ms",
        "current": "temperature_2m,weather_code,is_day,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min"})
    d = _get(f"{FORECAST}?{q}")
    c, day = d["current"], d["daily"]
    return {"valid": 1, "temp10": round(c["temperature_2m"] * 10), "code": int(c["weather_code"]),
            "tmin10": round(day["temperature_2m_min"][0] * 10), "tmax10": round(day["temperature_2m_max"][0] * 10),
            "wind10": round(c["wind_speed_10m"] * 10), "hum": int(c["relative_humidity_2m"]),
            "is_day": int(c["is_day"])}


def search(name, lang="ru"):
    """Города по названию: [{"name", "lat", "lon", "where"}]."""
    q = urllib.parse.urlencode({"name": name, "count": 8, "language": lang, "format": "json"})
    d = _get(f"{GEOCODE}?{q}")
    out = []
    for r in d.get("results") or []:
        where = ", ".join(x for x in (r.get("admin1"), r.get("country")) if x)
        out.append({"name": r["name"], "lat": round(r["latitude"], 4), "lon": round(r["longitude"], 4),
                    "where": where})
    return out
