import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        stock_platform_base_url="http://stock.test", ai_router_base_url="http://router.test"
    )
