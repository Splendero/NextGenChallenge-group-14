import re

from fastapi import APIRouter, Depends, Query

from app.currency import CURRENCY_QUERY_DESCRIPTION, UNSUPPORTED_CURRENCY_EXAMPLE, parse_currency
from app.dependencies import get_portfolio_service
from app.errors import InvalidPortfolioId
from app.models import ErrorResponse, PortfolioResponse
from app.services.portfolio_service import PortfolioService

router = APIRouter(tags=["portfolios"])

PORTFOLIO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def error_doc(description: str, example: dict) -> dict:
    return {"model": ErrorResponse, "description": description, "content": {"application/json": {"example": example}}}


def validate_portfolio_id(portfolio_id: str) -> None:
    if not PORTFOLIO_ID_PATTERN.fullmatch(portfolio_id):
        raise InvalidPortfolioId(
            "Portfolio id must be 1-64 characters: letters, digits, '-' or '_'.",
            details={"portfolioId": portfolio_id[:100]},
        )


@router.get(
    "/portfolios/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Portfolio metadata (sourced from the CRM)",
    responses={
        400: error_doc(
            "The id is not a valid portfolio id (invalid_portfolio_id), or currency is not CAD or USD. "
            "The CRM is not called.",
            UNSUPPORTED_CURRENCY_EXAMPLE,
        ),
        404: error_doc(
            "The CRM has no account with this id.",
            {"error": "portfolio_not_found", "message": "No portfolio found with id 'P-0000'.", "requestId": "..."},
        ),
        502: error_doc(
            "The CRM answered with data that could not be interpreted safely.",
            {"error": "crm_bad_response", "message": "...", "requestId": "...", "details": {"reason": "..."}},
        ),
        503: error_doc(
            "The CRM is down or returned a server error (after one retry). Includes Retry-After.",
            {"error": "crm_unavailable", "message": "...", "requestId": "...", "details": {"upstreamStatus": 503}},
        ),
        504: error_doc(
            "The CRM did not respond within the timeout.",
            {"error": "crm_timeout", "message": "...", "requestId": "...", "details": {"timeoutSeconds": 3}},
        ),
    },
)
async def get_portfolio(
    portfolio_id: str,
    currency: str | None = Query(default=None, description=CURRENCY_QUERY_DESCRIPTION),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioResponse:
    validate_portfolio_id(portfolio_id)
    return await service.get_portfolio(portfolio_id, parse_currency(currency))
