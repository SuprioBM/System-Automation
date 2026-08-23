"""Remote LaTeX compilation, replacing the local pdflatex dependency. Behind
a clean interface so the provider (currently YtoTech LaTeX-On-HTTP) can be
swapped without touching call sites. Never fakes a successful compile: a
provider failure raises ExternalServiceError with the compiler's own log
output preserved.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from app.core.config import settings
from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.retry import with_retries


@dataclass
class CompileResult:
    success: bool
    pdf_bytes: bytes | None
    log: str


class LatexCompiler(ABC):
    @abstractmethod
    def compile(self, tex_source: str) -> CompileResult: ...


class YtoTechCompiler(LatexCompiler):
    def __init__(self, url: str, api_token: str | None):
        self.url = url
        self.api_token = api_token

    @with_retries("ytotech", "compile", exceptions=(requests.ConnectionError, requests.Timeout))
    def compile(self, tex_source: str) -> CompileResult:
        payload = {"compiler": "pdflatex", "resources": [{"main": True, "content": tex_source}]}
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            res = requests.post(self.url, json=payload, headers=headers, timeout=60)
        except (requests.ConnectionError, requests.Timeout):
            raise
        except requests.RequestException as e:
            raise ExternalServiceError("ytotech", "compile", str(e), original=e) from e

        content_type = res.headers.get("content-type", "")
        if res.status_code == 201 and "application/pdf" in content_type:
            return CompileResult(success=True, pdf_bytes=res.content, log="")

        # Failure: YtoTech returns a JSON body describing the compile error.
        try:
            body = res.json()
            log = body.get("logs") or body.get("error") or str(body)
        except ValueError:
            log = res.text
        return CompileResult(success=False, pdf_bytes=None, log=log)


def get_latex_compiler() -> LatexCompiler:
    provider = (settings.LATEX_COMPILER_PROVIDER or "ytotech").lower()
    if provider == "ytotech":
        if not settings.LATEX_COMPILER_URL:
            raise ConfigurationError("LATEX_COMPILER_URL is not set")
        return YtoTechCompiler(settings.LATEX_COMPILER_URL, settings.LATEX_COMPILER_API_TOKEN)
    raise ConfigurationError(f"Unknown LATEX_COMPILER_PROVIDER: {provider}")
