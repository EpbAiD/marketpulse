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


def make_price_formatter(currency_code: str) -> tuple[Callable[[float], str], float, str]:
    """Return (format_fn, usd_to_local_rate, currency_symbol).

    format_fn takes a USD price and returns a formatted string in the
    recipient's currency. Rate + symbol are also returned so callers can
    build a footer like "FX: 1 USD = 83.42 INR".
    """
    rate, symbol = fetch_usd_rate(currency_code)
    code = currency_code.upper()

    def _fmt(usd_price: float) -> str:
        local = usd_price * rate
        # Choose decimals + grouping based on magnitude / currency
        if code in {"JPY", "INR", "TRY", "KRW", "IDR", "VND"} and local >= 1000:
            # Currencies with typically-large denominators: no decimals + grouping
            return f"{symbol}{local:,.0f}"
        if local >= 1000:
            return f"{symbol}{local:,.0f}"
        if local >= 10:
            return f"{symbol}{local:,.2f}"
        return f"{symbol}{local:.4f}"

    return _fmt, rate, symbol


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
