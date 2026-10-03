"""Display currency for money fields (Task 7).

Data is stored in each portfolio's native currency; `?currency=` asks for CAD or USD instead. Every money
field in a response is multiplied by the same rate and nothing is rounded, so converted holdings still add
up to the converted portfolio total. Quantities and percentages are never converted.
"""

from dataclasses import dataclass

from app.data import seed
from app.errors import UnsupportedCurrency

SUPPORTED_CURRENCIES = ("CAD", "USD")
CURRENCY_QUERY_DESCRIPTION = (
    "CAD or USD (exact match). Converts every money field; quantities and percentages are unchanged. "
    "Defaults to the portfolio's native currency."
)
UNSUPPORTED_CURRENCY_EXAMPLE = {
    "error": "unsupported_currency",
    "message": "currency must be one of CAD, USD.",
    "requestId": "...",
    "details": {"currency": "EUR", "allowed": ["CAD", "USD"]},
}


class NoExchangeRate(Exception):
    """There is no rate between the portfolio's native currency and the requested one."""


@dataclass(frozen=True)
class Conversion:
    currency: str
    rate: float

    def convert(self, amount: float) -> float:
        return amount * self.rate


def parse_currency(raw: str | None) -> str | None:
    """None means the parameter was omitted. Matching is exact, so "usd" or "" is rejected, not defaulted."""
    if raw is None or raw in SUPPORTED_CURRENCIES:
        return raw
    raise UnsupportedCurrency(
        f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}.",
        details={"currency": raw[:100], "allowed": list(SUPPORTED_CURRENCIES)},
    )


def conversion(native: str, requested: str | None) -> Conversion:
    """How to show money held in `native`. Omitting the request means native values, unconverted."""
    target = requested or native
    if target == native:
        return Conversion(native, 1.0)
    cad_to_usd = seed.load_seed()["CADtoUSD"]
    rate = {("CAD", "USD"): cad_to_usd, ("USD", "CAD"): 1 / cad_to_usd}.get((native, target))
    if rate is None:
        raise NoExchangeRate(f"no exchange rate from {native} to {target}")
    return Conversion(target, rate)
