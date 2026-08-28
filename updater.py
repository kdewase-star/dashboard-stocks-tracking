import json
import math
import subprocess
import sys
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

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

# Common user-added symbols are prioritized so their historical data appears
# quickly. NIFTY 500 symbols are then processed in batches.
PRIORITY_HISTORY = [
    "TCS","INFY","RELIANCE","GTLINFRA","HAL","MAZDOCK","GRSE","RVNL","IRFC",
    "HDFCBANK","ICICIBANK","SBIN","LT","HCLTECH","WIPRO","SUNPHARMA","DRREDDY",
    "CIPLA","TATAPOWER","ONGC","NTPC","COALINDIA","ITC","TITAN","MARUTI",
    "AXISBANK","KOTAKBANK","ADANIENT","ADANIPORTS"
]
HISTORY_BATCH_SIZE = 120
HISTORY_MAX_AGE_HOURS = 24


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
    yahoo_symbol = symbol.upper() + ".NS"
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * years + 30)
    end = dt.datetime.now(dt.timezone.utc)
    r = __import__("requests").get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
        params={
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()
    result = first_mapping((payload.get("chart") or {}).get("result"))
    ts = result.get("timestamp") or []
    quote = first_mapping((result.get("indicators") or {}).get("quote"))
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    points = []
    for i, t in enumerate(ts):
        c = num(closes[i]) if i < len(closes) else None
        if c is None or c <= 0:
            continue
        v = num(volumes[i]) if i < len(volumes) else 0
        points.append({"t": int(t), "c": round(c, 4), "v": int(v or 0)})
    return sorted(points, key=lambda x: x["t"])


def historical_close(points, days):
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


def historical_fields(last, points):
    periods = {"m1":30,"m3":91,"m6":182,"m9":274,"y1":365,"y5":1826}
    out = {}
    for key, days in periods.items():
        c = historical_close(points, days)
        out[key + "Price"] = c
        out[key] = pct(last, c)
    out["allTimePrice"] = points[0]["c"] if points else None
    out["allTime"] = pct(last, out["allTimePrice"]) if points else None
    return out


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def market_cap_crore(raw):
    # NSE tradeInfo.totalMarketCap is reported in ₹ lakh.
    # Convert lakh -> crore by dividing by 100.
    n = num(raw)
    return round(n / 100.0, 2) if n is not None else None


def current_quote(nse, symbol, name, previous):
    quote = nse.quote(symbol)
    if not isinstance(quote, dict):
        raise RuntimeError("NSE quote returned non-object payload")
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
            fresh = yahoo_history(symbol, years=10)
            if len(fresh) >= 30:
                points = fresh
        except Exception as exc:
            print(f"History failed {symbol}: {exc!r}")
    if points:
        last = last if last is not None else points[-1]["c"]
        prev = prev if prev is not None and prev > 0 else (points[-2]["c"] if len(points)>1 else None)
        high = high if high is not None else max(p["c"] for p in points[-252:])
        low = low if low is not None else min(p["c"] for p in points[-252:])
        volume = volume if volume is not None else points[-1].get("v")
    if last is None:
        raise RuntimeError("Current price unavailable")
    today = today if today is not None else pct(last, prev)
    out = {
        "name": name,
        "last": last,
        "prev": prev,
        "today": today,
        "high": high,
        "low": low,
        "volume": volume,
        "marketCap": market_cap_crore(trade.get("totalMarketCap")),
        "marketCapUnit": "Cr",
        "pe": num(sec.get("pdSymbolPe")),
        "sector": sec.get("sector") or sec.get("industryInfo"),
        "lastUpdateTime": quote.get("lastUpdateTime"),
        "points": points,
        "historySource": "Yahoo Finance chart API",
    }
    out.update(historical_fields(last, points))
    return out


def fetch_nifty50():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*","Referer":"https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com/", timeout=15)
        r = s.get("https://www.nseindia.com/api/equity-stock-indices",
                   params={"index":"NIFTY 50"}, timeout=15)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("data", payload.get("Table", [])) if isinstance(payload, dict) else payload
        row = first_mapping(rows)
        last = num(row.get("last")) or num(row.get("lastPrice")) or num(row.get("ltp")) or num(row.get("indexValue"))
        prev = num(row.get("previousClose")) or num(row.get("prevClose"))
        if last is None:
            return None
        return {"last":last,"prev":prev,"today":pct(last,prev),"source":"NSE","updatedAt":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        print("NIFTY unavailable:", repr(exc))
        return None
    finally:
        s.close()


def fetch_sensex():
    import requests
    try:
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN",
                         params={"range":"1d","interval":"5m"},
                         headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}, timeout=20)
        r.raise_for_status()
        meta = first_mapping(first_mapping((r.json().get("chart") or {}).get("result")).get("meta"))
        last = num(meta.get("regularMarketPrice"))
        prev = num(meta.get("previousClose") or meta.get("chartPreviousClose"))
        if last is None: return None
        return {"last":last,"prev":prev,"today":pct(last,prev),"source":"Yahoo Finance delayed","updatedAt":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        print("SENSEX unavailable:", repr(exc))
        return None


def opportunity_score(r):
    today = num(r.get("today")) or 0
    high, low, last = num(r.get("high")), num(r.get("low")), num(r.get("last"))
    volume = num(r.get("volume")) or 0
    momentum = max(0.0, min(30.0, 15.0 + today*3.0))
    range_position = near_high = 12.5
    if last and high and low and high > low:
        pos = max(0.0, min(1.0, (last-low)/(high-low)))
        range_position = pos*25.0
        near_high = max(0.0, min(1.0, 1.0-(high-last)/high))*25.0
    liquidity = min(20.0, max(0.0, math.log10(max(volume,1))*2.5))
    return round(momentum+range_position+near_high+liquidity,1)


def simple_market_screen(nse, previous=None):
    result = {}
    try:
        data = nse.listEquityStocksByIndex(index="NIFTY 500")
        rows = data.get("data", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict): continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol: continue
            last = num(row.get("lastPrice")) or num(row.get("ltp")) or num(row.get("last"))
            if last is None or last <= 0: continue
            prev = num(row.get("previousClose"))
            today = num(row.get("pChange"))
            if today is None: today = pct(last, prev)
            high = num(row.get("yearHigh") or row.get("52WeekHigh"))
            low = num(row.get("yearLow") or row.get("52WeekLow"))
            ffmc = num(row.get("ffmc"))
            mc = market_cap_crore(row.get("marketCap") or row.get("marketCapValue") or row.get("ffmc"))
            rec = {
                "name": row.get("companyName") or row.get("meta") or row.get("symbolInfo") or symbol,
                "last": last, "prev": prev, "today": today, "high": high, "low": low,
                "volume": num(row.get("totalTradedVolume") or row.get("volume")),
                "marketCap": mc, "marketCapUnit": "Cr",
                "ffmc": ffmc,
                "sector": row.get("industry") or row.get("sector") or row.get("industryInfo"),
                "m1": num(row.get("perChange30d")), "y1": num(row.get("perChange365d")),
            }
            rec["score"] = opportunity_score(rec)
            rec["strength"] = round(((last-low)/(high-low))*100,1) if high and low and high>low else None
            result[symbol] = rec
    except Exception as exc:
        print("NIFTY500 unavailable:", repr(exc))
    return result or (previous or {})


def update_history_cache(opportunities, old_cache):
    cache = dict(old_cache)
    now = datetime.now(timezone.utc)
    symbols = list(opportunities)
    priority = [s for s in PRIORITY_HISTORY if s not in symbols]
    ordered = priority + symbols

    needs = []
    for s in ordered:
        old = cache.get(s) if isinstance(cache.get(s), dict) else {}
        try:
            stamp = datetime.fromisoformat(str(old.get("updatedAt")).replace("Z","+00:00"))
            fresh = (now - stamp).total_seconds() < HISTORY_MAX_AGE_HOURS*3600
        except Exception:
            fresh = False
        if not fresh or not old.get("points"):
            needs.append(s)

    batch = needs[:HISTORY_BATCH_SIZE]

    def one(symbol):
        try:
            points = yahoo_history(symbol, years=10)
            if len(points) < 30:
                return symbol, None, f"insufficient points: {len(points)}"
            last = opportunities.get(symbol,{}).get("last") or points[-1]["c"]
            h = historical_fields(last, points)
            # Keep only the recent chart points + period anchors to keep JSON compact.
            compact = {
                "updatedAt": now.isoformat(),
                "name": opportunities.get(symbol,{}).get("name", symbol),
                "last": last,
                "points": points[-260:],
                **h,
            }
            return symbol, compact, None
        except Exception as exc:
            return symbol, None, repr(exc)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs=[pool.submit(one,s) for s in batch]
        for fut in as_completed(futs):
            symbol, value, err = fut.result()
            if value:
                cache[symbol]=value
                print("History cache OK",symbol,len(value["points"]))
            else:
                print("History cache FAIL",symbol,err)

    Path("history-cache.json").write_text(
        json.dumps({"version":2,"updatedAt":now.isoformat(),"stocks":cache}, separators=(",",":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return cache


def main():
    Path("nse_cache").mkdir(exist_ok=True)
    previous = load_json("data.json", {})
    previous_stocks = previous.get("stocks", {}) if isinstance(previous, dict) else {}
    previous_stocks = previous_stocks if isinstance(previous_stocks, dict) else {}
    previous_opportunities = previous.get("opportunities", {}) if isinstance(previous, dict) else {}
    previous_opportunities = previous_opportunities if isinstance(previous_opportunities, dict) else {}

    stocks = {s: dict(previous_stocks[s]) for s in WATCH if isinstance(previous_stocks.get(s),dict)}
    failures=[]
    with NSE("nse_cache", server=True, timeout=20) as nse:
        for symbol,name in WATCH.items():
            try:
                stocks[symbol]=current_quote(nse,symbol,name,previous_stocks.get(symbol))
            except Exception as exc:
                failures.append(f"{symbol}: {exc!r}")
                print("FAIL",symbol,repr(exc))
        # Also refresh common user-added symbols so current quotes are available.
        for symbol in PRIORITY_HISTORY:
            if symbol in stocks: continue
            try:
                name = previous_opportunities.get(symbol,{}).get("name",symbol)
                stocks[symbol]=current_quote(nse,symbol,name,previous_stocks.get(symbol))
                print("EXTRA OK",symbol,stocks[symbol].get("last"))
            except Exception as exc:
                # Extra symbols are optional; do not fail the whole run.
                print("EXTRA FAIL",symbol,repr(exc))
        opportunities=simple_market_screen(nse,previous_opportunities)

    history_cache=update_history_cache(opportunities,load_json("history-cache.json",{}).get("stocks",{}))
    # Apply cached history into opportunity records.
    for symbol,rec in opportunities.items():
        h=history_cache.get(symbol)
        if not isinstance(h,dict): continue
        for key in ("m1Price","m3Price","m6Price","m9Price","y1Price","y5Price","allTimePrice","m1","m3","m6","m9","y1","y5","allTime"):
            if h.get(key) is not None: rec[key]=h[key]

    markets=dict(previous.get("markets",{})) if isinstance(previous,dict) else {}
    nifty=fetch_nifty50()
    if nifty is not None: markets["NIFTY 50"]=nifty
    sensex=fetch_sensex()
    if sensex is not None: markets["SENSEX"]=sensex

    now=datetime.now(timezone.utc).isoformat()
    usable=[s for s in stocks if stocks.get(s,{}).get("last") is not None]
    output={
        "version":"7.0",
        "updatedAt":now if usable else previous.get("updatedAt"),
        "attemptedAt":now,
        "source":"NSE/BSE current data + Yahoo Finance historical data",
        "personalStocksUpdated":[s for s in WATCH if stocks.get(s,{}).get("last") is not None],
        "stockFailures":failures,
        "stocks":stocks,
        "markets":markets,
        "opportunities":opportunities,
        "historyCacheVersion":2,
        "opportunitySource":"NIFTY 500 public snapshot",
    }
    Path("data.json").write_text(json.dumps(output,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    print("UPDATE COMPLETE")
    print("personal",output["personalStocksUpdated"])
    print("failures",failures)
    print("opportunities",len(opportunities))
    print("history cached",len(history_cache))


if __name__=="__main__":
    main()
