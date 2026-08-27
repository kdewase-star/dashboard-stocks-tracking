import sys
import subprocess
import json
import time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

# V5.7.1
# Fixes:
# 1. markets variable initialization
# 2. Robust SENSEX response parsing
# 3. NIFTY 50 market data
# 4. Preserves working 5-stock personal watchlist
# 5. Preserves broader NIFTY 500 opportunity candidates

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "nse[server]", "bse", "requests"],
    check=True
)

from nse import NSE


WATCH = {
    "ABB": "ABB India",
    "BDL": "Bharat Dynamics",
    "BPCL": "BPCL",
    "BEL": "Bharat Electronics",
    "CUPID": "Cupid",
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
        if key in data and data[key] not in (None, ""):
            return data[key]

    return None


def pct(current, previous):
    if current is None or previous in (None, 0):
        return None

    return round((current / previous - 1) * 100, 2)


def historical_points(rows):
    result = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        close = find(
            row,
            "CH_CLOSING_PRICE",
            "CH_LAST_TRADED_PRICE",
            "close",
            "Close"
        )

        timestamp = find(
            row,
            "CH_TIMESTAMP",
            "mTIMESTAMP",
            "timestamp",
            "date"
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
            volume = int(float(volume or 0))
        except Exception:
            volume = 0

        try:
            if isinstance(timestamp, str) and "-" in timestamp:
                import datetime as dt

                parsed = dt.datetime.strptime(
                    timestamp[:10],
                    "%Y-%m-%d"
                )

                t = int(
                    parsed.replace(
                        tzinfo=dt.timezone.utc
                    ).timestamp()
                )
            else:
                t = len(result)

        except Exception:
            t = len(result)

        result.append({
            "t": t,
            "c": round(close, 4),
            "v": volume
        })

    result.sort(key=lambda x: x["t"])

    return result


def old_close(points, days):
    if not points:
        return None

    target = time.time() - days * 86400

    candidate = points[0]["c"]

    for point in points:
        if point["t"] <= target:
            candidate = point["c"]
        else:
            break

    return candidate


def quote_row(nse, symbol, name):
    quote = nse.quote(symbol)

    meta = quote.get("metaData", {})
    price = quote.get("priceInfo", {})
    trade = quote.get("tradeInfo", {})
    security = quote.get("secInfo", {})

    last = (
        num(trade.get("lastPrice"))
        or num(quote.get("orderBook", {}).get("lastPrice"))
        or num(meta.get("lastPrice"))
    )

    previous = num(meta.get("previousClose"))
    today = num(meta.get("pChange"))

    high = num(price.get("yearHigh"))
    low = num(price.get("yearLow"))

    volume = num(trade.get("totalTradedVolume"))

    points = []

    try:
        from_date = date.today() - timedelta(days=365 * 10 + 20)

        rows = nse.fetch_equity_historical_data(
            symbol,
            from_date=from_date,
            to_date=date.today()
        )

        points = historical_points(rows)

    except Exception as error:
        print(
            "Historical data unavailable for",
            symbol,
            repr(error)
        )

    if points:

        if last is None:
            last = points[-1]["c"]

        if previous is None and len(points) > 1:
            previous = points[-2]["c"]

        last_year = points[-252:]

        if high is None and last_year:
            high = max(x["c"] for x in last_year)

        if low is None and last_year:
            low = min(x["c"] for x in last_year)

        if volume is None:
            volume = points[-1]["v"]

    if today is None:
        today = pct(last, previous)

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
                    if high and last >= high * 0.97
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
        "score": round(score, 1) if score is not None else None,
        "marketCap": num(
            trade.get("totalMarketCap")
        ),
        "pe": num(
            security.get("pdSymbolPe")
        ),
        "sector": (
            security.get("sector")
            or security.get("industryInfo")
        ),
        "lastUpdateTime": quote.get(
            "lastUpdateTime"
        ),
        "points": points,
    }


def simple_market_screen(nse):
    result = {}

    try:
        data = nse.listEquityStocksByIndex(
            index="NIFTY 500"
        )

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        for row in rows:

            if not isinstance(row, dict):
                continue

            symbol = row.get("symbol")

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
                    or row.get("symbolInfo")
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

    try:
        gainers = nse.liveVolumeGainers()

        rows = (
            gainers.get("data", [])
            if isinstance(gainers, dict)
            else []
        )

        for row in rows[:50]:

            if not isinstance(row, dict):
                continue

            symbol = row.get("symbol")

            if not symbol:
                continue

            result.setdefault(
                symbol,
                {
                    "name": symbol,
                    "last": num(
                        find(
                            row,
                            "ltp",
                            "lastPrice"
                        )
                    ),
                    "today": num(
                        find(
                            row,
                            "pChange",
                            "percentChange"
                        )
                    ),
                    "high": None,
                    "low": None,
                    "score": None,
                    "points": []
                }
            )

    except Exception as error:
        print(
            "Volume-gainer screen unavailable:",
            repr(error)
        )

    return result


def fetch_nifty50():
    """
    Fetch NIFTY 50 directly from NSE's public index endpoint.
    """

    import requests

    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
        "Accept-Language": "en-IN,en;q=0.9",
    }

    session.headers.update(headers)

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

        rows = []

        if isinstance(payload, dict):
            rows = payload.get(
                "data",
                payload.get("Table", [])
            )

        elif isinstance(payload, list):
            rows = payload

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
            change = pct(last, previous)

        return {
            "last": last,
            "prev": previous,
            "today": change,
            "source": "NSE"
        }

    except Exception as error:

        print(
            "NIFTY 50 endpoint unavailable:",
            repr(error)
        )

        return None

    finally:
        session.close()



