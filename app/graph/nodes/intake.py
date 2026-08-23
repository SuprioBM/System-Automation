from __future__ import annotations

from app.core.errors import ValidationFailure
from app.graph.util import node
from app.services import github_app
from app.utils.context_builder import build_repo_context


@node("receive_event")
def receive_event(state: dict) -> dict:
    if not state.get("repository") or not state.get("commit"):
        raise ValidationFailure("workflow state is missing repository/commit -- cannot proceed")
    return {"current_stage": "received"}


@node("load_repository_context")
def load_repository_context(state: dict) -> dict:
    owner, _, repo = state["repository"].partition("/")
    if not repo:
        owner, repo = state.get("user", owner), state["repository"]

    repo_data = github_app.get_repo_details(owner, repo, state.get("installation_id"))
    readme = github_app.get_repo_readme(owner, repo, state.get("installation_id"))

    context = build_repo_context(repo_data)
    project_data = {
        "owner": owner,
        "repository_url": repo_data.get("html_url", ""),
        "live_url": repo_data.get("homepage") or "",
        "source_commit": state["commit"],
        "source_repository": state["repository"],
        "context": context,
        "readme": readme,
    }
    return {"current_stage": "context_loaded", "project_data": project_data}
