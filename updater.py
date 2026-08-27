import sys
import subprocess
import json
import time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "nse[server]", "bse", "requests"],
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

def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except Exception:
        return None

def pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b not in (None, 0) else None

def split_chunks(start, end, max_days=100):
    out = []
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out

def normalize_history(rows):
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("Data") or rows.get("records") or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = row.get("CH_CLOSING_PRICE")
        ts = row.get("CH_TIMESTAMP") or row.get("mTIMESTAMP")
        if close is None or ts is None:
            continue
        try:
            import datetime as dt
            s = str(ts)
            try:
                d = dt.datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            except Exception:
                d = dt.datetime.strptime(s[:11].strip(), "%d-%b-%Y").replace(tzinfo=dt.timezone.utc)
            t = int(d.timestamp())
        except Exception:
            continue
        try:
            vol = int(float(row.get("CH_TOT_TRADED_QTY") or 0))
        except Exception:
            vol = 0
        out.append({"t": t, "date": d.date().isoformat(), "c": float(close), "v": vol})
    dedup = {x["date"]: x for x in out}
    return sorted(dedup.values(), key=lambda x: x["t"])

def old_close(points, days):
    if not points:
        return None
    target = time.time() - days * 86400
    candidate = points[0]["c"]
    for p in points:
        if p["t"] <= target:
            candidate = p["c"]
        else:
            break
    return candidate

