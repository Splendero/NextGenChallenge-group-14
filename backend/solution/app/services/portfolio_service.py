from app.crm.client import CrmClient
from app.crm.mapper import map_portfolio
from app.currency import Conversion, NoExchangeRate, conversion
from app.models import PortfolioMetadata, PortfolioResponse

MONEY_FIELDS = ("total_market_value", "day_change_amount")


class PortfolioService:
    def __init__(self, crm: CrmClient):
        self._crm = crm

    async def get_metadata(self, portfolio_id: str) -> PortfolioMetadata:
        payload = await self._crm.fetch_portfolio(portfolio_id)
        return map_portfolio(payload, portfolio_id)

    async def get_portfolio(self, portfolio_id: str, currency: str | None = None) -> PortfolioResponse:
        metadata = await self.get_metadata(portfolio_id)
        values = metadata.model_dump()
        try:
            rate = conversion(metadata.currency, currency)
        except NoExchangeRate:
            rate = Conversion(metadata.currency, 1.0)
            values["warnings"] = [
                *metadata.warnings,
                f"no exchange rate from {metadata.currency} to {currency}; values are in {metadata.currency}",
            ]
        for field in MONEY_FIELDS:
            if values[field] is not None:
                values[field] = rate.convert(values[field])
        return PortfolioResponse(**{**values, "currency": rate.currency, "exchange_rate": rate.rate})
