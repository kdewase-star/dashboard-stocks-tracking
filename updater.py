import sys
import subprocess
import json
import time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

# V5.8
# Historical stock-data fix
# Keeps:
# - ABB / BDL / BPCL / BEL / CUPID
# - NIFTY 50
# - SENSEX
# - NIFTY 500 opportunities

subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "nse[server]",
        "bse",
        "requests"
    ],
    check=True
)

from nse import NSE


WATCH = {
    "ABB": "ABB India",
    "BDL": "Bharat Dynamics",
    "BPCL": "BPCL",
    "BEL": "Bharat Electronics",
    "CUPID": "Cupid"
}


def num(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def find(data, *keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]

    return None


def pct(current, previous):
    if current is None or previous in (None, 0):
        return None

    return round(
        (current / previous - 1) * 100,
        2
    )


# =========================================================
# HISTORICAL DATA
# =========================================================

def historical_points(rows):

    # NSE may return:
    #   list
    #   {"data": [...]}
    #   {"Data": [...]}
    #   {"records": [...]}

    if isinstance(rows, dict):

        rows = (
            rows.get("data")
            or rows.get("Data")
            or rows.get("records")
            or rows.get("rows")
            or []
        )

    if not isinstance(rows, list):
        rows = []

    points = []

    for row in rows:

        if not isinstance(row, dict):
            continue

        close = find(
            row,
            "CH_CLOSING_PRICE",
            "CH_LAST_TRADED_PRICE",
            "close",
            "Close",
            "CLOSE"
        )

        timestamp = find(
            row,
            "CH_TIMESTAMP",
            "mTIMESTAMP",
            "timestamp",
            "date",
            "Date"
        )

        volume = find(
            row,
            "CH_TOT_TRADED_QTY",
            "volume",
            "Volume"
        )

        if close is None:
            continue

        try:
            close = float(close)
        except Exception:
            continue

        try:
            volume = int(
                float(volume or 0)
            )
        except Exception:
            volume = 0

        # Convert date to Unix timestamp
        try:

            import datetime as dt

            text = str(timestamp)

            if "-" in text:

                parsed = dt.datetime.strptime(
                    text[:10],
                    "%Y-%m-%d"
                )

                timestamp_value = int(
                    parsed.replace(
                        tzinfo=dt.timezone.utc
                    ).timestamp()
                )

            else:
                timestamp_value = len(points)

        except Exception:

            timestamp_value = len(points)

        points.append(
            {
                "t": timestamp_value,
                "c": round(close, 4),
                "v": volume
            }
        )

    points.sort(
        key=lambda x: x["t"]
    )

    return points


def old_close(points, days):

    if not points:
        return None

    target = (
        time.time()
        - days * 86400
    )

    candidate = points[0]["c"]

    for point in points:

        if point["t"] <= target:
            candidate = point["c"]
        else:
            break

    return candidate


# =========================================================
# STOCK QUOTE
# =========================================================

def quote_row(nse, symbol, name):

    quote = nse.quote(symbol)

    meta = quote.get(
        "metaData",
        {}
    )

    price = quote.get(
        "priceInfo",
        {}
    )

    trade = quote.get(
        "tradeInfo",
        {}
    )

    security = quote.get(
        "secInfo",
        {}
    )

    last = (
        num(trade.get("lastPrice"))
        or num(
            quote
            .get("orderBook", {})
            .get("lastPrice")
        )
        or num(meta.get("lastPrice"))
    )

    previous = num(
        meta.get("previousClose")
    )

    today = num(
        meta.get("pChange")
    )

    high = num(
        price.get("yearHigh")
    )

    low = num(
        price.get("yearLow")
    )

    volume = num(
        trade.get("totalTradedVolume")
    )

    points = []

    # -----------------------------------------------------
    # FETCH 10 YEARS OF HISTORY
    # -----------------------------------------------------

    try:

        from_date = (
            date.today()
            - timedelta(
                days=3650 + 30
            )
        )

        rows = nse.fetch_equity_historical_data(
            symbol,
            from_date=from_date,
            to_date=date.today()
        )

        points = historical_points(rows)

        print(
            "Historical",
            symbol,
            "points:",
            len(points)
        )

    except Exception as error:

        print(
            "Historical data unavailable for",
            symbol,
            repr(error)
        )

    # -----------------------------------------------------
    # USE HISTORY WHEN AVAILABLE
    # -----------------------------------------------------

    if points:

        if last is None:
            last = points[-1]["c"]

        if previous is None and len(points) > 1:
            previous = points[-2]["c"]

        one_year = points[-252:]

        if high is None and one_year:
            high = max(
                x["c"]
                for x in one_year
            )

        if low is None and one_year:
            low = min(
                x["c"]
                for x in one_year
            )

        if volume is None:
            volume = points[-1]["v"]

    if today is None:
        today = pct(
            last,
            previous
        )

    # -----------------------------------------------------
    # PERFORMANCE
    # -----------------------------------------------------

    m1 = pct(
        last,
        old_close(points, 30)
    )

    m3 = pct(
        last,
        old_close(points, 91)
    )

    m6 = pct(
        last,
        old_close(points, 182)
    )

    m9 = pct(
        last,
        old_close(points, 274)
    )

    y1 = pct(
        last,
        old_close(points, 365)
    )

    y5 = pct(
        last,
        old_close(points, 1826)
    )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score = None

    if today is not None:

        score = max(
            0,
            min(
                100,
                35
                + today * 3
                + max(0, m1 or 0) * 1.5
                + max(0, m3 or 0) * 0.5
                + (
                    5
                    if (
                        high
                        and last
                        and last >= high * 0.97
                    )
                    else 0
                )
            )
        )

    return {

        "name": name,

        "last": last,

        "prev": previous,

        "today": today,

        "m1": m1,

        "m3": m3,

        "m6": m6,

        "m9": m9,

        "y1": y1,

        "y5": y5,

        "high": high,

        "low": low,

        "volume": volume,

        "score": (
            round(score, 1)
            if score is not None
            else None
        ),

        "marketCap": num(
            trade.get(
                "totalMarketCap"
            )
        ),

        "pe": num(
            security.get(
                "pdSymbolPe"
            )
        ),

        "sector": (
            security.get("sector")
            or security.get(
                "industryInfo"
            )
        ),

        "lastUpdateTime":
            quote.get(
                "lastUpdateTime"
            ),

        "points": points
    }


# =========================================================
# NIFTY 500 OPPORTUNITIES
# =========================================================

def simple_market_screen(nse):

    result = {}

    try:

        data = (
            nse.listEquityStocksByIndex(
                index="NIFTY 500"
            )
        )

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        for row in rows:

            if not isinstance(row, dict):
                continue

            symbol = row.get(
                "symbol"
            )

            if not symbol:
                continue

            last = num(
                find(
                    row,
                    "lastPrice",
                    "ltp",
                    "last"
                )
            )

            change = num(
                find(
                    row,
                    "pChange",
                    "percentChange",
                    "change"
                )
            )

            if last is None:
                continue

            result[symbol] = {

                "name": (
                    row.get("meta")
                    or row.get(
                        "symbolInfo"
                    )
                    or symbol
                ),

                "last": last,

                "today": change,

                "high": num(
                    find(
                        row,
                        "yearHigh",
                        "52WeekHigh"
                    )
                ),

                "low": num(
                    find(
                        row,
                        "yearLow",
                        "52WeekLow"
                    )
                ),

                "score": None,

                "points": []
            }

    except Exception as error:

        print(
            "NIFTY 500 screen unavailable:",
            repr(error)
        )

    return result


# =========================================================
# NIFTY 50
# =========================================================

def fetch_nifty50():

    import requests

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent":
                "Mozilla/5.0",

            "Accept":
                "application/json, text/plain, */*",

            "Referer":
                "https://www.nseindia.com/"
        }
    )

    try:

        session.get(
            "https://www.nseindia.com/",
            timeout=15
        )

        response = session.get(
            "https://www.nseindia.com/api/equity-stock-indices",
            params={
                "index": "NIFTY 50"
            },
            timeout=15
        )

        response.raise_for_status()

        payload = response.json()

        if isinstance(payload, dict):

            rows = (
                payload.get("data")
                or payload.get("Table")
                or []
            )

        elif isinstance(payload, list):

            rows = payload

        else:

            rows = []

        if not rows:
            return None

        row = rows[0]

        if not isinstance(row, dict):
            return None

        last = num(
            find(
                row,
                "last",
                "lastPrice",
                "ltp",
                "indexValue"
            )
        )

        previous = num(
            find(
                row,
                "previousClose",
                "prevClose",
                "prev_close"
            )
        )

        change = num(
            find(
                row,
                "percentChange",
                "pChange"
            )
        )

        if last is None:
            return None

        if change is None:
            change = pct(
                last,
                previous
            )

        return {

            "last": last,

            "prev": previous,

            "today": change,

            "source": "NSE"
        }

    except Exception as error:

        print(
            "NIFTY 50 unavailable:",
            repr(error)
        )

        return None

    finally:

        session.close()


