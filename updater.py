import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# The GitHub Action intentionally installs only the public packages this updater uses.
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "nse[server]", "requests"],
    check=True,
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
        if value in (None, ""):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b not in (None, 0) else None

def first_mapping(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}

def yahoo_history(symbol, years=10):
    """Fetch daily OHLCV from Yahoo Finance's public chart endpoint."""
    import requests
    import datetime as dt

    yahoo_symbol = symbol.upper() + ".NS"
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * years + 30)
    end = dt.datetime.now(dt.timezone.utc)

    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
        params={
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        timeout=25,
    )
    r.raise_for_status()
    payload = r.json()
    chart = payload.get("chart") or {}
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise RuntimeError(f"Yahoo returned no result: {chart.get('error')}")

    result = first_mapping(results[0])
    timestamps = result.get("timestamp") or []
    quote = first_mapping((result.get("indicators") or {}).get("quote"))
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    points = []
    for i, timestamp in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        close = num(closes[i])
        if close is None or close <= 0:
            continue
        volume = num(volumes[i]) if i < len(volumes) else 0
        points.append({
            "t": int(timestamp),
            "c": round(close, 4),
            "v": int(volume or 0),
        })

    return sorted(
        {point["t"]: point for point in points}.values(),
        key=lambda point: point["t"],
    )

def historical_close(points, days):
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

def historical_fields(last, points):
    periods = {
        "m1": 30,
        "m3": 91,
        "m6": 182,
        "m9": 274,
        "y1": 365,
        "y5": 1826,
    }
    output = {}
    for key, days in periods.items():
        close = historical_close(points, days)
        output[f"{key}Price"] = close
        output[key] = pct(last, close)
    if points:
        output["allTimePrice"] = points[0]["c"]
        output["allTime"] = pct(last, points[0]["c"])
    else:
        output["allTimePrice"] = None
        output["allTime"] = None
    return output

def current_quote(nse, symbol, name, previous):
    quote = nse.quote(symbol)
    if not isinstance(quote, dict):
        raise RuntimeError("NSE quote returned a non-object payload")

    meta = first_mapping(quote.get("metaData"))
    price = first_mapping(quote.get("priceInfo"))
    trade = first_mapping(quote.get("tradeInfo"))
    sec = first_mapping(quote.get("secInfo"))

    last = num(trade.get("lastPrice")) or num(meta.get("lastPrice"))
    prev = num(meta.get("previousClose"))
    today = num(meta.get("pChange"))
    high = num(price.get("yearHigh"))
    low = num(price.get("yearLow"))
    volume = num(trade.get("totalTradedVolume"))

    previous_points = (previous or {}).get("points") or []
    points = previous_points
    if len(points) < 300:
        try:
            fresh_points = yahoo_history(symbol, years=10)
            if len(fresh_points) >= 30:
                points = fresh_points
                print(f"Yahoo history {symbol}: {len(points)} points")
            else:
                print(f"Yahoo history {symbol}: insufficient points ({len(fresh_points)})")
        except Exception as exc:
            # Never throw away a previously good history because a refresh failed.
            print(f"Yahoo history failed {symbol}: {exc!r}")

    if points:
        if last is None:
            last = points[-1]["c"]
        if prev is None and len(points) > 1:
            prev = points[-2]["c"]
        one_year = points[-252:]
        if high is None and one_year:
            high = max(point["c"] for point in one_year)
        if low is None and one_year:
            low = min(point["c"] for point in one_year)
        if volume is None:
            volume = points[-1].get("v")

    if last is None:
        raise RuntimeError("Current price unavailable")

    if today is None:
        today = pct(last, prev)

    hist = historical_fields(last, points)
    return {
        "name": name,
        "last": last,
        "prev": prev,
        "today": today,
        "high": high,
        "low": low,
        "volume": volume,
        "marketCap": num(trade.get("totalMarketCap")),
        "pe": num(sec.get("pdSymbolPe")),
        "sector": sec.get("sector") or sec.get("industryInfo"),
        "lastUpdateTime": quote.get("lastUpdateTime"),
        "points": points,
        "historySource": "Yahoo Finance chart API",
        **hist,
    }

