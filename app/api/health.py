import asyncio

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.clients import RouterClient, StockPlatformClient
from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class ReadinessResponse(BaseModel):
    status: str
    stock_platform: str
    ai_router: str


def _clients(
    settings: Settings = Depends(get_settings),
) -> tuple[StockPlatformClient, RouterClient]:
    return StockPlatformClient(settings), RouterClient(settings)


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", response_model=ReadinessResponse)
async def ready(
    response: Response, clients: tuple[StockPlatformClient, RouterClient] = Depends(_clients)
) -> ReadinessResponse:
    stock_client, router_client = clients
    stock_ready, router_ready = await asyncio.gather(
        stock_client.readiness(), router_client.readiness()
    )
    await asyncio.gather(stock_client.aclose(), router_client.aclose())
    if not stock_ready or not router_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if stock_ready and router_ready else "degraded",
        stock_platform="ready" if stock_ready else "unavailable",
        ai_router="ready" if router_ready else "unavailable",
    )
