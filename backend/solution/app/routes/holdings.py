from fastapi import APIRouter, Depends, Query

from app.currency import CURRENCY_QUERY_DESCRIPTION, UNSUPPORTED_CURRENCY_EXAMPLE, parse_currency
from app.dependencies import get_holdings_service
from app.models import ErrorResponse, Holding
from app.services.holdings_service import HoldingsService

router = APIRouter(tags=["holdings"])


@router.get(
    "/portfolios/{portfolio_id}/holdings",
    response_model=list[Holding],
    summary="Holdings with server-side valuation and gain/loss",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "currency is not CAD or USD.",
            "content": {"application/json": {"example": UNSUPPORTED_CURRENCY_EXAMPLE}},
        },
        404: {
            "model": ErrorResponse,
            "description": "No portfolio with this id. A portfolio with no holdings returns [] instead.",
        },
    },
)
def get_holdings(
    portfolio_id: str,
    currency: str | None = Query(default=None, description=CURRENCY_QUERY_DESCRIPTION),
    service: HoldingsService = Depends(get_holdings_service),
) -> list[Holding]:
    return service.get_holdings(portfolio_id, parse_currency(currency))
