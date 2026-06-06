from google import genai

from app.core.config import GEMINI_API_KEY

from app.utils.output_parser import parse_ai_response
from app.utils.output_validator import validate_analysis
from app.prompt.v1 import analysis_prompt


client = genai.Client(api_key=GEMINI_API_KEY)



async def analyze_repo(context: dict):

    prompt = analysis_prompt(context)

    try:
        print("🧠 Sending request to Gemini...")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json"
            }
        )

        print("📩 Raw Gemini Response:")
        print(response.text)

        parsed = parse_ai_response(response.text)

        validated = validate_analysis(parsed)

        print("✅ Gemini output validated")

        return {
            "success": True,
            "data": validated.model_dump()
        }

    except Exception as e:

        print("❌ AI ANALYSIS FAILED")
        print(str(e))

        return {
            "success": False,
            "error": "gemini_failed",
            "message": str(e),
            "data": None
        }