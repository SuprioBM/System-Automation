from google import genai
from app.core.config import GEMINI_API_KEY
from app.utils.output_parser import parse_ai_response
from app.utils.output_validator import validate_analysis

client = genai.Client(api_key=GEMINI_API_KEY)


async def run_llm(prompt: str, validate: bool = False):
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

        # optional validation (only for structured outputs like GitHub analysis)
        if validate:
            parsed = validate_analysis(parsed).model_dump()

        return {
            "success": True,
            "data": parsed
        }

    except Exception as e:
        print("❌ LLM CALL FAILED")
        print(str(e))

        return {
            "success": False,
            "error": "gemini_failed",
            "message": str(e),
            "data": None
        }