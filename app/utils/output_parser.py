# app/services/output_parser.py

import json


def parse_ai_response(raw_text: str):

    try:
        return json.loads(raw_text)

    except Exception as e:
        raise Exception(
            f"Invalid Gemini JSON:\n{raw_text}"
        )