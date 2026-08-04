from domain.parsers import parse_number
from services.market_data import ETF_FLOW_COLUMNS, parse_latest_etf_flow_row


def test_parse_number_handles_currency_and_sign():
    assert parse_number("+123.45M $") == 123.45


def test_parse_number_handles_european_decimal():
    assert parse_number("%7,25") == 7.25


def test_parse_number_handles_parentheses_as_negative():
    assert parse_number("(1,234.50)") == -1234.5


def test_parse_number_returns_none_for_invalid_values():
    assert parse_number("not-a-number") is None
    assert parse_number(None) is None


def test_parse_latest_etf_flow_row_handles_current_farside_layout_with_msbt():
    sample = """
01 Apr 2026
(86.5)
(78.6)
(5.6)
0.0
0.0
0.0
0.0
0.0
0.0
-
(13.3)
10.3
(173.7)
08 Apr 2026
40.4
(79.1)
0.0
(74.7)
0.0
0.0
0.0
0.0
0.0
30.6
(11.1)
0.0
(93.9)
09 Apr 2026
-
-
-
-
-
-
-
-
-
-
-
-
0.0
Total
"""

    date_text, values = parse_latest_etf_flow_row(sample)
    mapping = dict(zip(ETF_FLOW_COLUMNS, values))

    assert date_text == "08 Apr 2026"
    assert mapping["MSBT"] == "30.6"
    assert mapping["GBTC"] == "(11.1)"
    assert mapping["BTC"] == "0.0"
    assert mapping["TOTAL"] == "(93.9)"


def test_parse_latest_etf_flow_row_remains_compatible_with_legacy_layout():
    sample = """
| 07 Apr 2026 | (17.1) | (47.8) | 0.0 | (34.2) | 0.0 | 0.0 | 2.3 | (20.4) | 0.0 | (41.9) | 0.0 | (159.1) |
| 08 Apr 2026 | 40.4 | (79.1) | 0.0 | (74.7) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | (11.1) | 0.0 | (93.9) |
"""

    date_text, values = parse_latest_etf_flow_row(sample)
    mapping = dict(zip(ETF_FLOW_COLUMNS, values))

    assert date_text == "08 Apr 2026"
    assert mapping["MSBT"] == "—"
    assert mapping["GBTC"] == "(11.1)"
    assert mapping["TOTAL"] == "(93.9)"


def test_parse_latest_etf_flow_row_handles_raw_farside_html():
    # r.jina.ai olmadan doğrudan farside.co.uk'tan gelen ham HTML tablosu
    sample = """
    <html><body>
    <table>
    <tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>BITB</th><th>ARKB</th><th>BTCO</th>
        <th>EZBC</th><th>BRRR</th><th>HODL</th><th>BTCW</th><th>MSBT</th><th>GBTC</th>
        <th>BTC</th><th>Total</th></tr>
    <tr><td>07 Apr 2026</td><td>(17.1)</td><td>(47.8)</td><td>0.0</td><td>(34.2)</td>
        <td>0.0</td><td>0.0</td><td>2.3</td><td>(20.4)</td><td>0.0</td><td>&#8211;</td>
        <td>(41.9)</td><td>0.0</td><td>(159.1)</td></tr>
    <tr><td>03 Aug 2026</td><td>&#8211;</td><td>&#8211;</td><td>2.8</td><td>2.1</td>
        <td>&#8211;</td><td>9.2</td><td>&#8211;</td><td>4.5</td><td>0.0</td><td>0.0</td>
        <td>0.0</td><td>0.0</td><td>18.6</td></tr>
    </table>
    </body></html>
    """

    date_text, values = parse_latest_etf_flow_row(sample)
    mapping = dict(zip(ETF_FLOW_COLUMNS, values))

    assert date_text == "03 Aug 2026"
    assert mapping["BITB"] == "2.8"
    assert mapping["EZBC"] == "9.2"
    assert mapping["TOTAL"] == "18.6"


def test_parse_latest_etf_flow_row_html_skips_all_placeholder_rows():
    # En güncel satır tamamen placeholder ise, HTML parser bir önceki dolu satıra düşmeli
    sample = """
    <table>
    <tr><td>07 Apr 2026</td><td>10.0</td><td>5.0</td><td>0.0</td><td>0.0</td>
        <td>0.0</td><td>0.0</td><td>0.0</td><td>0.0</td><td>0.0</td><td>-</td>
        <td>0.0</td><td>0.0</td><td>15.0</td></tr>
    <tr><td>08 Apr 2026</td><td>-</td><td>-</td><td>-</td><td>-</td>
        <td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>
        <td>-</td><td>-</td><td>0.0</td></tr>
    </table>
    """

    date_text, values = parse_latest_etf_flow_row(sample)
    mapping = dict(zip(ETF_FLOW_COLUMNS, values))

    assert date_text == "07 Apr 2026"
    assert mapping["IBIT"] == "10.0"
