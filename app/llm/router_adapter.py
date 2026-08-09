from typing import Any, Literal

from app.config import Settings

RouteHint = Literal["chat", "reason", "code"]


def build_nooa_router_llm(settings: Settings, *, route_hint: RouteHint | None = None) -> Any:
    """Build NOOA's LiteLLM-backed client against Router's OpenAI-compatible endpoint.

    This is deliberately the only model construction point. The Router chooses the
    actual local model; the logical model is never an Ollama model name.  CodeAct
    callers may provide a Router-owned route hint.  It is not a model name and
    does not duplicate Router classification rules.
    """

    from nooa.unifiedllm import get_llm_client
    from nooa.unifiedllm.retry_config import RetryConfig

    api_base = f"{str(settings.ai_router_base_url).rstrip('/')}/v1"
    overrides: dict[str, Any] = {
        "api_base": api_base,
        "api_key": settings.ai_router_api_key or "local-router-no-key",
        # Phase 1 is intentionally serial.  Retrying an already slow local
        # model behind a client timeout can overlap work on a single device.
        "retry_config": RetryConfig(max_retries=0),
    }
    if route_hint is not None:
        # LiteLLM forwards OpenAI-compatible extra_body fields unchanged.
        overrides["extra_body"] = {"route_hint": route_hint}
    return get_llm_client(
        f"openai/{settings.ai_router_logical_model}",
        **overrides,
    )


def build_nooa_controller_llm(settings: Settings) -> Any:
    """Build the direct, tool-capable Ministral NOOA controller.

    The Controller is deliberately separate from Router worker delegation. In
    the Docker experiment it reaches Ollama only through controller-proxy.
    """
    from nooa.unifiedllm import get_llm_client
    from nooa.unifiedllm.retry_config import RetryConfig

    return get_llm_client(
        f"openai/{settings.ministral_controller_model}",
        api_base=str(settings.ministral_controller_base_url).rstrip("/"),
        api_key="local-ollama-no-key",
        retry_config=RetryConfig(max_retries=0),
    )