def fetch_nifty50():
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com/", timeout=15)
        response = session.get(
            "https://www.nseindia.com/api/equity-stock-indices",
            params={"index": "NIFTY 50"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", payload.get("Table", [])) if isinstance(payload, dict) else payload
        row = first_mapping(rows)
        last = (
            num(row.get("last"))
            or num(row.get("lastPrice"))
            or num(row.get("ltp"))
            or num(row.get("indexValue"))
        )
        prev = num(row.get("previousClose")) or num(row.get("prevClose"))
        if last is None:
            return None
        return {
            "last": last,
            "prev": prev,
            "today": pct(last, prev),
            "source": "NSE",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        print("NIFTY 50 unavailable:", repr(exc))
        return None
    finally:
        session.close()

def fetch_sensex():
    import requests

    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN",
            params={"range": "1d", "interval": "5m"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        chart = payload.get("chart") or {}
        result = first_mapping(chart.get("result"))
        meta = first_mapping(result.get("meta"))
        last = num(meta.get("regularMarketPrice"))
        prev = num(meta.get("previousClose") or meta.get("chartPreviousClose"))
        if last is None:
            return None
        return {
            "last": last,
            "prev": prev,
            "today": pct(last, prev),
            "source": "Yahoo Finance delayed",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        print("SENSEX unavailable:", repr(exc))
        return None

def opportunity_score(record):
    today = num(record.get("today")) or 0
    high = num(record.get("high"))
    low = num(record.get("low"))
    last = num(record.get("last"))
    volume = num(record.get("volume")) or 0

    momentum = max(0.0, min(30.0, 15.0 + today * 3.0))
    range_position = 12.5
    near_high = 12.5
    if last and high and low and high > low:
        position = max(0.0, min(1.0, (last - low) / (high - low)))
        range_position = position * 25.0
        distance = max(0.0, min(1.0, 1.0 - (high - last) / high))
        near_high = distance * 25.0

    liquidity = min(20.0, max(0.0, math.log10(max(volume, 1)) * 2.5))
    return round(momentum + range_position + near_high + liquidity, 1)

def simple_market_screen(nse, previous_opportunities=None):
    result = {}
    try:
        data = nse.listEquityStocksByIndex(index="NIFTY 500")
        rows = data.get("data", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue

            last = (
                num(row.get("lastPrice"))
                or num(row.get("ltp"))
                or num(row.get("last"))
            )
            if last is None or last <= 0:
                continue

            today = num(row.get("pChange"))
            prev = num(row.get("previousClose"))
            if today is None and prev:
                today = pct(last, prev)

            high = num(row.get("yearHigh") or row.get("52WeekHigh"))
            low = num(row.get("yearLow") or row.get("52WeekLow"))
            record = {
                "name": row.get("companyName")
                or row.get("meta")
                or row.get("symbolInfo")
                or symbol,
                "last": last,
                "prev": prev,
                "today": today,
                "high": high,
                "low": low,
                "volume": num(row.get("totalTradedVolume") or row.get("volume")),
                "marketCap": (
                    num(row.get("marketCap"))
                    or num(row.get("marketCapValue"))
                    or num(row.get("ffmc"))
                ),
                "ffmc": num(row.get("ffmc")),
                "sector": (
                    row.get("industry")
                    or row.get("sector")
                    or row.get("industryInfo")
                ),
                "m1": num(row.get("perChange30d")),
                "y1": num(row.get("perChange365d")),
                "points": [],
            }
            record["score"] = opportunity_score(record)
            record["strength"] = (
                round(((last - low) / (high - low)) * 100, 1)
                if high is not None and low is not None and high > low
                else None
            )
            result[symbol] = record
    except Exception as exc:
        print("NIFTY 500 screen unavailable:", repr(exc))

    if not result:
        # Preserve a successful previous screen on a temporary source failure.
        return previous_opportunities or {}

    ranked = sorted(
        (x for x in result.values() if num(x.get("ffmc")) is not None),
        key=lambda x: num(x.get("ffmc")) or 0,
        reverse=True,
    )
    rank_by_symbol = {
        symbol: rank for rank, symbol in enumerate(
            [s for s, x in sorted(result.items(), key=lambda kv: num(kv[1].get("ffmc")) or 0, reverse=True)],
            start=1,
        )
    }
    total = max(len(ranked), 1)
    for symbol, record in result.items():
        rank = rank_by_symbol.get(symbol)
        if rank is None:
            record["capCategory"] = "Unclassified"
        elif rank <= max(50, round(total * 0.10)):
            record["capCategory"] = "Blue-chip"
        elif rank <= max(150, round(total * 0.30)):
            record["capCategory"] = "Large-cap"
        elif rank <= max(350, round(total * 0.70)):
            record["capCategory"] = "Mid-cap"
        else:
            record["capCategory"] = "Small-cap"
    return result

def load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value
    except Exception:
        return default

def merge_stock(previous, current):
    if not previous:
        return current
    merged = dict(previous)
    for key, value in current.items():
        if value is not None:
            merged[key] = value
    return merged

def main():
    Path("nse_cache").mkdir(exist_ok=True)
    previous = load_json("data.json", {})
    previous_stocks = previous.get("stocks") if isinstance(previous, dict) else {}
    previous_stocks = previous_stocks if isinstance(previous_stocks, dict) else {}
    previous_opportunities = previous.get("opportunities") if isinstance(previous, dict) else {}
    previous_opportunities = previous_opportunities if isinstance(previous_opportunities, dict) else {}

    stocks = {}
    failures = []

    # Seed with the last successful snapshot. Each stock is then updated independently.
    for symbol, name in WATCH.items():
        if isinstance(previous_stocks.get(symbol), dict):
            stocks[symbol] = dict(previous_stocks[symbol])
        else:
            stocks[symbol] = {"name": name}

    with NSE("nse_cache", server=True, timeout=20) as nse:
        for symbol, name in WATCH.items():
            try:
                fresh = current_quote(nse, symbol, name, previous_stocks.get(symbol))
                stocks[symbol] = merge_stock(previous_stocks.get(symbol), fresh)
                print("OK", symbol, stocks[symbol].get("last"))
            except Exception as exc:
                failures.append(f"{symbol}: {exc!r}")
                print("FAIL", symbol, repr(exc))

        opportunities = simple_market_screen(nse, previous_opportunities)

    previous_markets = previous.get("markets") if isinstance(previous, dict) else {}
    previous_markets = previous_markets if isinstance(previous_markets, dict) else {}
    markets = dict(previous_markets)

    nifty = fetch_nifty50()
    if nifty is not None:
        markets["NIFTY 50"] = nifty

    sensex = fetch_sensex()
    if sensex is not None:
        markets["SENSEX"] = sensex

    usable = [symbol for symbol in WATCH if stocks.get(symbol, {}).get("last") is not None]
    if not usable and not previous_stocks:
        raise RuntimeError("No usable personal stock quotes and no previous snapshot exists.")

    now = datetime.now(timezone.utc).isoformat()
    output = {
        "version": "6.0",
        # Keep the last successful snapshot time when no fresh personal quote succeeded.
        "updatedAt": now if usable else previous.get("updatedAt"),
        "attemptedAt": now,
        "source": "NSE/BSE current data + Yahoo Finance historical data",
        "personalStocksUpdated": usable,
        "stockFailures": failures,
        "stocks": stocks,
        "markets": markets,
        "opportunities": opportunities,
        "opportunitySource": "NIFTY 500 public snapshot",
    }
    Path("data.json").write_text(
        json.dumps(output, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    print("========================================")
    print("V6.0 UPDATE COMPLETE")
    print("Personal stocks:", usable)
    print("Failures:", len(failures))
    print("Markets:", list(markets))
    print("Opportunities:", len(opportunities))
    print("Historical points:", {
        symbol: len(stocks[symbol].get("points", [])) for symbol in usable
    })
    print("========================================")

if __name__ == "__main__":
    main()
