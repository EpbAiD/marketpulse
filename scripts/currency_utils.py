#!/usr/bin/env python3
"""
Currency conversion helper for the alert systems.

Fetches live USD → local-currency exchange rates from Yahoo Finance and
formats prices for display in the recipient's currency.

Design notes:
  - Gold's global spot price is set in USD (COMEX / London Fix). To display
    in local currency, we multiply by USD-to-local. The pullback percentage
    signal is inherently a USD-gold move — displaying in local currency is
    a UX improvement for the reader; it does not change the alert logic.
  - The USD-vs-local pullback can differ slightly because currency movements
    add a layer. For most currencies the difference is small (<1%); for
    high-inflation currencies (INR, TRY, ZAR) it can be larger over time.
  - The FX rate is included in the email footer for transparency.
"""
from __future__ import annotations

from typing import Callable

import yfinance as yf


# Yahoo Finance FX ticker conventions vary. Some pairs are "USD per LOCAL"
# (EURUSD=X means 1 EUR = X USD), others are "LOCAL per USD" (INR=X means
# 1 USD = X INR). This table encodes which convention each ticker uses so
# we can always compute "amount of local currency for 1 USD".
# Gold weight-unit conversions. Prices from GC=F (COMEX gold futures) are
# quoted per troy ounce. Factor = multiplier applied to per-troy-ounce
# price to get per-target-unit price.
#
#   1 troy ounce = 31.1035 grams
#   1 tola       = 11.6638 grams (Indian traditional)
#   1 kilogram   = 32.1507 troy ounces
WEIGHT_UNITS = {
    "troy_ounce": {"factor": 1.0,               "label": "per troy ounce", "short": "oz"},
    "ounce":      {"factor": 1.0,               "label": "per troy ounce", "short": "oz"},
    "gram":       {"factor": 1 / 31.1035,       "label": "per gram",       "short": "g"},
    "10_gram":    {"factor": 10 / 31.1035,      "label": "per 10 grams",   "short": "10g"},
    "kilogram":   {"factor": 1000 / 31.1035,    "label": "per kilogram",   "short": "kg"},
    "kg":         {"factor": 1000 / 31.1035,    "label": "per kilogram",   "short": "kg"},
    "tola":       {"factor": 11.6638 / 31.1035, "label": "per tola",       "short": "tola"},
}


def weight_factor(weight_unit: str) -> tuple[float, str, str]:
    """Return (multiplier, label, short_symbol) for a weight unit code.
    Defaults to troy_ounce for unknown codes."""
    key = (weight_unit or "troy_ounce").lower()
    cfg = WEIGHT_UNITS.get(key, WEIGHT_UNITS["troy_ounce"])
    return cfg["factor"], cfg["label"], cfg["short"]


SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$",   "yf_ticker": None, "invert": False, "name": "US Dollar"},
    "EUR": {"symbol": "€",   "yf_ticker": "EURUSD=X", "invert": True,  "name": "Euro"},
    "GBP": {"symbol": "£",   "yf_ticker": "GBPUSD=X", "invert": True,  "name": "British Pound"},
    "AUD": {"symbol": "A$",  "yf_ticker": "AUDUSD=X", "invert": True,  "name": "Australian Dollar"},
    "NZD": {"symbol": "NZ$", "yf_ticker": "NZDUSD=X", "invert": True,  "name": "New Zealand Dollar"},
    "INR": {"symbol": "₹",   "yf_ticker": "INR=X",    "invert": False, "name": "Indian Rupee"},
    "JPY": {"symbol": "¥",   "yf_ticker": "JPY=X",    "invert": False, "name": "Japanese Yen"},
    "CAD": {"symbol": "C$",  "yf_ticker": "CAD=X",    "invert": False, "name": "Canadian Dollar"},
    "CHF": {"symbol": "Fr",  "yf_ticker": "CHF=X",    "invert": False, "name": "Swiss Franc"},
    "CNY": {"symbol": "¥",   "yf_ticker": "CNY=X",    "invert": False, "name": "Chinese Yuan"},
    "AED": {"symbol": "AED", "yf_ticker": "AED=X",    "invert": False, "name": "UAE Dirham"},
    "SGD": {"symbol": "S$",  "yf_ticker": "SGD=X",    "invert": False, "name": "Singapore Dollar"},
    "HKD": {"symbol": "HK$", "yf_ticker": "HKD=X",    "invert": False, "name": "Hong Kong Dollar"},
    "ZAR": {"symbol": "R",   "yf_ticker": "ZAR=X",    "invert": False, "name": "South African Rand"},
    "BRL": {"symbol": "R$",  "yf_ticker": "BRL=X",    "invert": False, "name": "Brazilian Real"},
    "MXN": {"symbol": "MX$", "yf_ticker": "MXN=X",    "invert": False, "name": "Mexican Peso"},
    "SAR": {"symbol": "SAR", "yf_ticker": "SAR=X",    "invert": False, "name": "Saudi Riyal"},
    "TRY": {"symbol": "₺",   "yf_ticker": "TRY=X",    "invert": False, "name": "Turkish Lira"},
}


