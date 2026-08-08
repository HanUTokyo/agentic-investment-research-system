from typing import Any

from app.config import Settings


def build_nooa_router_llm(settings: Settings) -> Any:
    """Build NOOA's LiteLLM-backed client against Router's OpenAI-compatible endpoint.

    This is deliberately the only model construction point. The Router chooses the
    actual local model; the logical model is never an Ollama model name.
    """

    from nooa.unifiedllm import get_llm_client

    api_base = f"{str(settings.ai_router_base_url).rstrip('/')}/v1"
    return get_llm_client(
        f"openai/{settings.ai_router_logical_model}",
        api_base=api_base,
        api_key=settings.ai_router_api_key or "local-router-no-key",
    )