# =========================================================
# SENSEX
# =========================================================

def fetch_sensex():

    import requests

    url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/%5EBSESN"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0",

        "Accept":
            "application/json"
    }

    try:

        response = requests.get(
            url,

            params={
                "range": "1d",
                "interval": "5m"
            },

            headers=headers,

            timeout=20
        )

        response.raise_for_status()

        payload = response.json()

        result = (
            payload
            .get("chart", {})
            .get("result")
        )

        if not result:
            return None

        meta = result[0].get(
            "meta",
            {}
        )

        last = num(
            meta.get(
                "regularMarketPrice"
            )
        )

        previous = num(
            meta.get(
                "previousClose"
            )
            or
            meta.get(
                "chartPreviousClose"
            )
        )

        if last is None:
            return None

        change = pct(
            last,
            previous
        )

        print(
            "SENSEX OK",
            round(last, 2),
            "change:",
            change
        )

        return {

            "last": last,

            "prev": previous,

            "today": change,

            "source":
                "Yahoo Finance delayed"
        }

    except Exception as error:

        print(
            "SENSEX unavailable:",
            repr(error)
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    Path(
        "nse_cache"
    ).mkdir(
        exist_ok=True
    )

    Path(
        "bse_cache"
    ).mkdir(
        exist_ok=True
    )

    # Previous snapshot
    try:

        previous_snapshot = json.loads(
            Path(
                "data.json"
            ).read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        previous_snapshot = {}

    stocks = {}

    failures = []

    markets = {}

    # =====================================================
    # NSE
    # =====================================================

    with NSE(
        "nse_cache",
        server=True,
        timeout=20
    ) as nse:

        # -------------------------------------------------
        # PERSONAL STOCKS
        # -------------------------------------------------

        for symbol, name in WATCH.items():

            try:

                print(
                    "Fetching",
                    symbol
                )

                stocks[symbol] = quote_row(
                    nse,
                    symbol,
                    name
                )

                print(
                    "OK",
                    symbol,
                    stocks[symbol].get(
                        "last"
                    )
                )

            except Exception as error:

                failures.append(
                    f"{symbol}: {error!r}"
                )

                print(
                    "FAIL",
                    symbol,
                    repr(error)
                )

        # -------------------------------------------------
        # OPPORTUNITIES
        # -------------------------------------------------

        try:

            opportunities = (
                simple_market_screen(
                    nse
                )
            )

        except Exception as error:

            print(
                "Opportunity screen failed:",
                repr(error)
            )

            opportunities = {}

    # =====================================================
    # NIFTY
    # =====================================================

    nifty = fetch_nifty50()

    if nifty:

        markets[
            "NIFTY 50"
        ] = nifty

    else:

        old_nifty = (
            previous_snapshot
            .get("markets", {})
            .get("NIFTY 50")
        )

        if old_nifty:

            markets[
                "NIFTY 50"
            ] = old_nifty

    # =====================================================
    # SENSEX
    # =====================================================

    sensex = fetch_sensex()

    if sensex:

        markets[
            "SENSEX"
        ] = sensex

    else:

        old_sensex = (
            previous_snapshot
            .get("markets", {})
            .get("SENSEX")
        )

        if old_sensex:

            markets[
                "SENSEX"
            ] = old_sensex

    # =====================================================
    # PRESERVE GOOD STOCK DATA
    # =====================================================

    for symbol in WATCH:

        current = stocks.get(
            symbol,
            {}
        )

        if (
            current.get("last")
            is None
        ):

            old = (
                previous_snapshot
                .get("stocks", {})
                .get(symbol)
            )

            if old:

                stocks[
                    symbol
                ] = old

    # =====================================================
    # SAFETY CHECK
    # =====================================================

    usable = [

        symbol

        for symbol in WATCH

        if stocks.get(
            symbol,
            {}
        ).get("last") is not None
    ]

    if not usable:

        raise RuntimeError(
            "No usable personal stock quotes."
        )

    # =====================================================
    # OUTPUT
    # =====================================================

    output = {

        "version":
            "5.8",

        "updatedAt":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "NSE/BSE public delayed data",

        "personalStocksUpdated":
            usable,

        "stockFailures":
            failures,

        "stocks":
            stocks,

        "markets":
            markets,

        "opportunities":
            opportunities
    }

    Path(
        "data.json"
    ).write_text(

        json.dumps(
            output,
            separators=(
                ",",
                ":"
            )
        ),

        encoding="utf-8"
    )

    print()
    print(
        "======================================"
    )

    print(
        "V5.8 UPDATE COMPLETE"
    )

    print(
        "======================================"
    )

    print(
        "Personal stocks:",
        usable
    )

    print(
        "Historical points:"
    )

    for symbol in usable:

        print(
            " ",
            symbol,
            len(
                stocks[symbol].get(
                    "points",
                    []
                )
            )
        )

    print(
        "Markets:",
        list(
            markets.keys()
        )
    )

    print(
        "======================================")


if __name__ == "__main__":
    main()