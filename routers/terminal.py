from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import requests
import os
import datetime
import statistics
import random
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

try:
    import pandas as pd
except Exception:
    pd = None

load_dotenv()

router = APIRouter(prefix="/terminal", tags=["Agri Terminal"])

# -----------------------
# Config
# -----------------------
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
DISTANCEMATRIX_API_KEY = os.getenv("DISTANCEMATRIX_API_KEY")

DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "international_prices_synthetic_expanded_inr.csv"
)

CACHE = {
    "commodities": {},
    "international_options": {"commodities": [], "ports": [], "timestamp": None},
    "last_refresh": None,
}
CACHE_REFRESH_INTERVAL = int(os.getenv("TERMINAL_CACHE_REFRESH_SECONDS", 5 * 60))


# -----------------------
# Helpers
# -----------------------
def float_or_none(x):
    try:
        return float(x)
    except Exception:
        return None


# -----------------------
# Mandi Data
# -----------------------
def fetch_mandi_records(commodity: str, limit: int = 200):
    try:
        url = "https://data.gov.in"
        params = {
            "api-key": DATA_GOV_API_KEY,
            "format": "json",
            "limit": limit,
            "filters[commodity]": commodity.capitalize(),
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        records = r.json().get("records", [])
        if not records:
            raise Exception("No mandi records returned")
        return records
    except Exception as e:
        print("⚠️ Mandi fallback:", e)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return [
            {
                "state": "Madhya Pradesh",
                "district": "Indore",
                "market": "Indore",
                "commodity": commodity.capitalize(),
                "variety": "Common",
                "arrival_date": today,
                "min_price": "2200",
                "max_price": "2450",
                "modal_price": "2350",
                "price_unit": "Rs/Quintal",
            },
            {
                "state": "Maharashtra",
                "district": "Nagpur",
                "market": "Nagpur",
                "commodity": commodity.capitalize(),
                "variety": "Common",
                "arrival_date": today,
                "min_price": "2250",
                "max_price": "2480",
                "modal_price": "2380",
                "price_unit": "Rs/Quintal",
            },
        ]


def normalize_mandi_records(records, commodity_name):
    normalized = []
    for r in records:
        try:
            modal_val = float_or_none(r.get("modal_price"))
            normalized.append(
                {
                    "state": r.get("state", "") or r.get("state_name", ""),
                    "district": r.get("district", ""),
                    "market": r.get("market", "") or r.get("market_name", ""),
                    "commodity": commodity_name.capitalize(),
                    "variety": r.get("variety", ""),
                    "arrival_date": r.get("arrival_date", ""),
                    "min_price": float_or_none(r.get("min_price")),
                    "max_price": float_or_none(r.get("max_price")),
                    "modal_price": modal_val,
                    "unit": r.get("price_unit", "Rs/Quintal"),
                }
            )
        except Exception:
            continue
    return normalized


# -----------------------
# Weather
# -----------------------
def fetch_weather_for_location(location):
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days=7&aqi=no&alerts=no"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})
        forecast_days = data.get("forecast", {}).get("forecastday", [])
        simplified_forecast = [
            {
                "date": d.get("date"),
                "avgtemp_c": d["day"].get("avgtemp_c"),
                "totalprecip_mm": d["day"].get("totalprecip_mm"),
                "avghumidity": d["day"].get("avghumidity"),
                "condition": d["day"]["condition"].get("text"),
            }
            for d in forecast_days
        ]
        return {
            "location": data.get("location", {}).get("name", location),
            "country": data.get("location", {}).get("country", "India"),
            "current": {
                "temp_c": current.get("temp_c"),
                "humidity": current.get("humidity"),
                "precip_mm": current.get("precip_mm"),
                "condition": current.get("condition", {}).get("text"),
            },
            "forecast": simplified_forecast,
        }
    except Exception as e:
        print("⚠️ Weather fallback:", e)
        return {
            "location": location,
            "country": "India",
            "current": {
                "temp_c": 28,
                "humidity": 55,
                "precip_mm": 0,
                "condition": "Clear",
            },
            "forecast": [],
        }


# -----------------------
# International CSV Loader
# -----------------------
def load_international_prices():
    if DATA_PATH.exists() and pd is not None:
        df = pd.read_csv(DATA_PATH)
        df.columns = [c.strip() for c in df.columns]
        return df
    print("⚠️ International CSV not available, using fallback.")
    return None


def build_international_options_from_csv():
    df = load_international_prices()
    if df is None:
        return {
            "commodities": ["Wheat", "Rice", "Maize", "Soybean"],
            "ports": ["Mumbai Port", "Kandla", "Chennai", "Novorossiysk"],
        }

    commodities = sorted(df.iloc[:, 0].dropna().unique().tolist())
    ports = sorted(df.iloc[:, 1].dropna().unique().tolist())
    return {"commodities": commodities, "ports": ports}


# -----------------------
# Price Forecast
# -----------------------
def generate_price_forecast(market_data, days=7):
    today = datetime.datetime.utcnow().date()
    prices = [m["modal_price"] for m in market_data if m.get("modal_price")]
    baseline = statistics.median(prices) if prices else 2300
    return [
        {
            "date": (today + datetime.timedelta(days=i)).strftime("%Y-%m-%d"),
            "forecast_price": round(baseline + random.uniform(-50, 50), 2),
        }
        for i in range(1, days + 1)
    ]


# -----------------------
# AI Insight (fallback)
# -----------------------
def fallback_structured_insight(
    commodity, market_data, summary, forecast, harvest_days, weather
):
    return {
        "recommendation": {
            "action": "HOLD",
            "confidence": 75,
            "reason": "Market stable, minor price movement expected.",
        },
        "yield_outlook": {"change_percent": "+0.0%", "factors": ["stable weather"]},
        "price_forecast_comment": "Prices likely steady for next week.",
        "market_sentiment": {"overall": "neutral", "keywords": ["steady", "stable"]},
        "optimal_market": {"sell_high": [], "buy_low": []},
        "ai_summary": "Market remains stable with no major risk detected.",
        "reason": "Stable prices and normal conditions.",
    }


# -----------------------
# Main Payload Builder
# -----------------------
def assemble_terminal_payload(commodity="wheat", harvest_days=53, location="Indore"):
    records = fetch_mandi_records(commodity)
    market_data = normalize_mandi_records(records, commodity)

    if not market_data:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        market_data = [
            {
                "state": "DemoState",
                "district": "DemoDistrict",
                "market": "Indore",
                "commodity": commodity.capitalize(),
                "variety": "Common",
                "arrival_date": today,
                "min_price": 2200,
                "max_price": 2500,
                "modal_price": 2350,
                "unit": "Rs/Quintal",
            }
        ]

    prices = [m["modal_price"] for m in market_data if m.get("modal_price")]
    avg_price = round(statistics.mean(prices), 2) if prices else 2300

    summary = {
        "commodity": commodity.capitalize(),
        "average_price": avg_price,
        "highest_price": max(prices) if prices else 0,
        "lowest_price": min(prices) if prices else 0,
    }

    weather = fetch_weather_for_location(location)
    price_forecast = generate_price_forecast(market_data)
    ai_structured = fallback_structured_insight(
        commodity, market_data, summary, price_forecast, harvest_days, weather
    )

    return {
        "timestamp": datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "commodity": commodity.capitalize(),
        "location": location,
        "summary": summary,
        "market_data": market_data,
        "price_forecast": price_forecast,
        "recommendation": ai_structured["recommendation"],
        "yield_outlook": ai_structured["yield_outlook"],
        "price_forecast_comment": ai_structured["price_forecast_comment"],
        "market_sentiment": ai_structured["market_sentiment"],
        "optimal_market": ai_structured["optimal_market"],
        "ai_summary": ai_structured["ai_summary"],
        "ai_reason": ai_structured["reason"],
    }


# -----------------------
# Background Cache Thread
# -----------------------
def cache_refresh_once_for(commodity="wheat", harvest_days=53, location="Indore"):
    try:
        payload = assemble_terminal_payload(commodity, harvest_days, location)
        CACHE["commodities"][commodity.lower()] = {
            "payload": payload,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        print(f"✅ Cached {commodity} ({len(payload['market_data'])} markets)")
    except Exception as e:
        print("⚠️ Cache refresh failed:", e)


def cache_background_loop():
    print("▶️ Terminal cache background thread started.")
    while True:
        try:
            for c in ["wheat", "rice", "maize", "soybean"]:
                cache_refresh_once_for(c)
            # also refresh international options
            CACHE["international_options"] = build_international_options_from_csv()
            CACHE["international_options"][
                "timestamp"
            ] = datetime.datetime.utcnow().isoformat()
            CACHE["last_refresh"] = datetime.datetime.utcnow().isoformat()
        except Exception as e:
            print("⚠️ Cache background loop error:", e)
        time.sleep(CACHE_REFRESH_INTERVAL)


_cache_thread_started = False


@router.on_event("startup")
def start_cache_on_startup():
    global _cache_thread_started
    if not _cache_thread_started:
        print("🧩 Prefilling terminal cache on startup...")
        for c in ["wheat", "rice", "maize", "soybean"]:
            cache_refresh_once_for(c)
        t = threading.Thread(target=cache_background_loop, daemon=True)
        t.start()
        _cache_thread_started = True
        print("🚀 Terminal cache system started successfully.")


# -----------------------
# API Endpoints
# -----------------------
@router.get("/")
def get_market_terminal(
    commodity: str = Query("wheat"),
    harvest_days: int = Query(53),
    location: str = Query("Indore"),
    use_cache: bool = Query(True),
):
    try:
        key = commodity.lower()
        if use_cache and CACHE["commodities"].get(key):
            cached = CACHE["commodities"][key]
            payload = cached["payload"]
            payload["cached_at"] = cached["timestamp"]
            payload["served_from_cache"] = True
            return JSONResponse(content=payload)

        payload = assemble_terminal_payload(commodity, harvest_days, location)
        payload["served_from_cache"] = False
        return JSONResponse(content=payload)
    except Exception as e:
        print("❌ Terminal Error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cached")
def get_terminal_cached():
    try:
        default = CACHE["commodities"].get("wheat")
        if not default or not default.get("payload"):
            print("⚙️ Cache empty, rebuilding...")
            cache_refresh_once_for("wheat")
            default = CACHE["commodities"].get("wheat")

        p = default["payload"]
        p["cached_at"] = default["timestamp"]
        p["served_from_cache"] = True
        return JSONResponse(content=p)
    except Exception as e:
        print("⚠️ cached endpoint error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/international-options")
def get_international_options():
    """Return cached or built international trade options."""
    try:
        opts = CACHE.get("international_options", {})
        if opts and opts.get("ports"):
            return JSONResponse(content=opts)

        # fallback if cache empty
        opts = build_international_options_from_csv()
        CACHE["international_options"] = {
            "commodities": opts["commodities"],
            "ports": opts["ports"],
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        return JSONResponse(content=CACHE["international_options"])
    except Exception as e:
        print("⚠️ Failed to load international options:", e)
        return JSONResponse(
            content={
                "commodities": ["Wheat", "Rice", "Maize", "Soybean"],
                "ports": ["Mumbai Port", "Kandla", "Chennai", "Novorossiysk"],
            }
        )


# ==========================================================
# 🌾 Snapshot Fetcher (for main.py prefetch)
# ==========================================================
async def fetch_terminal_snapshot(commodity: str = "wheat", location: str = "Indore"):
    try:
        key = commodity.lower()
        cached = CACHE["commodities"].get(key)
        if cached and cached.get("payload"):
            snapshot = cached["payload"].copy()
            snapshot["served_from_cache"] = True
            snapshot["cached_at"] = cached["timestamp"]
            return snapshot

        payload = assemble_terminal_payload(commodity, 53, location)
        CACHE["commodities"][key] = {
            "payload": payload,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        payload["served_from_cache"] = False
        return payload
    except Exception as e:
        print("⚠️ fetch_terminal_snapshot error:", e)
        return {
            "error": str(e),
            "commodity": commodity,
            "location": location,
            "served_from_cache": False,
        }
