"""
ScreenerClaw — Screener.in Filter Constants
All filter/ratio names supported by Screener.in's query builder.
Used by the QueryRouter and FilterScraper.

URL pattern: https://www.screener.in/screen/raw/?sort=&order=&source_id=&query=<encoded>
"""

# ── Annual P&L ─────────────────────────────────────────────────────────────────

ANNUAL_PL_RECENT = [
    "Sales",
    "OPM",
    "Profit after tax",
    "Return on capital employed",
    "EPS",
    "Change in promoter holding",
    "Sales last year",
    "Operating profit last year",
    "Other income last year",
    "EBIDT last year",
    "Depreciation last year",
    "EBIT last year",
    "Interest last year",
    "Profit before tax last year",
    "Tax last year",
    "Profit after tax last year",
    "Extraordinary items last year",
    "Net Profit last year",
    "Dividend last year",
    "Material cost last year",
    "Employee cost last year",
    "OPM last year",
    "NPM last year",
    "Operating profit",
    "Interest",
    "Depreciation",
    "EPS last year",
    "EBIT",
    "Net profit",
    "Current Tax",
    "Tax",
    "Other income",
    "TTM Result Date",
    "Last annual result date",
]

ANNUAL_PL_PRECEDING = [
    "Sales preceding year",
    "Operating profit preceding year",
    "Other income preceding year",
    "EBIDT preceding year",
    "Depreciation preceding year",
    "EBIT preceding year",
    "Interest preceding year",
    "Profit before tax preceding year",
    "Tax preceding year",
    "Profit after tax preceding year",
    "Extraordinary items preceding year",
    "Net Profit preceding year",
    "Dividend preceding year",
    "OPM preceding year",
    "NPM preceding year",
    "EPS preceding year",
    "Sales preceding 12months",
    "Net profit preceding 12months",
]

ANNUAL_PL_HISTORICAL = [
    "Sales growth 3Years",
    "Sales growth 5Years",
    "Profit growth 3Years",
    "Profit growth 5Years",
    "Sales growth 10years median",
    "Sales growth 5years median",
    "Sales growth 7Years",
    "Sales growth 10Years",
    "EBIDT growth 3Years",
    "EBIDT growth 5Years",
    "EBIDT growth 7Years",
    "EBIDT growth 10Years",
    "EPS growth 3Years",
    "EPS growth 5Years",
    "EPS growth 7Years",
    "EPS growth 10Years",
    "Profit growth 7Years",
    "Profit growth 10Years",
    "Change in promoter holding 3Years",
    "Average Earnings 5Year",
    "Average Earnings 10Year",
    "Average EBIT 5Year",
    "Average EBIT 10Year",
]

# ── Quarter P&L ────────────────────────────────────────────────────────────────

QUARTER_PL_RECENT = [
    "Sales latest quarter",
    "Profit after tax latest quarter",
    "YOY Quarterly sales growth",
    "YOY Quarterly profit growth",
    "Sales growth",
    "Profit growth",
    "Operating profit latest quarter",
    "Other income latest quarter",
    "EBIDT latest quarter",
    "Depreciation latest quarter",
    "EBIT latest quarter",
    "Interest latest quarter",
    "Profit before tax latest quarter",
    "Tax latest quarter",
    "Extraordinary items latest quarter",
    "Net Profit latest quarter",
    "GPM latest quarter",
    "OPM latest quarter",
    "NPM latest quarter",
    "Equity Capital latest quarter",
    "EPS latest quarter",
    "Operating profit 2quarters back",
    "Operating profit 3quarters back",
    "Sales 2quarters back",
    "Sales 3quarters back",
    "Net profit 2quarters back",
    "Net profit 3quarters back",
    "Operating profit growth",
    "Last result date",
    "Expected quarterly sales growth",
    "Expected quarterly sales",
    "Expected quarterly operating profit",
    "Expected quarterly net profit",
    "Expected quarterly EPS",
]

QUARTER_PL_PRECEDING = [
    "Sales preceding quarter",
    "Operating profit preceding quarter",
    "Other income preceding quarter",
    "EBIDT preceding quarter",
    "Depreciation preceding quarter",
    "EBIT preceding quarter",
    "Interest preceding quarter",
    "Profit before tax preceding quarter",
    "Tax preceding quarter",
    "Profit after tax preceding quarter",
    "Extraordinary items preceding quarter",
    "Net Profit preceding quarter",
    "OPM preceding quarter",
    "NPM preceding quarter",
    "Equity Capital preceding quarter",
    "EPS preceding quarter",
]

