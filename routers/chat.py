from fastapi import APIRouter, HTTPException, Request
from google import genai
import os
import asyncio
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

# --- Initialize Gemini Client ---
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- Router ---
router = APIRouter(prefix="/chat", tags=["AI Chatbot"])


# ======================================================
# 🤖 AI Chatbot (POST)
# ======================================================
@router.post("/")
async def chat(request: Request):
    """
    AI Chatbot endpoint for farmers using Gemini.
    Accepts JSON with 'message' key.
    Example:
    {
        "message": "What crop should I plant next month in Madhya Pradesh?"
    }
    """
    try:
        data = await request.json()
        message = data.get("message", "").strip()

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # 🌾 Optimized prompt for farmer-friendly responses
        prompt = f"""
        You are AgriPulse AI — an agriculture expert designed to assist Indian farmers.
        Your goal is to give practical, location-aware, and concise answers.
        Use simple English and local context for clarity.

        Guidelines:
        - Base advice on Indian weather, soil type, and season.
        - When asked about crop choices, include 2–3 options with reasoning.
        - When asked about diseases, suggest natural and chemical control.
        - When asked about prices, mention market trends and storage tips.
        - When asked about schemes or subsidies, summarize simply.

        Farmer's question:
        {message}
        """

        # ✅ Run Gemini sync call in background thread
        response = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
        )

        return {"response": response.text.strip()}

    except Exception as e:
        print("❌ Gemini Chat Error:", e)
        raise HTTPException(
            status_code=500, detail="AI response failed. Please try again later."
        )


# ======================================================
# 🩺 Health Check (GET)
# ======================================================
@router.get("/")
def chat_health():
    return {
        "message": "✅ Chat endpoint active. Use POST /chat/ with JSON body to talk to AgriPulse AI."
    }
