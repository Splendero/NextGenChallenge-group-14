from app.calculations.holdings import compute_holdings
from app.currency import Conversion, conversion
from app.data import seed
from app.errors import PortfolioNotFound
from app.models import Holding

MONEY_FIELDS = (
    "cost_basis_per_share",
    "price",
    "previous_close_price",
    "market_value",
    "unrealized_gain_loss",
    "day_change_amount",
)


class HoldingsService:
    def get_holdings(self, portfolio_id: str, currency: str | None = None) -> list[Holding]:
        portfolio = seed.get_portfolio(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFound(f"No portfolio found with id '{portfolio_id}'.")
        rate = conversion(portfolio["currency"], currency)
        return [_to_response(row, rate) for row in compute_holdings(seed.holdings_for(portfolio_id))]


def _to_response(row: dict, rate: Conversion) -> Holding:
    money = {field: rate.convert(row[field]) for field in MONEY_FIELDS}
    return Holding(**{**row, **money, "currency": rate.currency, "exchange_rate": rate.rate})
