from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, detect, dashboard, terminal
from google import genai
import os
import asyncio
import time
from dotenv import load_dotenv
from utils.cache_manager import load_cache_from_disk, update_cache

# ===============================================================
# 🌱 Environment Setup
# ===============================================================
load_dotenv()

app = FastAPI(
    title="AgriPulse Backend",
    description="AI-driven Agriculture Intelligence API",
    version="1.0.0",
)

# ===============================================================
# 🌐 CORS Configuration
# ===============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://frontend-agripulse.vercel.app",  # ✅ remove trailing slash
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================================================
# 🤖 Initialize Gemini Client (global singleton)
# ===============================================================
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ===============================================================
# 🧩 Include Routers
# ===============================================================
app.include_router(chat.router)
app.include_router(detect.router)
app.include_router(dashboard.router)
app.include_router(terminal.router)


# ===============================================================
# 🏠 Root Endpoint
# ===============================================================
@app.get("/")
def home():
    return {
        "message": "Welcome to AgriPulse API 🚜",
        "routes": ["/chat", "/dashboard", "/detect", "/terminal"],
    }


# ===============================================================
# 🚀 Background Prefetch + Cache System
# ===============================================================
@app.on_event("startup")
async def startup_event():
    """
    On startup:
    - Loads existing cache from disk (if any)
    - Starts background refresh loop (every 5 minutes)
    """
    from routers.dashboard import fetch_dashboard_snapshot
    from routers.terminal import fetch_terminal_snapshot

    try:
        load_cache_from_disk()
        print("✅ Cache loaded from disk.")
    except Exception as e:
        print("⚠️ No cache found or failed to load:", e)

    async def refresh_loop():
        while True:
            print("🔄 Refreshing cached data for dashboard & terminal...")
            try:
                # Dashboard prefetch
                dashboard_data = await fetch_dashboard_snapshot("Indore")
                await update_cache("dashboard", dashboard_data)

                # Terminal prefetch
                terminal_data = await fetch_terminal_snapshot("wheat", "Indore")
                await update_cache("terminal", terminal_data)

                print(f"✅ Cache updated successfully at {time.strftime('%H:%M:%S')}")
            except Exception as e:
                print("⚠️ Cache refresh error:", e)
            await asyncio.sleep(300)  # every 5 minutes

    asyncio.create_task(refresh_loop())


# ===============================================================
# 🏁 Local Run (Render handles uvicorn automatically)
# ===============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
