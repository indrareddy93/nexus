"""AI Middleware — request classification and response summarization."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from nexus.ai.engine import AIEngine
from nexus.core.request import Request
from nexus.core.response import JSONResponse, Response
from nexus.middleware.base import BaseMiddleware

logger = logging.getLogger("nexus.ai.middleware")


class AIMiddleware(BaseMiddleware):
    """
    AI-powered middleware that can:
    - Classify incoming requests (spam detection, intent detection, moderation)
    - Summarize/transform outgoing JSON responses
    - Add AI-generated metadata to responses

    Usage::

        app.add_middleware(
            AIMiddleware,
            ai=AIEngine(provider="openai", api_key="sk-..."),
            classify_requests=True,
            summarize_responses=False,
        )
    """

    def __init__(
        self,
        call_next: Callable,
        *,
        ai: AIEngine,
        classify_requests: bool = False,
        summarize_responses: bool = False,
        moderation_paths: list[str] | None = None,
        classification_prompt: str | None = None,
    ) -> None:
        super().__init__(call_next)
        self.ai = ai
        self.classify_requests = classify_requests
        self.summarize_responses = summarize_responses
        self.moderation_paths: set[str] = set(moderation_paths or [])
        self.classification_prompt = classification_prompt or (
            "Classify this HTTP request as one of: [normal, suspicious, spam, bot]. "
            "Reply with just the label.\n\n"
            "Method: {method}\nPath: {path}\nBody: {body}"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Request classification
        if self.classify_requests and request.path in self.moderation_paths:
            classification = await self._classify_request(request)
            if classification in ("suspicious", "spam", "bot"):
                logger.warning(
                    "AI classified request as %r: %s %s",
                    classification, request.method, request.path,
                )
                return Response(
                    json.dumps({"error": "Request blocked by AI moderation", "reason": classification}),
                    status_code=403,
                    content_type="application/json",
                )

        response = await call_next(request)

        # Response summarization
        if self.summarize_responses and isinstance(response, JSONResponse):
            response = await self._summarize_response(response)

        return response

    async def _classify_request(self, request: Request) -> str:
        try:
            body = ""
            if request.method in ("POST", "PUT", "PATCH"):
                raw = await request.body()
                body = raw.decode("utf-8", errors="replace")[:500]

            prompt = self.classification_prompt.format(
                method=request.method,
                path=request.path,
                body=body or "(empty)",
            )
            response = await self.ai.generate(prompt, max_tokens=20)
            label = response.content.strip().lower()
            return label if label in ("normal", "suspicious", "spam", "bot") else "normal"
        except Exception as exc:
            logger.error("AI classification failed: %s", exc)
            return "normal"

    async def _summarize_response(self, response: JSONResponse) -> JSONResponse:
        try:
            data = response.data
            prompt = (
                "Summarize this JSON API response in one sentence:\n"
                + json.dumps(data, default=str)[:1000]
            )
            summary = await self.ai.generate(prompt, max_tokens=100)
            if isinstance(data, dict):
                data["_ai_summary"] = summary.content
                return JSONResponse(data, status_code=response.status_code)
        except Exception as exc:
            logger.error("AI summarization failed: %s", exc)
        return response