QUARTER_PL_HISTORICAL = [
    "Sales preceding year quarter",
    "Operating profit preceding year quarter",
    "Other income preceding year quarter",
    "EBIDT preceding year quarter",
    "Depreciation preceding year quarter",
    "EBIT preceding year quarter",
    "Interest preceding year quarter",
    "Profit before tax preceding year quarter",
    "Tax preceding year quarter",
    "Profit after tax preceding year quarter",
    "Extraordinary items preceding year quarter",
    "Net Profit preceding year quarter",
    "OPM preceding year quarter",
    "NPM preceding year quarter",
    "Equity Capital preceding year quarter",
    "EPS preceding year quarter",
]

# ── Balance Sheet ──────────────────────────────────────────────────────────────

BALANCE_SHEET = [
    "Total assets",
    "Fixed assets",
    "Capital work in progress",
    "Investments",
    "Other assets",
    "Total liabilities",
    "Equity capital",
    "Reserves",
    "Borrowings",
    "Other liabilities",
    "Total debt",
]

# ── Cash Flow ──────────────────────────────────────────────────────────────────

CASH_FLOW_RECENT = [
    "Cash from operations last year",
    "Free cash flow last year",
    "Cash from investing last year",
    "Cash from financing last year",
    "Net cash flow last year",
    "Cash beginning of last year",
    "Cash end of last year",
]

CASH_FLOW_PRECEDING = [
    "Free cash flow preceding year",
    "Cash from operations preceding year",
    "Cash from investing preceding year",
    "Cash from financing preceding year",
    "Net cash flow preceding year",
    "Cash beginning of preceding year",
    "Cash end of preceding year",
]

CASH_FLOW_HISTORICAL = [
    "Free cash flow 3years",
    "Free cash flow 5years",
    "Free cash flow 7years",
    "Free cash flow 10years",
    "Operating cash flow 3years",
    "Operating cash flow 5years",
    "Operating cash flow 7years",
    "Operating cash flow 10years",
    "Investing cash flow 10years",
    "Investing cash flow 7years",
    "Investing cash flow 5years",
    "Investing cash flow 3years",
    "Cash 3Years back",
    "Cash 5Years back",
    "Cash 7Years back",
]

# ── Ratios ─────────────────────────────────────────────────────────────────────

RATIOS_RECENT = [
    "Market Capitalization",
    "Price to Earning",
    "Dividend yield",
    "Price to book value",
    "Return on assets",
    "Debt to equity",
    "Return on equity",
    "Promoter holding",
    "Earnings yield",
    "Pledged percentage",
    "Industry PE",
    "Enterprise Value",
    "Number of equity shares",
    "Price to Quarterly Earning",
    "Book value",
    "Inventory turnover ratio",
    "Quick ratio",
    "Exports percentage",
    "Piotroski score",
    "G Factor",
    "Asset Turnover Ratio",
    "Financial leverage",
    "Number of Shareholders",
    "Unpledged promoter holding",
    "Return on invested capital",
    "Debtor days",
    "Industry PBV",
    "Credit rating",
    "Working Capital Days",
    "Earning Power",
    "Graham Number",
    "Cash Conversion Cycle",
    "Days Payable Outstanding",
    "Days Receivable Outstanding",
    "Days Inventory Outstanding",
    "Public holding",
    "FII holding",
    "Change in FII holding",
    "DII holding",
    "Change in DII holding",
    "Return on capital employed",
    "Current ratio",
    "Interest Coverage Ratio",
    "EV/EBITDA",
    "PEG Ratio",
    "Price to Sales",
    "Price to Free Cash Flow",
]

RATIOS_PRECEDING = [
    "Book value preceding year",
    "Return on capital employed preceding year",
    "Return on assets preceding year",
    "Return on equity preceding year",
    "Number of Shareholders preceding quarter",
]

RATIOS_HISTORICAL = [
    "Average return on equity 5Years",
    "Average return on equity 3Years",
    "Number of equity shares 10years back",
    "Book value 3years back",
    "Book value 5years back",
    "Book value 10years back",
    "Inventory turnover ratio 3Years back",
    "Inventory turnover ratio 5Years back",
    "Inventory turnover ratio 7Years back",
    "Inventory turnover ratio 10Years back",
    "Exports percentage 3Years back",
    "Exports percentage 5Years back",
    "Average 5years dividend",
    "Average return on capital employed 3Years",
    "Average return on capital employed 5Years",
    "Average return on capital employed 7Years",
    "Average return on capital employed 10Years",
    "Average return on equity 10Years",
    "Average return on equity 7Years",
    "Return on equity 5years growth",
    "OPM 5Year",
    "OPM 10Year",
    "Number of Shareholders 1year back",
    "Average dividend payout 3years",
    "Average debtor days 3years",
    "Debtor days 3years back",
    "Debtor days 5years back",
    "Return on assets 5years",
    "Return on assets 3years",
    "Historical PE 3Years",
    "Historical PE 10Years",
    "Historical PE 7Years",
    "Historical PE 5Years",
    "Market Capitalization 3years back",
    "Market Capitalization 5years back",
    "Market Capitalization 7years back",
    "Market Capitalization 10years back",
    "Average Working Capital Days 3years",
    "Change in FII holding 3Years",
    "Change in DII holding 3Years",
]

