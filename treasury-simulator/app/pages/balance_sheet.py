from common import coming_soon, page_header

page_header("Balance sheet & NAV", 1, "The TRS balance sheet in each currency and in USD.")
coming_soon(2, [
    "Assets: bank cash, MMFs, IC loans, FX deals with a positive MTM",
    "Liabilities: facility drawings, IC deposits, FX deals with a negative MTM, accrued fees",
    "NAV per currency and in USD; open FX position per currency against the USD 50k tolerance",
    "Accrued interest by day count (actual/360 for USD, EUR, CHF; actual/365 for GBP)",
])
