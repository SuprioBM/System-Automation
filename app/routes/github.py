from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.github_service import get_repo_details
from app.services.ai_analyzer import run_llm
from app.utils.trigger import should_trigger
from app.utils.extract_commit import extract_commit_message
from app.utils.extract_repoName import extract_repo_name
from app.utils.update_stage import update_stage
from app.utils.context_builder import build_repo_context
from app.prompt.analysis import analysis_prompt

router = APIRouter()


@router.post("/webhook")
async def github_webhook(request: Request):

    # Fresh status object for every request
    pipeline_status = {
        "webhook": {"success": False, "message": None},
        "github_fetch": {"success": False, "message": None},
        "readme_fetch": {"success": False, "message": None},
        "gemini": {"success": False, "message": None},
        "save": {"success": False, "message": None}
    }

    try:

        # ==================================================
        # 1. RECEIVE PAYLOAD
        # ==================================================
        try:
            payload = await request.json()

            update_stage(
                pipeline_status,
                "webhook",
                True,
                "Payload received"
            )

        except Exception as e:
            update_stage(
                pipeline_status,
                "webhook",
                False,
                str(e)
            )

            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Invalid JSON payload",
                    "error": str(e)
                }
            )

        print("📦 GitHub Payload received")

        # ==================================================
        # 2. EXTRACT DATA
        # ==================================================
        commit_message = extract_commit_message(payload)
        repo_name = extract_repo_name(payload)

        print("Commit:", commit_message)
        print("Repo:", repo_name)

        if not commit_message:
            return {
                "status": "ignored",
                "reason": "empty commit message"
            }

        if not repo_name:
            return {
                "status": "error",
                "reason": "repo not found"
            }

        # ==================================================
        # 3. TRIGGER CHECK
        # ==================================================
        if not should_trigger(commit_message):
            return {
                "status": "ignored",
                "reason": "publish:true not found",
                "commit": commit_message
            }

        # ==================================================
        # 4. FETCH REPO DATA
        # ==================================================
        repo_data = get_repo_details(repo_name)

        if "error" in repo_data:

            update_stage(
                pipeline_status,
                "github_fetch",
                False,
                str(repo_data)
            )

            return {
                "status": "error",
                "reason": "github fetch failed",
                "details": repo_data
            }

        update_stage(
            pipeline_status,
            "github_fetch",
            True,
            f"Fetched {repo_name}"
        )
        context = build_repo_context(repo_data)

        # ==================================================
        # 5. README FETCH
        # ==================================================
        # Placeholder for future implementation

        update_stage(
            pipeline_status,
            "readme_fetch",
            True,
            "Skipped (not implemented yet)"
        )

        # ==================================================
        # 6. AI ANALYSIS
        # ==================================================
        try:

            analysis = await run_llm(analysis_prompt(context), validate=True)
            if not analysis["success"]:
                update_stage(pipeline_status, "gemini", False, analysis["message"])
                return {
                    "status": "error",
                    "stage": "gemini",
                    "details": analysis
    }

            analysis = analysis["data"]

            update_stage(
                pipeline_status,
                "gemini",
                True,
                "Analysis completed"
            )

        except Exception as e:

            update_stage(
                pipeline_status,
                "gemini",
                False,
                str(e)
            )

            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "reason": "AI analysis failed",
                    "error": str(e)
                }
            )

        # ==================================================
        # 7. SAVE STAGE
        # ==================================================
        # Placeholder until DB storage exists

        update_stage(
            pipeline_status,
            "save",
            True,
            "Skipped (not implemented yet)"
        )

        # ==================================================
        # 8. SUCCESS RESPONSE
        # ==================================================
        return {
            "status": "processed",
            "repo": repo_name,
            "analysis": analysis
        }

    finally:

        print("\n====================")
        print("PIPELINE SUMMARY")
        print("====================")

        for stage, info in pipeline_status.items():

            icon = "✅" if info["success"] else "❌"

            print(
                f"{icon} {stage}: "
                f"{info['message']}"
            )