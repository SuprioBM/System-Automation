def resume_modify_prompt(context: dict) -> str:
    return f"""
You are an expert ATS resume engineer.

You are given:
- Existing resume bullets generated from a software project
- Original project context (analysis metadata)
- A user modification instruction

Your job is to MODIFY the resume bullets ONLY based on the instruction.

--------------------
INPUT DATA
--------------------
{context}

--------------------
TASK
--------------------

Modify the resume bullets while ensuring:

### STRICT RULES
- Must remain FULLY ATS OPTIMIZED
- Must use strong action verbs (Built, Designed, Engineered, Implemented, Developed)
- Must include technical keywords where relevant
- Must be concise and recruiter-scannable
- Must preserve technical accuracy from original project
- DO NOT add storytelling or LinkedIn-style writing
- DO NOT change meaning of project
- DO NOT invent new features not present in context

--------------------
OUTPUT REQUIREMENTS
--------------------

Return ONLY:

{
  "resume_bullets": [str]
}

RULES:
- Output ONLY valid JSON
- No markdown
- No explanations
"""