def fetch_history_direct(symbol, from_date, to_date):
    """
    Direct NSE NextApi historical fetch in <=100-day chunks.
    This deliberately avoids a single multi-year request.
    """
    import requests

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
        "Accept-Language": "en-IN,en;q=0.9",
    })

    try:
        s.get("https://www.nseindia.com/", timeout=15)
        all_rows = []

        for c_from, c_to in split_chunks(from_date, to_date, 100):
            r = s.get(
                "https://www.nseindia.com/NextApi/apiClient/GetQuoteApi",
                params={
                    "functionName": "getHistoricalTradeData",
                    "symbol": symbol,
                    "series": "EQ",
                    "fromDate": c_from.strftime("%d-%m-%Y"),
                    "toDate": c_to.strftime("%d-%m-%Y"),
                },
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(rows, list):
                all_rows.extend(rows)

            # Be polite to NSE and avoid rapid-fire calls.
            time.sleep(0.25)

        points = normalize_history(all_rows)
        print(f"Direct history {symbol}: {len(points)} points")
        return points

    except Exception as e:
        print(f"Direct history failed {symbol}: {e!r}")
        return []

    finally:
        s.close()

def quote_row(nse, symbol, name, previous=None):
    q = nse.quote(symbol)
    meta = q.get("metaData", {})
    trade = q.get("tradeInfo", {})
    price = q.get("priceInfo", {})
    sec = q.get("secInfo", {})

    last = num(trade.get("lastPrice")) or num(meta.get("lastPrice"))
    prev = num(meta.get("previousClose"))
    today = num(meta.get("pChange"))
    high = num(price.get("yearHigh"))
    low = num(price.get("yearLow"))
    volume = num(trade.get("totalTradedVolume"))

    # History is fetched only when missing or too short. This keeps the 5-minute
    # updates lightweight after the initial successful history build.
    points = []
    existing = (previous or {}).get("points") or []
    history_ok = len(existing) >= 300

    if history_ok:
        points = existing
    else:
        try:
            points = fetch_history_direct(
                symbol,
                date.today() - timedelta(days=3650),
                date.today(),
            )
        except Exception as e:
            print(f"History exception {symbol}: {e!r}")

    if points:
        if last is None:
            last = points[-1]["c"]
        if prev is None and len(points) > 1:
            prev = points[-2]["c"]
        year = points[-252:]
        if high is None and year:
            high = max(p["c"] for p in year)
        if low is None and year:
            low = min(p["c"] for p in year)
        if volume is None:
            volume = points[-1]["v"]

    if today is None:
        today = pct(last, prev)

    m1 = pct(last, old_close(points, 30))
    m3 = pct(last, old_close(points, 91))
    m6 = pct(last, old_close(points, 182))
    m9 = pct(last, old_close(points, 274))
    y1 = pct(last, old_close(points, 365))
    y5 = pct(last, old_close(points, 1826))

    return {
        "name": name,
        "last": last,
        "prev": prev,
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
        "marketCap": num(trade.get("totalMarketCap")),
        "pe": num(sec.get("pdSymbolPe")),
        "sector": sec.get("sector") or sec.get("industryInfo"),
        "lastUpdateTime": q.get("lastUpdateTime"),
        "points": points,
    }

def fetch_nifty50():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com/", timeout=15)
        r = s.get(
            "https://www.nseindia.com/api/equity-stock-indices",
            params={"index": "NIFTY 50"},
            timeout=15,
        )
        r.raise_for_status()
        p = r.json()
        rows = p.get("data", p.get("Table", [])) if isinstance(p, dict) else p
        if not rows:
            return None
        row = rows[0]
        last = num(row.get("last")) or num(row.get("lastPrice")) or num(row.get("ltp")) or num(row.get("indexValue"))
        prev = num(row.get("previousClose")) or num(row.get("prevClose"))
        if last is None:
            return None
        return {"last": last, "prev": prev, "today": pct(last, prev), "source": "NSE"}
    except Exception as e:
        print("NIFTY 50 unavailable:", repr(e))
        return None
    finally:
        s.close()

def fetch_sensex():
    import requests
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN",
            params={"range": "1d", "interval": "5m"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        result = r.json().get("chart", {}).get("result")
        if not result:
            return None
        meta = result[0].get("meta", {})
        last = num(meta.get("regularMarketPrice"))
        prev = num(meta.get("previousClose") or meta.get("chartPreviousClose"))
        if last is None:
            return None
        return {"last": last, "prev": prev, "today": pct(last, prev), "source": "Yahoo Finance delayed"}
    except Exception as e:
        print("SENSEX unavailable:", repr(e))
        return None

def simple_market_screen(nse):
    result = {}
    try:
        data = nse.listEquityStocksByIndex(index="NIFTY 500")
        rows = data.get("data", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if not symbol:
                continue
            last = num(row.get("lastPrice") or row.get("ltp") or row.get("last"))
            change = num(row.get("pChange") or row.get("percentChange") or row.get("change"))
            if last is not None:
                result[symbol] = {
                    "name": row.get("meta") or row.get("symbolInfo") or symbol,
                    "last": last, "today": change,
                    "high": num(row.get("yearHigh") or row.get("52WeekHigh")),
                    "low": num(row.get("yearLow") or row.get("52WeekLow")),
                    "score": None, "points": [],
                }
    except Exception as e:
        print("NIFTY 500 screen unavailable:", repr(e))
    return result

def main():
    Path("nse_cache").mkdir(exist_ok=True)
    previous = {}
    try:
        previous = json.loads(Path("data.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    stocks = {}
    failures = []
    markets = {}

    with NSE("nse_cache", server=True, timeout=20) as nse:
        for symbol, name in WATCH.items():
            try:
                old = previous.get("stocks", {}).get(symbol)
                stocks[symbol] = quote_row(nse, symbol, name, old)
                print("OK", symbol, stocks[symbol].get("last"))
            except Exception as e:
                failures.append(f"{symbol}: {e!r}")
                print("FAIL", symbol, repr(e))

        opportunities = simple_market_screen(nse)

    nifty = fetch_nifty50()
    if nifty:
        markets["NIFTY 50"] = nifty
    elif previous.get("markets", {}).get("NIFTY 50"):
        markets["NIFTY 50"] = previous["markets"]["NIFTY 50"]

    sensex = fetch_sensex()
    if sensex:
        markets["SENSEX"] = sensex
    elif previous.get("markets", {}).get("SENSEX"):
        markets["SENSEX"] = previous["markets"]["SENSEX"]

    usable = [s for s in WATCH if stocks.get(s, {}).get("last") is not None]
    if not usable:
        raise RuntimeError("No usable personal stock quotes.")

    output = {
        "version": "5.8.1",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "NSE/BSE public delayed data",
        "personalStocksUpdated": usable,
        "stockFailures": failures,
        "stocks": stocks,
        "markets": markets,
        "opportunities": opportunities,
    }

    Path("data.json").write_text(
        json.dumps(output, separators=(",", ":")),
        encoding="utf-8",
    )

    print("========================================")
    print("V5.8.1 UPDATE COMPLETE")
    print("Personal stocks:", usable)
    print("Markets:", list(markets))
    print("Historical points:", {s: len(stocks[s].get("points", [])) for s in usable})
    print("========================================")

if __name__ == "__main__":
    main()
