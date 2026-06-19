import os
import uuid
from dotenv import load_dotenv

from app.services.discord_service import DiscordService
from app.utils.approval_view import ApprovalView

# ---------------- LOAD ENV ----------------
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

RESUME_CHANNEL = int(os.getenv("DISCORD_RESUME_CHANNEL_ID"))
LINKEDIN_CHANNEL = int(os.getenv("DISCORD_LINKEDIN_CHANNEL_ID"))

# ---------------- SAMPLE LINKEDIN TEXT ----------------
linkedin_text = """
Today I built a GitHub-driven automation system...
It connects FastAPI + Supabase + Discord...
"""

# ---------------- PATHS ----------------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
pdf_path = os.path.join(BASE_DIR, "resume", "generated", "resume.pdf")

# ---------------- MOCK AI CONTEXT (IMPORTANT FOR YOUR NEW SYSTEM) ----------------
# This replaces your missing analysis_data + resume_bullets issue
analysis_data = {
    "project": "GitHub automation system",
    "tech": ["FastAPI", "Supabase", "Discord"],
    "impact": "automation pipeline for portfolio generation"
}

resume_bullets = [
    "Built a GitHub-driven automation system using FastAPI and Supabase",
    "Engineered Discord-based approval workflow for AI-generated content",
    "Integrated backend automation pipeline with real-time interaction system"
]

# ---------------- DRAFT ID ----------------
draft_id = str(uuid.uuid4())
print(f"🆔 New draft_id for this run: {draft_id}")

# ---------------- INIT SERVICE ----------------
service = DiscordService(TOKEN, ApprovalView)

# ---------------- SEND DRAFT ----------------
service.send_draft(
    resume_channel=RESUME_CHANNEL,
    linkedin_channel=LINKEDIN_CHANNEL,
    linkedin_text=linkedin_text,
    pdf_path=pdf_path,
    draft_id=draft_id,
    analysis_data=analysis_data,
    resume_bullets=resume_bullets
)

# ---------------- START BOT ----------------
service.start()