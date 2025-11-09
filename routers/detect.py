from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from google import genai
import os
import io
import base64
import json
import asyncio
from dotenv import load_dotenv
from PIL import Image

# --- Setup ---
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

router = APIRouter(prefix="/detect", tags=["Disease Detection"])


# ======================================================
# 🌿 AI Leaf Disease Detection Endpoint
# ======================================================
@router.post("/")
async def detect_disease(file: UploadFile = File(...)):
    """
    Analyze an uploaded crop leaf image using Google Gemini Vision model.
    Returns detected disease, confidence, and treatment suggestions.
    """

    try:
        # ✅ Step 1: Read uploaded image into memory
        contents = await file.read()

        # ✅ Step 2: Validate it’s a real image
        try:
            Image.open(io.BytesIO(contents))
        except Exception:
            raise HTTPException(
                status_code=400, detail="Uploaded file is not a valid image"
            )

        # ✅ Step 3: Encode image to base64 for Gemini API
        encoded_image = base64.b64encode(contents).decode("utf-8")

        # ✅ Step 4: Construct expert AI prompt
        prompt = """
        You are an agricultural plant pathology expert AI.
        Analyze the uploaded crop leaf image carefully.

        Return a *pure JSON* object with:
        {
            "detected_disease": "name of disease or 'Healthy'",
            "confidence": "confidence percentage (integer 0–100)",
            "severity": "low | medium | high",
            "recommended_treatment": "practical treatment steps or 'No issue detected'"
        }

        Keep output concise and JSON only — no markdown, explanations, or extra text.
        """

        # ✅ Step 5: Run Gemini Vision model (async-safe)
        response = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": file.content_type or "image/jpeg",
                                    "data": encoded_image,
                                }
                            },
                        ],
                    }
                ],
            )
        )

        # ✅ Step 6: Get AI output text
        ai_output = response.text.strip()

        # ✅ Step 7: Try parsing JSON
        try:
            parsed = json.loads(ai_output)
        except json.JSONDecodeError:
            # Fallback to raw response
            parsed = {"raw_response": ai_output}

        # ✅ Step 8: Attach filename
        parsed["filename"] = file.filename

        return JSONResponse(content=parsed)

    except Exception as e:
        print("❌ Gemini error:", e)
        raise HTTPException(
            status_code=500, detail="AI analysis failed. Please try again."
        )
