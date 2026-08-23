"""Groq adapter via LangChain (ChatGroq). Single chokepoint for all LLM
calls in the system -- model/provider is fully configurable through env vars
(GROQ_API_KEY, GROQ_MODEL), never hard-coded. Every call returns a validated
Pydantic object, never raw trusted-as-is model text, so a node's decision
logic never has to parse free text itself.
"""
from __future__ import annotations

from typing import Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from app.core.config import require, settings
from app.core.errors import ExternalServiceError, ValidationFailure
from app.core.logging import get_logger
from app.core.retry import with_retries

logger = get_logger("groq")

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_MESSAGE_MARKERS = ("rate limit", "429", "timeout", "connection", "503", "502")


def _model(temperature: float = 0.0) -> ChatGroq:
    require("GROQ_API_KEY")
    return ChatGroq(model=settings.GROQ_MODEL, api_key=settings.GROQ_API_KEY, temperature=temperature)


def _is_retryable(exc: BaseException) -> bool:
    return any(marker in str(exc).lower() for marker in _RETRYABLE_MESSAGE_MARKERS)


def structured_call(
    system_prompt: str,
    user_prompt: str,
    schema: Type[T],
    *,
    temperature: float = 0.0,
    operation: str = "structured_call",
) -> T:
    """Call Groq and force the response into `schema`. Raises
    ExternalServiceError on provider failure, ValidationFailure if the model
    genuinely cannot produce a conforming response."""

    @with_retries("groq", operation, exceptions=(ExternalServiceError,))
    def _call() -> T:
        model = _model(temperature).with_structured_output(schema)
        try:
            result = model.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        except ValidationError as e:
            raise ValidationFailure(f"Groq response did not match {schema.__name__}: {e}") from e
        except Exception as e:
            if _is_retryable(e):
                raise ExternalServiceError("groq", operation, str(e), original=e) from e
            raise ExternalServiceError("groq", operation, str(e), original=e) from e
        if not isinstance(result, schema):
            raise ValidationFailure(f"Groq structured output for {operation} was not a {schema.__name__}")
        return result

    return _call()
