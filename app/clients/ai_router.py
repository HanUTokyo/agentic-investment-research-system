from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.clients.errors import UpstreamProtocolError, UpstreamServiceError, UpstreamTimeoutError
from app.config import Settings


class RouteDecision(BaseModel):
    route: str
    selected_model: str | None = None
    latency_ms: float | None = None
    source: str | None = None


class RoutedCompletion(BaseModel):
    content: str
    route: str | None = None
    model: str | None = None
    latency_ms: float
    raw: dict[str, Any] = Field(repr=False)


class RouterClient:
    """Small adapter for the existing Router; it never classifies locally."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.ai_router_api_key:
            headers["X-API-Key"] = settings.ai_router_api_key
        self._client = client or httpx.AsyncClient(
            base_url=str(settings.ai_router_base_url).rstrip("/"),
            headers=headers,
            timeout=settings.http_timeout_seconds,
        )
        self._logical_model = settings.ai_router_logical_model
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def readiness(self) -> bool:
        try:
            return (await self._client.get("/health/ready")).is_success
        except httpx.HTTPError:
            return False

    async def route(self, message: str) -> RouteDecision:
        response = await self._request("/route", {"message": message})
        try:
            return RouteDecision.model_validate(response)
        except Exception as exc:
            raise UpstreamProtocolError("router returned an invalid route decision") from exc

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> RoutedCompletion:
        started = perf_counter()
        payload = {"model": self._logical_model, "messages": messages, "stream": False, **kwargs}
        response = await self._request("/v1/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("content is not text")
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamProtocolError("router returned an invalid chat completion") from exc
        return RoutedCompletion(
            content=content,
            route=response.get("route"),
            model=response.get("model"),
            latency_ms=(perf_counter() - started) * 1000,
            raw=response,
        )

    async def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("router request timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("router request failed") from exc
        if not response.is_success:
            raise UpstreamServiceError(f"router returned HTTP {response.status_code}")
        try:
            decoded = response.json()
        except ValueError as exc:
            raise UpstreamProtocolError("router returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise UpstreamProtocolError("router returned a non-object JSON body")
        return decoded
