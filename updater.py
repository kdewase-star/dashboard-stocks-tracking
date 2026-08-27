import sys, subprocess, json, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "nse[server]", "requests"], check=True)
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

def yahoo_history(symbol, years=10):
    """Fetch daily OHLCV from Yahoo chart API using Unix period1/period2."""
    import requests
    import datetime as dt

    yahoo_symbol = symbol.upper() + ".NS"
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * years + 30)
    end = dt.datetime.now(dt.timezone.utc)

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "application/json",
    }

    r = requests.get(url, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    payload = r.json()

    result = (payload.get("chart") or {}).get("result")
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo returned no result: {err}")

    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    points = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        try:
            close = float(closes[i])
        except Exception:
            continue
        volume = 0
        if i < len(volumes) and volumes[i] is not None:
            try:
                volume = int(volumes[i])
            except Exception:
                pass
        points.append({
            "t": int(ts),
            "c": round(close, 4),
            "v": volume,
        })

    # Deduplicate timestamps and sort.
    points = sorted({p["t"]: p for p in points}.values(), key=lambda x: x["t"])
    return points

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

def current_quote(nse, symbol, name, previous):
    q = nse.quote(symbol)
    meta = q.get("metaData", {})
    price = q.get("priceInfo", {})
    trade = q.get("tradeInfo", {})
    sec = q.get("secInfo", {})

    last = num(trade.get("lastPrice")) or num(meta.get("lastPrice"))
    prev = num(meta.get("previousClose"))
    today = num(meta.get("pChange"))
    high = num(price.get("yearHigh"))
    low = num(price.get("yearLow"))
    volume = num(trade.get("totalTradedVolume"))

    # Reuse a successful cached history; otherwise fetch it once.
    points = (previous or {}).get("points") or []
    if len(points) < 300:
        try:
            points = yahoo_history(symbol, years=10)
            print(f"Yahoo history {symbol}: {len(points)} points")
        except Exception as e:
            print(f"Yahoo history failed {symbol}: {e!r}")
            points = []

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

    return {
        "name": name,
        "last": last,
        "prev": prev,
        "today": today,
        "m1": pct(last, old_close(points, 30)),
        "m3": pct(last, old_close(points, 91)),
        "m6": pct(last, old_close(points, 182)),
        "m9": pct(last, old_close(points, 274)),
        "y1": pct(last, old_close(points, 365)),
        "y5": pct(last, old_close(points, 1826)),
        "high": high,
        "low": low,
        "volume": volume,
        "marketCap": num(trade.get("totalMarketCap")),
        "pe": num(sec.get("pdSymbolPe")),
        "sector": sec.get("sector") or sec.get("industryInfo"),
        "lastUpdateTime": q.get("lastUpdateTime"),
        "points": points,
        "historySource": "Yahoo Finance chart API",
    }

def fetch_nifty50():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*","Referer":"https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com/", timeout=15)
        r = s.get("https://www.nseindia.com/api/equity-stock-indices", params={"index":"NIFTY 50"}, timeout=15)
        r.raise_for_status()
        p = r.json()
        rows = p.get("data", p.get("Table", [])) if isinstance(p, dict) else p
        if not rows: return None
        row = rows[0]
        last = num(row.get("last")) or num(row.get("lastPrice")) or num(row.get("ltp")) or num(row.get("indexValue"))
        prev = num(row.get("previousClose")) or num(row.get("prevClose"))
        if last is None: return None
        return {"last":last,"prev":prev,"today":pct(last,prev),"source":"NSE"}
    except Exception as e:
        print("NIFTY 50 unavailable:", repr(e)); return None
    finally:
        s.close()

def fetch_sensex():
    import requests
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN",
            params={"range":"1d","interval":"5m"},
            headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"},
            timeout=20,
        )
        r.raise_for_status()
        result = r.json().get("chart",{}).get("result")
        if not result: return None
        meta = result[0].get("meta",{})
        last = num(meta.get("regularMarketPrice"))
        prev = num(meta.get("previousClose") or meta.get("chartPreviousClose"))
        if last is None: return None
        return {"last":last,"prev":prev,"today":pct(last,prev),"source":"Yahoo Finance delayed"}
    except Exception as e:
        print("SENSEX unavailable:", repr(e)); return None

def simple_market_screen(nse):
    result = {}
    try:
        data = nse.listEquityStocksByIndex(index="NIFTY 500")
        rows = data.get("data",[]) if isinstance(data,dict) else []
        for row in rows:
            if not isinstance(row,dict): continue
            sym = row.get("symbol")
            if not sym: continue
            last = num(row.get("lastPrice") or row.get("ltp") or row.get("last"))
            ch = num(row.get("pChange") or row.get("percentChange") or row.get("change"))
            if last is not None:
                result[sym] = {
                    "name": row.get("meta") or row.get("symbolInfo") or sym,
                    "last": last, "today": ch,
                    "high": num(row.get("yearHigh") or row.get("52WeekHigh")),
                    "low": num(row.get("yearLow") or row.get("52WeekLow")),
                    "score": None, "points": []
                }
    except Exception as e:
        print("NIFTY 500 screen unavailable:",repr(e))
    return result

def main():
    Path("nse_cache").mkdir(exist_ok=True)
    previous = {}
    try:
        previous = json.loads(Path("data.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    stocks, failures, markets = {}, [], {}

    with NSE("nse_cache", server=True, timeout=20) as nse:
        for sym, name in WATCH.items():
            try:
                old = previous.get("stocks",{}).get(sym)
                stocks[sym] = current_quote(nse, sym, name, old)
                print("OK", sym, stocks[sym].get("last"))
            except Exception as e:
                failures.append(f"{sym}: {e!r}")
                print("FAIL", sym, repr(e))
        opportunities = simple_market_screen(nse)

    nifty = fetch_nifty50()
    if nifty: markets["NIFTY 50"] = nifty
    elif previous.get("markets",{}).get("NIFTY 50"): markets["NIFTY 50"] = previous["markets"]["NIFTY 50"]

    sensex = fetch_sensex()
    if sensex: markets["SENSEX"] = sensex
    elif previous.get("markets",{}).get("SENSEX"): markets["SENSEX"] = previous["markets"]["SENSEX"]

    usable = [s for s in WATCH if stocks.get(s,{}).get("last") is not None]
    if not usable: raise RuntimeError("No usable personal stock quotes.")

    output = {
        "version":"5.9",
        "updatedAt":datetime.now(timezone.utc).isoformat(),
        "source":"NSE/BSE current data + Yahoo Finance historical data",
        "personalStocksUpdated":usable,
        "stockFailures":failures,
        "stocks":stocks,
        "markets":markets,
        "opportunities":opportunities,
    }
    Path("data.json").write_text(json.dumps(output,separators=(",",":")),encoding="utf-8")

    print("========================================")
    print("V5.9 UPDATE COMPLETE")
    print("Personal stocks:", usable)
    print("Markets:", list(markets))
    print("Historical points:", {s:len(stocks[s].get("points",[])) for s in usable})
    print("========================================")

if __name__ == "__main__":
    main()
