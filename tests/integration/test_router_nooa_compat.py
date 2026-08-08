import os

import pytest

from app.config import get_settings
from app.llm import build_nooa_router_llm


@pytest.mark.integration
@pytest.mark.asyncio
async def test_router_accepts_nooa_compatible_tool_request() -> None:
    """Opt-in compatibility gate; it never contacts a cloud provider."""
    if os.getenv("RUN_LIVE_ROUTER_TESTS") != "1":
        pytest.skip("set RUN_LIVE_ROUTER_TESTS=1 with the local Router running")
    llm = build_nooa_router_llm(get_settings())
    assert llm is not None
