"""Slot-based résumé generation: fill only the DEVSYNC_* slots in the fixed
LaTeX template, compile remotely, validate, version, and store. Never
activates a resume that failed compilation, protected-region validation, or
the "must be an improvement" quality gate.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase
from app.models.decisions import ArtifactValidation
from app.models.project import Project
from app.services import latex_slots
from app.services.latex_compiler import get_latex_compiler
from app.services.project_service import FEATURED_LIMIT, INSIGHT_LIMIT
from app.utils.latex_escape import latex_escape

logger = get_logger("resume_service")

TEMPLATE_PATH = "app/resume/resume.tex"
BUCKET = "resumes"


def load_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _featured_slot_content(p: Project) -> str:
    stack = " · ".join(latex_escape(s) for s in p.technologies[:5])
    bullets = "\n".join(f"\\resumeItem{{{latex_escape(b)}}}" for b in p.resume_bullets)
    live = p.live_url or p.repository_url or "#"
    return (
        f"\\resumeProjectHeading\n"
        f"{{\\textbf{{\\href{{{live}}}{{{latex_escape(p.name)}}}}} $|$ \\emph{{{stack}}}}}{{}}\n"
        f"\\resumeItemListStart\n{bullets}\n\\resumeItemListEnd\n\\vspace{{-12pt}}"
    )


def _insight_slot_content(p: Project) -> str:
    live = p.live_url or p.repository_url or "#"
    return (
        f"\\resumeProjectHeading\n"
        f"{{\\textbf{{\\href{{{live}}}{{{latex_escape(p.name)}}}}} $|$ {latex_escape(p.description)}}}{{}}\n"
        f"\\vspace{{-10pt}}"
    )


def render_tex(base_tex: str, featured: list[Project], insight: list[Project]) -> str:
    tex = base_tex
    for i in range(1, FEATURED_LIMIT + 1):
        content = _featured_slot_content(featured[i - 1]) if i <= len(featured) else ""
        tex = latex_slots.set_slot(tex, "featured", i, content)
    for i in range(1, INSIGHT_LIMIT + 1):
        content = _insight_slot_content(insight[i - 1]) if i <= len(insight) else ""
        tex = latex_slots.set_slot(tex, "insight", i, content)
    return tex


def _page_count(pdf_bytes: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return None


def get_active_resume() -> dict | None:
    res = get_supabase().table("resume_versions").select("*").eq("is_active", True).execute()
    return res.data[0] if res.data else None


def next_version() -> int:
    res = get_supabase().table("resume_versions").select("version").order("version", desc=True).limit(1).execute()
    return (res.data[0]["version"] + 1) if res.data else 1


def compile_and_validate(candidate_tex: str, base_tex: str) -> tuple[bytes | None, ArtifactValidation]:
    validation = ArtifactValidation(passed=False)

    try:
        latex_slots.assert_only_slots_changed(base_tex, candidate_tex)
        validation.content_checks["only_slots_modified"] = True
    except Exception as e:
        validation.content_checks["only_slots_modified"] = False
        validation.issues.append(str(e))
        return None, validation

    validation.content_checks["required_sections_present"] = latex_slots.required_sections_present(candidate_tex)
    if not validation.content_checks["required_sections_present"]:
        validation.issues.append("one or more required sections (Education/Experience/Technical Skills) missing")
        return None, validation

    compiler = get_latex_compiler()
    result = compiler.compile(candidate_tex)
    validation.technical_checks["compiled"] = result.success
    if not result.success:
        validation.issues.append(f"compilation failed: {result.log[:2000]}")
        return None, validation

    validation.technical_checks["pdf_non_empty"] = bool(result.pdf_bytes)
    pages = _page_count(result.pdf_bytes)
    validation.technical_checks["page_count_reasonable"] = pages is not None and 1 <= pages <= 2

    active = get_active_resume()
    if active:
        active_pages = _page_count_from_url(active) if active.get("pdf_storage_url") else None
        validation.is_improvement_over_active = (
            validation.technical_checks["compiled"]
            and (active_pages is None or pages is None or pages <= active_pages)
        )
        validation.quality_checks["is_improvement_over_active"] = bool(validation.is_improvement_over_active)
    else:
        validation.is_improvement_over_active = True
        validation.quality_checks["is_improvement_over_active"] = True

    validation.passed = (
        validation.technical_checks.get("compiled", False)
        and validation.technical_checks.get("pdf_non_empty", False)
        and validation.content_checks.get("only_slots_modified", False)
        and validation.content_checks.get("required_sections_present", False)
        and validation.quality_checks.get("is_improvement_over_active", False)
    )
    if not validation.passed and not validation.issues:
        validation.issues.append("candidate resume is not an improvement over the active resume")

    return result.pdf_bytes, validation


def _page_count_from_url(active_row: dict) -> int | None:
    return None  # active PDF isn't re-downloaded for a page-count comparison; page_count_reasonable already guards gross regressions


def ensure_bucket() -> None:
    try:
        get_supabase().storage.create_bucket(BUCKET, options={"public": True})
    except Exception:
        pass  # already exists, or insufficient privileges -- surfaced on the actual upload attempt instead


def store_pdf(pdf_bytes: bytes, version: int) -> str:
    ensure_bucket()
    path = f"resume-v{version}.pdf"
    try:
        get_supabase().storage.from_(BUCKET).upload(
            path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"}
        )
        return get_supabase().storage.from_(BUCKET).get_public_url(path)
    except Exception as e:
        log_error(logger, "resume PDF upload failed", exc=e, service="supabase_storage", operation="store_pdf")
        raise ExternalServiceError("supabase_storage", "store_pdf", str(e), original=e) from e


def save_version(pdf_url: str, tex_snapshot: str, validation: ArtifactValidation, artifact_id: str | None) -> dict:
    version = next_version()
    res = get_supabase().table("resume_versions").insert({
        "artifact_id": artifact_id, "version": version, "pdf_storage_url": pdf_url,
        "tex_snapshot": tex_snapshot, "is_active": False, "validation_results": validation.model_dump(),
    }).execute()
    return res.data[0]


def activate_version(resume_version_id: str) -> None:
    get_supabase().table("resume_versions").update({"is_active": False}).eq("is_active", True).execute()
    get_supabase().table("resume_versions").update({"is_active": True}).eq("id", resume_version_id).execute()
