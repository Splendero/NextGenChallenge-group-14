"""Task 7: ?currency=CAD|USD on the portfolio, holdings and performance-history endpoints."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.currency import Conversion, NoExchangeRate, conversion, parse_currency
from app.dependencies import get_crm_client, get_history_service
from app.errors import UnsupportedCurrency
from app.main import create_app
from app.services.history_service import HistoryService, Snapshot
from tests.conftest import AUTH_HEADERS, load_fixture, make_settings
from tests.test_portfolios_api import FakeCrm, assert_error

CAD_TO_USD = 0.73
TODAY = date(2026, 10, 3)
ENDPOINTS = ["/portfolios/{}", "/portfolios/{}/holdings", "/portfolios/{}/performance-history"]
HOLDING_MONEY = ["costBasisPerShare", "price", "previousClosePrice", "marketValue", "unrealizedGainLoss",
                 "dayChangeAmount"]
HOLDING_NON_MONEY = ["ticker", "name", "assetClass", "quantity", "weightPercent", "dayChangePercent"]


def with_currency(fixture: str, code: str) -> dict:
    payload = load_fixture(fixture)
    for account in payload["client_record"]["accounts"]:
        account["curr_val"]["ccy"] = code
    return payload


# --- Pure functions ---


@pytest.mark.parametrize("raw", ["CAD", "USD", None])
def test_parse_currency_accepts_supported_values_and_omission(raw):
    assert parse_currency(raw) == raw


@pytest.mark.parametrize("raw", ["EUR", "usd", "cad", " USD", ""])
def test_parse_currency_rejects_anything_else_instead_of_defaulting(raw):
    with pytest.raises(UnsupportedCurrency) as caught:
        parse_currency(raw)
    assert caught.value.details == {"currency": raw, "allowed": ["CAD", "USD"]}


@pytest.mark.parametrize(
    ("native", "requested", "expected"),
    [
        ("CAD", None, Conversion("CAD", 1.0)),
        ("CAD", "CAD", Conversion("CAD", 1.0)),
        ("CAD", "USD", Conversion("USD", CAD_TO_USD)),
        ("USD", "CAD", Conversion("CAD", 1 / CAD_TO_USD)),
        ("USD", None, Conversion("USD", 1.0)),
        ("EUR", None, Conversion("EUR", 1.0)),
    ],
)
def test_conversion_rate_comes_from_seed(native, requested, expected):
    assert conversion(native, requested) == expected


def test_no_rate_between_unsupported_currencies():
    with pytest.raises(NoExchangeRate):
        conversion("EUR", "USD")


# --- HTTP ---


@pytest.fixture
def fake_crm() -> FakeCrm:
    crm = FakeCrm()
    crm.responses["P-9001"] = load_fixture("ok_p9001")
    return crm


@pytest.fixture
def client(fake_crm):
    app = create_app(make_settings())
    history = HistoryService(
        {"P-9001": [Snapshot(date(2026, 10, 2), 48917.8), Snapshot(TODAY, 48930.0)]},
        {"P-9001": "CAD", "P-EMPTY": "CAD"},
        today=lambda: TODAY,
    )
    app.dependency_overrides[get_crm_client] = lambda: fake_crm
    app.dependency_overrides[get_history_service] = lambda: history
    with TestClient(app, raise_server_exceptions=False, headers=AUTH_HEADERS) as test_client:
        yield test_client


def test_portfolio_in_usd(client):
    body = client.get("/portfolios/P-9001", params={"currency": "USD"}).json()
    assert body["currency"] == "USD"
    assert body["exchangeRate"] == CAD_TO_USD
    assert body["totalMarketValue"] == pytest.approx(48930 * CAD_TO_USD)
    assert body["dayChangeAmount"] == pytest.approx(30 * CAD_TO_USD)
    assert body["dayChangePercent"] == pytest.approx(0.0006134969325153375)
    assert body["totalReturnSinceInception"] == 0.187


def test_holdings_in_usd_convert_money_fields_only(client):
    cad = {h["ticker"]: h for h in client.get("/portfolios/P-9001/holdings").json()}
    usd = {h["ticker"]: h for h in client.get("/portfolios/P-9001/holdings", params={"currency": "USD"}).json()}
    assert set(usd) == set(cad)
    for ticker, holding in usd.items():
        assert (holding["currency"], holding["exchangeRate"]) == ("USD", CAD_TO_USD)
        for field in HOLDING_MONEY:
            assert holding[field] == pytest.approx(cad[ticker][field] * CAD_TO_USD), (ticker, field)
        for field in HOLDING_NON_MONEY:
            assert holding[field] == cad[ticker][field], (ticker, field)


def test_history_in_usd(client):
    body = client.get("/portfolios/P-9001/performance-history", params={"currency": "USD"}).json()
    assert [point["marketValue"] for point in body] == pytest.approx([48917.8 * CAD_TO_USD, 48930.0 * CAD_TO_USD])
    assert all((point["currency"], point["exchangeRate"]) == ("USD", CAD_TO_USD) for point in body)


@pytest.mark.parametrize("params", [{}, {"currency": "CAD"}], ids=["omitted", "explicit_cad"])
def test_omitted_or_cad_returns_native_values(client, params):
    portfolio = client.get("/portfolios/P-9001", params=params).json()
    holdings = client.get("/portfolios/P-9001/holdings", params=params).json()
    history = client.get("/portfolios/P-9001/performance-history", params=params).json()
    assert (portfolio["currency"], portfolio["exchangeRate"], portfolio["totalMarketValue"]) == ("CAD", 1.0, 48930.0)
    assert holdings[0]["marketValue"] == 27300.0
    assert history[-1]["marketValue"] == 48930.0
    assert all((item["currency"], item["exchangeRate"]) == ("CAD", 1.0) for item in holdings + history)


@pytest.mark.parametrize("currency", ["CAD", "USD"])
def test_totals_agree_across_endpoints(client, currency):
    params = {"currency": currency}
    portfolio_total = client.get("/portfolios/P-9001", params=params).json()["totalMarketValue"]
    holdings = client.get("/portfolios/P-9001/holdings", params=params).json()
    latest = client.get("/portfolios/P-9001/performance-history", params=params).json()[-1]["marketValue"]
    assert sum(h["marketValue"] for h in holdings) == pytest.approx(portfolio_total)
    assert latest == pytest.approx(portfolio_total)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("bad_currency", ["EUR", "usd", ""])
def test_unsupported_currency_returns_400_on_every_endpoint(client, endpoint, bad_currency):
    response = client.get(endpoint.format("P-9001"), params={"currency": bad_currency})
    body = assert_error(response, 400, "unsupported_currency")
    assert body["details"] == {"currency": bad_currency, "allowed": ["CAD", "USD"]}


def test_unsupported_currency_does_not_call_the_crm(client, fake_crm):
    client.get("/portfolios/P-9001", params={"currency": "EUR"})
    assert fake_crm.calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS[1:])
def test_bad_currency_is_reported_before_unknown_id(client, endpoint):
    assert_error(client.get(endpoint.format("UNKNOWN"), params={"currency": "EUR"}), 400, "unsupported_currency")


@pytest.mark.parametrize("endpoint", ENDPOINTS[1:])
def test_empty_portfolio_stays_empty_in_usd(client, endpoint):
    response = client.get(endpoint.format("P-EMPTY"), params={"currency": "USD"})
    assert (response.status_code, response.json()) == (200, [])


def test_null_money_fields_stay_null_when_converted(client, fake_crm):
    fake_crm.responses["P-9001"] = load_fixture("all_numbers_null")
    body = client.get("/portfolios/P-9001", params={"currency": "USD"}).json()
    assert (body["totalMarketValue"], body["dayChangeAmount"]) == (None, None)
    assert (body["currency"], body["exchangeRate"]) == ("USD", CAD_TO_USD)


def test_usd_account_from_the_crm_converts_to_cad(client, fake_crm):
    fake_crm.responses["P-9001"] = with_currency("ok_p9001", "USD")
    native = client.get("/portfolios/P-9001").json()
    in_cad = client.get("/portfolios/P-9001", params={"currency": "CAD"}).json()
    assert (native["currency"], native["exchangeRate"], native["totalMarketValue"]) == ("USD", 1.0, 48930.0)
    assert (in_cad["currency"], in_cad["exchangeRate"]) == ("CAD", pytest.approx(1 / CAD_TO_USD))
    assert in_cad["totalMarketValue"] == pytest.approx(48930 / CAD_TO_USD)


def test_crm_currency_without_a_rate_is_returned_unconverted_with_a_warning(client, fake_crm):
    fake_crm.responses["P-9001"] = with_currency("ok_p9001", "EUR")
    body = client.get("/portfolios/P-9001", params={"currency": "USD"}).json()
    assert (body["currency"], body["exchangeRate"], body["totalMarketValue"]) == ("EUR", 1.0, 48930.0)
    assert body["warnings"] == ["no exchange rate from EUR to USD; values are in EUR"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_openapi_documents_the_currency_parameter(client, endpoint):
    path = endpoint.format("{portfolio_id}")
    operation = client.get("/openapi.json").json()["paths"][path]["get"]
    assert "currency" in [parameter["name"] for parameter in operation["parameters"]]
    assert "400" in operation["responses"]
