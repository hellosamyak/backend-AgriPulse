from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from google import genai
from functools import lru_cache
import httpx
import os
import datetime
import json
import asyncio
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# --- API Keys ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Initialize Gemini Client ---
client = genai.Client(api_key=GEMINI_API_KEY)


# ======================================================
# 🧠 DASHBOARD ENDPOINT (ASYNC)
# ======================================================
@router.get("/")
async def get_dashboard(location: str = "Indore"):
    """
    Fetches:
    - Live weather (WeatherAPI)
    - Market prices (data.gov.in)
    - AI summaries and insights (Gemini)
    """
    try:
        # Run weather + mandi concurrently
        weather_task = asyncio.create_task(fetch_weather_data_async(location))
        mandi_task = asyncio.create_task(fetch_mandi_data_async(location))
        weather_data, mandi_data = await asyncio.gather(weather_task, mandi_task)

        # Static placeholder news (could also be cached)
        news_data = [
            {
                "headline": "Govt raises MSP for wheat by ₹150/quintal",
                "summary": "Government increases wheat MSP to boost Rabi season earnings.",
                "sentiment": "positive",
            },
            {
                "headline": "Rainfall expected in Northern India this weekend",
                "summary": "IMD predicts moderate rain, farmers advised to delay sowing by 2 days.",
                "sentiment": "neutral",
            },
            {
                "headline": "Soybean exports rise 8% amid global demand",
                "summary": "Soybean prices surge as exports grow globally.",
                "sentiment": "positive",
            },
        ]

        # Run Gemini summarization concurrently
        summary_task = asyncio.create_task(
            generate_ai_summary_async(location, weather_data, mandi_data, news_data)
        )
        insights_task = asyncio.create_task(
            generate_multi_crop_insights_async(location, weather_data, mandi_data)
        )
        ai_summary, ai_crop_insights = await asyncio.gather(summary_task, insights_task)

        dashboard_data = {
            "date": datetime.datetime.now().strftime("%d %b %Y"),
            "location": location,
            "weather": weather_data,
            "market_data": mandi_data,
            "news": news_data,
            "ai_summary": ai_summary,
            "ai_crop_insights": ai_crop_insights,
        }

        return JSONResponse(content=dashboard_data)

    except Exception as e:
        print("❌ Dashboard Error:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================
# 🌤️ WEATHER DATA (ASYNC + CACHE)
# ======================================================
@lru_cache(maxsize=32)
async def fetch_weather_data_async(location: str):
    try:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days=7&aqi=no&alerts=no"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(url)
            res.raise_for_status()
            data = res.json()

        current = data.get("current", {})
        forecast_days = data.get("forecast", {}).get("forecastday", [])

        return {
            "location": data.get("location", {}).get("name", location),
            "country": data.get("location", {}).get("country", "India"),
            "current": {
                "temp_c": current.get("temp_c"),
                "condition": current.get("condition", {}).get("text"),
                "icon": current.get("condition", {}).get("icon"),
                "humidity": current.get("humidity"),
                "wind_kph": current.get("wind_kph"),
                "precip_mm": current.get("precip_mm"),
            },
            "astro": {
                "sunrise": forecast_days[0].get("astro", {}).get("sunrise", ""),
                "sunset": forecast_days[0].get("astro", {}).get("sunset", ""),
            },
            "forecast": [
                {
                    "date": d["date"],
                    "avgtemp_c": d["day"]["avgtemp_c"],
                    "totalprecip_mm": d["day"]["totalprecip_mm"],
                    "avghumidity": d["day"]["avghumidity"],
                    "condition": d["day"]["condition"]["text"],
                    "icon": d["day"]["condition"]["icon"],
                    "daily_chance_of_rain": d["day"]["daily_chance_of_rain"],
                }
                for d in forecast_days
            ],
        }
    except Exception as e:
        print("⚠️ WeatherAPI fallback:", e)
        return {
            "location": location,
            "country": "India",
            "current": {"temp_c": 30, "condition": "Clear", "humidity": 60},
            "astro": {"sunrise": "06:30 AM", "sunset": "05:45 PM"},
            "forecast": [],
        }


# ======================================================
# 📊 MARKET DATA (ASYNC + CACHE)
# ======================================================
@lru_cache(maxsize=32)
async def fetch_mandi_data_async(location: str):
    try:
        url = "https://data.gov.in"
        params = {
            "api-key": DATA_GOV_API_KEY,
            "format": "json",
            "limit": 10,
            "filters[market]": location,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            records = res.json().get("records", [])

        if not records:
            raise ValueError("No mandi data found")

        return [
            {
                "commodity": r.get("commodity", "Unknown"),
                "market": r.get("market", location),
                "modal_price": float(r.get("modal_price", 0)),
                "max_price": float(r.get("max_price", 0)),
                "min_price": float(r.get("min_price", 0)),
                "arrival_date": r.get("arrival_date", ""),
            }
            for r in records
        ]
    except Exception as e:
        print("⚠️ Mandi fallback:", e)
        return [
            {"commodity": "Wheat", "market": location, "modal_price": 2300},
            {"commodity": "Soybean", "market": location, "modal_price": 5200},
            {"commodity": "Maize", "market": location, "modal_price": 1850},
        ]


# ======================================================
# 🧠 GEMINI AI SUMMARIES (ASYNC)
# ======================================================
async def generate_ai_summary_async(location, weather, market, news):
    try:
        prompt = f"""
You are AgriPulse AI — India's agriculture advisor.
Analyze real data and summarize for farmers in {location}:

Weather: {weather}
Market: {market[:5]}
News: {news[:3]}

Give:
1️⃣ Weather Outlook
2️⃣ Market Trends
3️⃣ Weekly Advisory

Keep it factual, under 100 words, friendly tone.
"""
        result = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
        )
        return result.text.strip()
    except Exception as e:
        print("⚠️ Gemini summary fallback:", e)
        return "Stable weather and moderate market trends this week. Monitor rainfall and wheat prices."


# ======================================================
# 🌾 GEMINI MULTI-CROP INSIGHTS (ASYNC)
# ======================================================
async def generate_multi_crop_insights_async(location, weather, market):
    try:
        prompt = f"""
You are AgriPulse AI — a data-driven crop advisor.
Analyze:
- Weather: {weather}
- Mandi: {market[:5]}

Output top 3 crops to *plant or sell* this week, strictly in JSON:
[{{"crop":"Wheat","recommendation_type":"sell","confidence":85,"reason":["Good MSP","Stable yield"]}},...]
"""
        response = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
        )

        try:
            crops = json.loads(response.text.strip())
            if isinstance(crops, list):
                return crops
            raise ValueError("Invalid format")
        except Exception:
            return [
                {
                    "crop": "Soybean",
                    "confidence": 90,
                    "reason": "High demand & good rainfall",
                },
                {
                    "crop": "Wheat",
                    "confidence": 85,
                    "reason": "Rising MSP & steady market",
                },
                {
                    "crop": "Maize",
                    "confidence": 78,
                    "reason": "Stable yield & export demand",
                },
            ]

    except Exception as e:
        print("⚠️ Gemini Crop Fallback:", e)
        return [
            {"crop": "Wheat", "confidence": 80, "reason": "Favorable conditions"},
            {"crop": "Maize", "confidence": 75, "reason": "Moderate temperatures"},
            {"crop": "Soybean", "confidence": 70, "reason": "Stable market rates"},
        ]


async def fetch_dashboard_snapshot(location="Indore"):
    weather = await fetch_weather_data_async(location)
    mandi = await fetch_mandi_data_async(location)
    ai_summary = await generate_ai_summary_async(location, weather, mandi, [])
    ai_crop_insights = await generate_multi_crop_insights_async(
        location, weather, mandi
    )
    return {
        "date": datetime.datetime.now().strftime("%d %b %Y"),
        "location": location,
        "weather": weather,
        "market_data": mandi,
        "ai_summary": ai_summary,
        "ai_crop_insights": ai_crop_insights,
    }


@router.get("/cached")
async def get_cached_dashboard():
    from utils.cache_manager import get_cache

    cache = get_cache()
    data = cache.get("dashboard")
    if data:
        return JSONResponse(content=data)
    else:
        raise HTTPException(status_code=503, detail="Cache not ready yet")