def fetch_sensex():
    """
    Fetch SENSEX using Yahoo Finance's public delayed endpoint.

    This is used as a fallback because the BSE public endpoint
    intermittently returns incompatible response formats or fails.
    """

    import requests

    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            url,
            params={
                "range": "1d",
                "interval": "5m",
            },
            headers=headers,
            timeout=20,
        )

        response.raise_for_status()

        payload = response.json()

        result = payload.get("chart", {}).get("result")

        if not result:
            print("SENSEX Yahoo returned no result")
            return None

        meta = result[0].get("meta", {})

        last = num(
            meta.get("regularMarketPrice")
        )

        previous = num(
            meta.get("previousClose")
            or meta.get("chartPreviousClose")
        )

        if last is None:
            print("SENSEX Yahoo returned no price")
            return None

        change = pct(last, previous)

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
            "source": "Yahoo Finance delayed"
        }

    except Exception as error:
        print(
            "SENSEX Yahoo endpoint unavailable:",
            repr(error)
        )

        return None
def fetch_sensex_archive():
    """
    Fallback for SENSEX when the live BSE endpoint
    is temporarily unavailable.
    """

    try:

        from bse import BSE

        with BSE("bse_cache") as bse:

            for days_back in range(0, 8):

                day = (
                    date.today()
                    - timedelta(days=days_back)
                )

                try:

                    response = (
                        bse.fetchAllIndicesDataByDate(
                            day
                        )
                    )

                    if isinstance(response, dict):

                        rows = []

                        for key, value in response.items():

                            if (
                                "sensex"
                                in str(key).lower()
                            ):

                                if isinstance(value, list):
                                    rows.extend(value)

                                elif isinstance(value, dict):
                                    rows.append(value)

                    elif isinstance(response, list):

                        rows = response

                    else:

                        rows = []

                    for row in rows:

                        if not isinstance(row, dict):
                            continue

                        # Make sure this is actually Sensex.
                        text = json.dumps(
                            row
                        ).lower()

                        if "sensex" not in text:
                            continue

                        last = None
                        previous = None

                        for key, value in row.items():

                            number = num(value)

                            if number is None:
                                continue

                            key_lower = (
                                str(key).lower()
                            )

                            if (
                                "prev" in key_lower
                                and "close" in key_lower
                            ):
                                previous = number

                            elif (
                                "close" in key_lower
                                or "ltp" in key_lower
                                or "indexvalue" in key_lower
                            ):
                                last = number

                        if last is not None:

                            return {
                                "last": last,
                                "prev": previous,
                                "today": pct(
                                    last,
                                    previous
                                ),
                                "asOf": day.isoformat(),
                                "source": "BSE daily archive"
                            }

                except Exception as error:

                    print(
                        "SENSEX archive date failed:",
                        day,
                        repr(error)
                    )

    except Exception as error:

        print(
            "SENSEX archive unavailable:",
            repr(error)
        )

    return None