# ── Price ──────────────────────────────────────────────────────────────────────

PRICE_RECENT = [
    "Current price",
    "Return over 3months",
    "Return over 6months",
    "Is SME",
    "Is not SME",
    "Volume 1month average",
    "Volume 1week average",
    "Volume",
    "High price",
    "Low price",
    "High price all time",
    "Low price all time",
    "Return over 1day",
    "Return over 1week",
    "Return over 1month",
    "DMA 50",
    "DMA 200",
    "DMA 50 previous day",
    "DMA 200 previous day",
    "RSI",
    "MACD",
    "MACD Previous Day",
    "MACD Signal",
    "MACD Signal Previous Day",
]

PRICE_HISTORICAL = [
    "Return over 1year",
    "Return over 3years",
    "Return over 5years",
    "Volume 1year average",
    "Return over 7years",
    "Return over 10years",
]

# ── Most Used (convenience list for the QueryRouter) ──────────────────────────

MOST_USED = [
    "Sales",
    "OPM",
    "Profit after tax",
    "Market Capitalization",
    "Sales latest quarter",
    "Profit after tax latest quarter",
    "YOY Quarterly sales growth",
    "YOY Quarterly profit growth",
    "Price to Earning",
    "Dividend yield",
    "Price to book value",
    "Return on capital employed",
    "Return on assets",
    "Debt to equity",
    "Return on equity",
    "EPS",
    "Promoter holding",
    "Change in promoter holding",
    "Earnings yield",
    "Pledged percentage",
    "Industry PE",
    "Sales growth",
    "Profit growth",
    "Current price",
    "Price to Sales",
    "Price to Free Cash Flow",
    "EV/EBITDA",
    "Enterprise Value",
    "Current ratio",
    "Interest Coverage Ratio",
    "PEG Ratio",
    "Return over 3months",
    "Return over 6months",
    "Sales growth 3Years",
    "Sales growth 5Years",
    "Profit growth 3Years",
    "Profit growth 5Years",
    "Average return on equity 5Years",
    "Average return on equity 3Years",
    "Return over 1year",
    "Return over 3years",
    "Return over 5years",
    "Free cash flow last year",
    "Cash from operations last year",
    "Piotroski score",
    "Graham Number",
    "Debtor days",
    "Working Capital Days",
    "FII holding",
    "DII holding",
    "Promoter holding",
    "Pledged percentage",
    "DMA 50",
    "DMA 200",
    "RSI",
]

# ── All filters flat (for fuzzy matching in router) ───────────────────────────

ALL_FILTERS: list[str] = list({
    *ANNUAL_PL_RECENT, *ANNUAL_PL_PRECEDING, *ANNUAL_PL_HISTORICAL,
    *QUARTER_PL_RECENT, *QUARTER_PL_PRECEDING, *QUARTER_PL_HISTORICAL,
    *BALANCE_SHEET,
    *CASH_FLOW_RECENT, *CASH_FLOW_PRECEDING, *CASH_FLOW_HISTORICAL,
    *RATIOS_RECENT, *RATIOS_PRECEDING, *RATIOS_HISTORICAL,
    *PRICE_RECENT, *PRICE_HISTORICAL,
})

# ── Common query templates ────────────────────────────────────────────────────

QUERY_TEMPLATES = {
    "quality_compounders": (
        "Return on capital employed > 20 AND "
        "Sales growth 5Years > 15 AND "
        "Profit growth 5Years > 15 AND "
        "Debt to equity < 0.5"
    ),
    "value_picks": (
        "Price to Earning < 15 AND "
        "Return on capital employed > 15 AND "
        "Market Capitalization > 500"
    ),
    "high_roce_low_debt": (
        "Return on capital employed > 25 AND "
        "Debt to equity < 0.3"
    ),
    "dividend_aristocrats": (
        "Dividend yield > 3 AND "
        "Return on capital employed > 15 AND "
        "Profit growth 5Years > 10"
    ),
    "momentum_quality": (
        "Return over 1year > 20 AND "
        "Return on capital employed > 20 AND "
        "Sales growth 3Years > 15"
    ),
    "hidden_gems": (
        "Market Capitalization < 5000 AND "
        "Market Capitalization > 500 AND "
        "Return on capital employed > 20 AND "
        "Profit growth 5Years > 20 AND "
        "Debt to equity < 0.5"
    ),
    "debt_free": (
        "Debt to equity < 0.1 AND "
        "Return on capital employed > 15 AND "
        "Market Capitalization > 500"
    ),
    "cash_rich": (
        "Free cash flow last year > 0 AND "
        "Cash from operations last year > 0 AND "
        "Return on capital employed > 15"
    ),
}