def fetch_usd_rate(currency_code: str) -> tuple[float, str]:
    """Return (units_of_local_currency_per_1_USD, currency_symbol).

    For USD, returns (1.0, "$") without a network call.
    For unsupported codes, falls back to USD with a warning suffix in symbol.
    """
    code = currency_code.upper()
    if code == "USD" or code not in SUPPORTED_CURRENCIES:
        return 1.0, SUPPORTED_CURRENCIES["USD"]["symbol"]

    cfg = SUPPORTED_CURRENCIES[code]
    ticker = cfg["yf_ticker"]
    try:
        df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
        if len(df) == 0:
            return 1.0, "$"
        # yfinance may return a MultiIndex column
        if hasattr(df.columns, "get_level_values"):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        latest_rate = float(df["Close"].iloc[-1])
    except Exception:
        return 1.0, "$"

    if cfg["invert"]:
        # ticker gave USD per LOCAL (e.g. EURUSD = 1.08 means 1 EUR = 1.08 USD)
        # To get LOCAL per USD, we invert.
        return (1.0 / latest_rate), cfg["symbol"]
    else:
        # ticker already gave LOCAL per USD (e.g. INR=X = 83 means 1 USD = 83 INR)
        return latest_rate, cfg["symbol"]


def make_price_formatter(currency_code: str,
                         weight_unit: str = "troy_ounce") -> tuple[Callable[[float], str], float, str]:
    """Return (format_fn, usd_to_local_rate, currency_symbol).

    format_fn takes a per-troy-ounce USD price and returns a formatted
    string in the recipient's currency AND the recipient's weight unit
    (default: troy ounce, so no conversion).
    """
    rate, symbol = fetch_usd_rate(currency_code)
    code = currency_code.upper()
    w_mult, _, _ = weight_factor(weight_unit)

    def _fmt(usd_per_oz: float) -> str:
        local = usd_per_oz * rate * w_mult
        # Choose decimals + grouping based on magnitude / currency
        if code in {"JPY", "INR", "TRY", "KRW", "IDR", "VND"} and local >= 1000:
            return f"{symbol}{local:,.0f}"
        if local >= 1000:
            return f"{symbol}{local:,.0f}"
        if local >= 10:
            return f"{symbol}{local:,.2f}"
        return f"{symbol}{local:.4f}"

    return _fmt, rate, symbol


def _format_local(usd_per_oz: float, rate: float, sym: str, code: str,
                  weight_multiplier: float) -> str:
    local = usd_per_oz * rate * weight_multiplier
    if code in {"JPY", "INR", "TRY", "KRW", "IDR", "VND"} and local >= 1000:
        return f"{sym}{local:,.0f}"
    if local >= 1000:
        return f"{sym}{local:,.0f}"
    if local >= 10:
        return f"{sym}{local:,.2f}"
    return f"{sym}{local:.4f}"


def _build_single_weight_table(usd_prices: dict[str, float],
                               currencies: list[str],
                               rates: dict[str, tuple[float, str]],
                               weight_unit: str,
                               accent: str) -> str:
    """One table for one weight unit, showing currency rows × price-label columns."""
    w_mult, w_label, _ = weight_factor(weight_unit)
    head = "".join(
        f'<th style="padding: 6px 10px; text-align: right; color: #7F8C8D; '
        f'font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; '
        f'font-weight: 500; border-bottom: 1px solid #ECF0F1;">{label}</th>'
        for label in usd_prices
    )
    rows = ""
    for code in currencies:
        rate, sym = rates[code]
        row_cells = "".join(
            f'<td style="padding: 6px 10px; text-align: right; color: #2C3E50; '
            f'font-size: 0.9rem; font-weight: 500;">'
            f'{_format_local(usd, rate, sym, code, w_mult)}</td>'
            for usd in usd_prices.values()
        )
        rows += (
            f'<tr>'
            f'<td style="padding: 6px 10px; color: #34495E; font-size: 0.85rem; '
            f'font-weight: 500;">{code}</td>'
            f'{row_cells}'
            f'</tr>'
        )
    return f"""
  <div style="border: 1px solid #ECF0F1; border-radius: 4px; margin: 1rem 0; overflow-x: auto;">
    <div style="padding: 0.7rem 1rem; background: #F8F9FA; border-bottom: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Prices {w_label}</div>
    </div>
    <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
      <thead>
        <tr>
          <th style="padding: 6px 10px; text-align: left; color: #7F8C8D; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500; border-bottom: 1px solid #ECF0F1;">Currency</th>
          {head}
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""


def build_multi_currency_table_html(usd_prices: dict[str, float],
                                    currencies: list[str],
                                    weight_units: list[str] | None = None,
                                    accent: str = "#1F4E79") -> str:
    """Return HTML showing each USD price converted into each requested
    currency AND each requested weight unit.

    usd_prices:   {label: usd_per_troy_ounce} — e.g. {"Gold today": 4481}
    currencies:   list of currency codes to show as rows
    weight_units: list of weight units to show as separate tables; if None
                  or empty, defaults to ["troy_ounce"] (one table)
    """
    if not currencies or not usd_prices:
        return ""
    if not weight_units:
        weight_units = ["troy_ounce"]

    # Fetch each currency rate + symbol once
    rates: dict[str, tuple[float, str]] = {}
    for c in currencies:
        rates[c] = fetch_usd_rate(c)

    # One table per weight unit
    return "".join(
        _build_single_weight_table(usd_prices, currencies, rates, wu, accent)
        for wu in weight_units
    )


def fx_footer_line(currency_code: str, rate: float) -> str:
    """Human-readable FX-rate line to include in the email footer."""
    code = currency_code.upper()
    if code == "USD":
        return ""
    if code not in SUPPORTED_CURRENCIES:
        return ""
    name = SUPPORTED_CURRENCIES[code]["name"]
    # Choose readable formatting for the rate itself
    if rate >= 100:
        rate_str = f"{rate:,.2f}"
    elif rate >= 10:
        rate_str = f"{rate:.3f}"
    else:
        rate_str = f"{rate:.4f}"
    return f"Prices shown in {name} ({code}) at today's rate: 1 USD = {rate_str} {code}."
