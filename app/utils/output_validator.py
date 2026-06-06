# app/services/output_validator.py

from app.schemas.repo_analysis import RepoAnalysis


def validate_analysis(data: dict):

    return RepoAnalysis.model_validate(data)