def load_previous_snapshot():
    try:

        return json.loads(
            Path("data.json").read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return {}


def main():

    Path("nse_cache").mkdir(
        exist_ok=True
    )

    Path("bse_cache").mkdir(
        exist_ok=True
    )

    previous_snapshot = (
        load_previous_snapshot()
    )

    stocks = {}
    failures = []

    # IMPORTANT:
    # markets is initialized BEFORE any market
    # data is fetched.
    markets = {}

    with NSE(
        "nse_cache",
        server=True,
        timeout=15
    ) as nse:

        # ------------------------------------------
        # PERSONAL WATCHLIST
        # ------------------------------------------

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
                    stocks[symbol].get("last")
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

        # ------------------------------------------
        # BROADER MARKET
        # ------------------------------------------

        try:

            opportunities = (
                simple_market_screen(nse)
            )

        except Exception as error:

            print(
                "Opportunity screen failed:",
                repr(error)
            )

            opportunities = {}

    # ----------------------------------------------
    # NIFTY 50
    # ----------------------------------------------

    nifty = fetch_nifty50()

    if nifty:

        markets["NIFTY 50"] = nifty

        print(
            "NIFTY 50:",
            nifty.get("last"),
            nifty.get("today")
        )

    else:

        # Preserve previous NIFTY if available.
        old_nifty = (
            previous_snapshot
            .get("markets", {})
            .get("NIFTY 50")
        )

        if old_nifty:

            markets["NIFTY 50"] = old_nifty

            print(
                "Using previous NIFTY 50 snapshot"
            )

        else:

            print(
                "NIFTY 50 unavailable"
            )

    # ----------------------------------------------
    # SENSEX
    # ----------------------------------------------

    sensex = fetch_sensex()

    if sensex:

        markets["SENSEX"] = sensex

        print(
            "SENSEX:",
            sensex.get("last"),
            sensex.get("today")
        )

    else:

        print(
            "Trying SENSEX archive..."
        )

        sensex = fetch_sensex_archive()

        if sensex:

            markets["SENSEX"] = sensex

            print(
                "SENSEX archive:",
                sensex.get("last"),
                sensex.get("today")
            )

        else:

            old_sensex = (
                previous_snapshot
                .get("markets", {})
                .get("SENSEX")
            )

            if old_sensex:

                markets["SENSEX"] = old_sensex

                print(
                    "Using previous SENSEX snapshot"
                )

            else:

                print(
                    "SENSEX unavailable"
                )

    # ----------------------------------------------
    # PRESERVE GOOD STOCK SNAPSHOTS
    # ----------------------------------------------

    for symbol in WATCH:

        current = stocks.get(symbol)

        if (
            not current
            or current.get("last") is None
        ):

            old = (
                previous_snapshot
                .get("stocks", {})
                .get(symbol)
            )

            if old:

                stocks[symbol] = old

                print(
                    "Using previous snapshot for",
                    symbol
                )

    # ----------------------------------------------
    # SAFETY CHECK
    # ----------------------------------------------

    usable_personal = [
        symbol
        for symbol in WATCH
        if (
            stocks.get(symbol, {})
            .get("last") is not None
        )
    ]

    if not usable_personal:

        raise RuntimeError(
            "NSE returned no usable personal stock quotes."
        )

    # ----------------------------------------------
    # FINAL DATA
    # ----------------------------------------------

    output = {
        "version": "5.7.1",
        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": (
            "NSE/BSE public delayed data"
        ),

        "personalStocksUpdated": (
            usable_personal
        ),

        "stockFailures": failures,

        "stocks": stocks,

        "markets": markets,

        "opportunities": opportunities,
    }

    Path("data.json").write_text(
        json.dumps(
            output,
            separators=(",", ":")
        ),
        encoding="utf-8"
    )

    print()
    print(
        "========================================"
    )
    print(
        "V5.7.1 DATA UPDATE COMPLETE"
    )
    print(
        "========================================"
    )

    print(
        "Personal stocks:",
        usable_personal
    )

    print(
        "Markets:",
        list(markets.keys())
    )

    print(
        "Opportunity candidates:",
        len(opportunities)
    )

    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
