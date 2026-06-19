from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_analyzer import run_llm
from app.prompt.modify_resume import resume_modify_prompt
from app.prompt.modify_linkedln import linkedin_modify_prompt

router = APIRouter()


class DiscordApprovalRequest(BaseModel):
    draft_id: str
    action: str
    draft_type: str | None = None
    content: str | None = None
    feedback: str | None = None


@router.post("/discord/approval")
async def discord_approval(payload: DiscordApprovalRequest):

    print("🔥 RECEIVED FROM DISCORD BOT:")
    print(payload)

    # ---------------- APPROVE / REJECT ----------------
    if payload.action in ["approve", "reject"]:
        return {
            "status": "success",
            "draft_id": payload.draft_id,
            "action": payload.action
        }

    # ---------------- EDIT FLOW ----------------
    if payload.action == "edit":

        # safety check
        if not payload.draft_type:
            return {
                "status": "error",
                "message": "draft_type is required for edit"
            }

        context = {
            "content": payload.content,
            "instruction": payload.feedback
        }

        # ---------------- ROUTE TO CORRECT PROMPT ----------------
        if payload.draft_type == "resume":
            prompt = resume_modify_prompt(context)

        elif payload.draft_type == "linkedin":
            prompt = linkedin_modify_prompt(context)

        else:
            return {
                "status": "error",
                "message": "unknown draft_type"
            }

        # ---------------- AI CALL ----------------
        result = await run_llm(prompt, validate=False)

        return {
            "status": "success",
            "draft_id": payload.draft_id,
            "action": payload.action,
            "result": result["data"] if result["success"] else None,
            "error": result["error"] if not result["success"] else None,
        }

    return {
        "status": "ignored",
        "message": "unknown action"
    }