from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, detect, dashboard, terminal
from google import genai
import os, asyncio, time
from dotenv import load_dotenv
from utils.cache_manager import load_cache_from_disk, update_cache

load_dotenv()

app = FastAPI(title="AgriPulse Backend")

# ✅ Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://agri-pulse-frontend.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialize Gemini client (global)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ✅ Include routers
app.include_router(chat.router)
app.include_router(detect.router)
app.include_router(dashboard.router)
app.include_router(terminal.router)


@app.get("/")
def home():
    return {"message": "Welcome to AgriPulse API!"}


# ===============================================================
# 🚀 Background Prefetch System for Instant Dashboard/Terminal
# ===============================================================
@app.on_event("startup")
async def startup_event():
    """
    Runs at server start:
    - Loads existing cache from disk (if any)
    - Starts background refresh loop every few minutes
    """
    from routers.dashboard import fetch_dashboard_snapshot
    from routers.terminal import fetch_terminal_snapshot

    load_cache_from_disk()  # load old cache if available

    async def refresh_loop():
        while True:
            print("🔄 Refreshing cached data for dashboard & terminal...")
            try:
                dashboard_data = await fetch_dashboard_snapshot("Indore")
                await update_cache("dashboard", dashboard_data)

                terminal_data = await fetch_terminal_snapshot("wheat", "Indore")
                await update_cache("terminal", terminal_data)

                print("✅ Cache updated successfully at", time.strftime("%H:%M:%S"))
            except Exception as e:
                print("⚠️ Cache refresh error:", e)
            await asyncio.sleep(300)  # every 5 minutes

    asyncio.create_task(refresh_loop())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
