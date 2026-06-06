# app/prompts/repo_analysis_prompt.py

def analysis_prompt(context: dict) -> str:
    return f"""
You are a senior software engineer portfolio analyzer.

Repository:

{context}

Return ONLY JSON.

Schema:

{{
  "project_score": int,
  "impact_level": str,
  "summary": str,
  "skills_used": [str],
  "portfolio_recommendation": bool,
  "resume_bullets": [str],
  "linkedin_angle": str,
  "tags": [str]
}}

Rules:
- Output ONLY valid JSON
- No markdown
- No explanations
- No code fences
"""