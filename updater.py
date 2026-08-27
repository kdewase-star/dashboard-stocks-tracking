import sys, subprocess, json, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

# V5.4: use the maintained unofficial NSE client. It manages NSE cookies/sessions
# and the current package uses NSE's newer NextApi for equity history.
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "nse[server]"],
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

# Keep the first reliable version focused on the personal list.
# Market Opportunities are populated from NSE's own live gainer/loser/index
# endpoints where possible; this avoids hundreds of individual quote calls.

def num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def find(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None

def historical_points(rows):
    out = []
    for r in rows or []:
        close = find(r, "CH_CLOSING_PRICE", "CH_LAST_TRADED_PRICE")
        ts = find(r, "CH_TIMESTAMP", "mTIMESTAMP")
        qty = find(r, "CH_TOT_TRADED_QTY")
        if close is None or ts is None:
            continue
        try:
            # YYYY-MM-DD is preferred; otherwise keep the row index as a stable
            # chart position and use the original timestamp string.
            import datetime as dt
            if isinstance(ts, str) and "-" in ts:
                t = int(dt.datetime.strptime(ts[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
            else:
                t = len(out)
        except Exception:
            t = len(out)
        out.append({"t": t, "c": round(float(close), 4), "v": int(float(qty or 0))})
    return out

def pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b else None

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

def quote_row(nse, sym, name):
    q = nse.quote(sym)
    meta = q.get("metaData", {})
    depth = q.get("tradeInfo", {})
    price = q.get("priceInfo", {})
    sec = q.get("secInfo", {})

    last = num(depth.get("lastPrice")) or num(q.get("orderBook", {}).get("lastPrice")) or num(meta.get("lastPrice"))
    prev = num(meta.get("previousClose"))
    today = num(meta.get("pChange"))
    high = num(price.get("yearHigh"))
    low = num(price.get("yearLow"))
    volume = num(depth.get("totalTradedVolume"))

    # NSE's current historical endpoint is used by nse 3.x / NextApi.
    from_date = date.today() - timedelta(days=365*10 + 20)
    rows = nse.fetch_equity_historical_data(sym, from_date=from_date, to_date=date.today())
    points = historical_points(rows)

    if points:
        if last is None:
            last = points[-1]["c"]
        if prev is None and len(points) > 1:
            prev = points[-2]["c"]
        if high is None:
            high = max(p["c"] for p in points[-252:])
        if low is None:
            low = min(p["c"] for p in points[-252:])
        if volume is None:
            volume = points[-1]["v"]

    if today is None:
        today = pct(last, prev)

    all_time = points[0]["c"] if points else None
    score = None
    m1 = pct(last, old_close(points,30))
    m3 = pct(last, old_close(points,91))

    if today is not None:
        score = max(0, min(100,
            35 + today*3 +
            max(0,m1 or 0)*1.5 +
            max(0,m3 or 0)*0.5 +
            (5 if high and last >= high*0.97 else 0)
        ))

    return {
        "name": name,
        "last": last,
        "prev": prev,
        "today": today,
        "m1": m1,
        "m3": m3,
        "m6": pct(last, old_close(points,182)),
        "m9": pct(last, old_close(points,274)),
        "y1": pct(last, old_close(points,365)),
        "y5": pct(last, old_close(points,1826)),
        "high": high,
        "low": low,
        "volume": volume,
        "score": round(score,1) if score is not None else None,
        "marketCap": num(depth.get("totalMarketCap")),
        "pe": num(sec.get("pdSymbolPe")),
        "sector": sec.get("sector") or sec.get("industryInfo"),
        "lastUpdateTime": q.get("lastUpdateTime"),
        "points": points,
    }

def simple_market_screen(nse):
    out = {}
    # NIFTY 500 list is one NSE request and generally contains current change
    # information. We use it as a broad-market candidate pool rather than
    # individually quoting hundreds of stocks.
    try:
        d = nse.listEquityStocksByIndex(index="NIFTY 500")
        rows = d.get("data", []) if isinstance(d, dict) else []
        for r in rows:
            sym = r.get("symbol")
            if not sym:
                continue
            last = num(find(r,"lastPrice","ltp","last"))
            ch = num(find(r,"pChange","percentChange","change"))
            if last is None:
                continue
            out[sym] = {
                "name": r.get("meta") or r.get("symbolInfo") or sym,
                "last": last, "today": ch,
                "high": num(find(r,"yearHigh","52WeekHigh")),
                "low": num(find(r,"yearLow","52WeekLow")),
                "score": None, "points": []
            }
    except Exception as e:
        print("NIFTY 500 screen unavailable:", repr(e))

    # Add official NSE live volume gainers if available.
    try:
        vg = nse.liveVolumeGainers()
        for r in vg.get("data", [])[:20]:
            sym = r.get("symbol")
            if sym:
                out.setdefault(sym, {
                    "name": r.get("symbol") or sym,
                    "last": num(find(r,"ltp","lastPrice")),
                    "today": num(find(r,"pChange","percentChange")),
                    "high": None, "low": None, "score": None, "points": []
                })
    except Exception as e:
        print("volume-gainer screen unavailable:", repr(e))
    return out

def main():
    Path("nse_cache").mkdir(exist_ok=True)

    with NSE("nse_cache", server=True, timeout=15) as nse:
        stocks = {}
        failures = []

        # Five personal stocks only: deliberately slow/controlled rather than
        # hammering NSE. The package itself throttles NSE requests.
        for sym, name in WATCH.items():
            try:
                print("Fetching", sym)
                stocks[sym] = quote_row(nse, sym, name)
                print("OK", sym, stocks[sym]["last"])
            except Exception as e:
                failures.append(f"{sym}: {e!r}")
                print("FAIL", sym, repr(e))

        if not any(stocks.get(s, {}).get("last") is not None for s in WATCH):
            raise RuntimeError(
                "NSE returned no usable personal stock quotes. "
                + " | ".join(failures)
            )

        opportunities = simple_market_screen(nse)

        markets = {}
        # NIFTY 50 from NSE historical index data.
        try:
            idx_rows = nse.fetch_historical_index_data(
                "NIFTY 50",
                from_date=date.today() - timedelta(days=10),
                to_date=date.today(),
            )
            def idx_value(row):
                for k in ("CLOSE_INDEX_VAL", "CLOSE", "closingValue", "last"):
                    if row.get(k) not in (None, ""):
                        try:
                            return float(row[k])
                        except Exception:
                            pass
                return None
            vals = [idx_value(r) for r in idx_rows]
            vals = [v for v in vals if v is not None]
            if vals:
                last = vals[-1]
                prev = vals[-2] if len(vals) > 1 else None
                markets["NIFTY 50"] = {
                    "last": last,
                    "today": round((last / prev - 1) * 100, 2) if prev else None
                }
        except Exception as e:
            print("NIFTY 50 unavailable:", repr(e))

        # SENSEX from BSE's index archive. We keep this optional so a BSE
        # outage cannot break the five-stock NSE update.
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "bse"],
                check=True,
            )
            from bse import BSE
            with BSE("bse_cache") as bse:
                idx = bse.fetchAllIndicesDataByDate(date.today())
                rows = idx.get("S&P BSE SENSEX", [])
                if rows:
                    row = rows[-1]
                    last = None
                    for k, v in row.items():
                        if "close" in str(k).lower() and v not in (None, ""):
                            try:
                                last = float(v)
                                break
                            except Exception:
                                pass
                    if last is not None:
                        markets["SENSEX"] = {"last": last, "today": None}
        except Exception as e:
            print("SENSEX unavailable:", repr(e))

        # Preserve a previous good snapshot if one or more symbols temporarily
        # fail. Never replace a good personal stock with an empty record.
        previous = {}
        try:
            previous = json.loads(Path("data.json").read_text(encoding="utf-8"))
        except Exception:
            pass

        for sym in WATCH:
            if stocks.get(sym, {}).get("last") is None and previous.get("stocks", {}).get(sym):
                stocks[sym] = previous["stocks"][sym]

        out = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "NSE India via NseIndiaApi (unofficial client with cookie/session handling)",
            "personalStocksUpdated": [s for s in WATCH if stocks.get(s, {}).get("last") is not None],
            "stockFailures": failures,
            "stocks": stocks,
            "markets": markets,
            "opportunities": opportunities,
        }

        Path("data.json").write_text(json.dumps(out, separators=(",",":")), encoding="utf-8")
        print("Published personal stocks:", out["personalStocksUpdated"])
        print("Opportunity candidates:", len(opportunities))

if __name__ == "__main__":
    main()
