import json, time, urllib.request, urllib.parse
from datetime import datetime, timezone

# Personal watchlist. These five are mandatory: the workflow fails if none can be updated.
WATCH = {
    "ABB": "ABB India",
    "BDL": "Bharat Dynamics",
    "BPCL": "BPCL",
    "BEL": "Bharat Electronics",
    "CUPID": "Cupid",
}

# Broader market screen. Failures here are tolerated so the personal dashboard remains usable.
UNIVERSE = {
    "RELIANCE":"Reliance Industries","TCS":"Tata Consultancy Services","HDFCBANK":"HDFC Bank",
    "ICICIBANK":"ICICI Bank","INFY":"Infosys","SBIN":"State Bank of India","BHARTIARTL":"Bharti Airtel",
    "ITC":"ITC","LT":"Larsen & Toubro","AXISBANK":"Axis Bank","KOTAKBANK":"Kotak Mahindra Bank",
    "M&M":"Mahindra & Mahindra","SUNPHARMA":"Sun Pharma","MARUTI":"Maruti Suzuki",
    "HINDUNILVR":"Hindustan Unilever","TITAN":"Titan Company","BEL":"Bharat Electronics",
    "BDL":"Bharat Dynamics","HAL":"Hindustan Aeronautics","ADANIENT":"Adani Enterprises",
    "ADANIPORTS":"Adani Ports","NTPC":"NTPC","POWERGRID":"Power Grid","ONGC":"ONGC",
    "COALINDIA":"Coal India","BPCL":"BPCL","TATASTEEL":"Tata Steel","JSWSTEEL":"JSW Steel",
    "HINDALCO":"Hindalco","TRENT":"Trent","ETERNAL":"Eternal","INDIGO":"InterGlobe Aviation",
    "BAJFINANCE":"Bajaj Finance","BAJAJFINSV":"Bajaj Finserv","WIPRO":"Wipro","TECHM":"Tech Mahindra",
    "HCLTECH":"HCL Technologies","LTIM":"LTIMindtree","ASIANPAINT":"Asian Paints",
    "ULTRACEMCO":"UltraTech Cement","TATAMOTORS":"Tata Motors","TATACONSUM":"Tata Consumer",
    "NESTLEIND":"Nestle India","CIPLA":"Cipla","DRREDDY":"Dr Reddy's Laboratories",
    "EICHERMOT":"Eicher Motors","HEROMOTOCO":"Hero MotoCorp","TVSMOTOR":"TVS Motor",
    "INDUSINDBK":"IndusInd Bank","PNB":"Punjab National Bank","CANBK":"Canara Bank",
    "IRFC":"IRFC","RVNL":"Rail Vikas Nigam","IREDA":"IREDA","NHPC":"NHPC","HUDCO":"HUDCO",
    "SUZLON":"Suzlon Energy","YESBANK":"Yes Bank","IDEA":"Vodafone Idea","IOC":"Indian Oil",
    "GAIL":"GAIL","BHEL":"BHEL","CUPID":"Cupid"
}

ALL = dict(UNIVERSE)
ALL.update(WATCH)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

def fetch_url(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(raw.decode("utf-8"))

def get_chart(sym, attempts=3):
    q = urllib.parse.quote(sym + ".NS", safe="")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=10y&interval=1d&events=div%2Csplits",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{q}?range=10y&interval=1d&events=div%2Csplits",
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1=946684800&period2={int(time.time())}&interval=1d&events=div%2Csplits",
    ]
    last = None
    for attempt in range(attempts):
        for url in urls:
            try:
                j = fetch_url(url)
                result = j.get("chart", {}).get("result")
                if result and result[0].get("timestamp"):
                    return result[0]
                err = j.get("chart", {}).get("error")
                last = RuntimeError(str(err) if err else "empty chart result")
            except Exception as e:
                last = e
        time.sleep(2 + attempt * 2)
    raise RuntimeError(f"{sym}: {last}")

def clean(result):
    ts = result.get("timestamp", [])
    q = result.get("indicators", {}).get("quote", [{}])[0]
    closes = q.get("close", [])
    volumes = q.get("volume", [])
    points = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        v = volumes[i] if i < len(volumes) else 0
        if c is not None:
            points.append({"t": int(t), "c": round(float(c), 4), "v": int(v or 0)})

    if len(points) < 2:
        raise RuntimeError("not enough daily prices")

    last = points[-1]["c"]
    prev = points[-2]["c"]

    def old(days):
        target = time.time() - days * 86400
        candidate = points[0]
        for p in points:
            if p["t"] <= target:
                candidate = p
            else:
                break
        return candidate["c"]

    def pct(base):
        return round((last / base - 1) * 100, 2) if base else None

    year = points[-252:]
    high = max(p["c"] for p in year)
    low = min(p["c"] for p in year)

    recent_vol = [p["v"] for p in points[-21:-1] if p["v"]]
    avg20 = sum(recent_vol) / len(recent_vol) if recent_vol else 0
    volume_ratio = (points[-1]["v"] / avg20) if avg20 else 1

    today = pct(prev)
    m1 = pct(old(30))
    m3 = pct(old(91))

    # Indicative momentum screen only; not an investment prediction.
    score = (
        max(0, min(35, (today + 3) * 4))
        + max(0, min(25, (m1 + 5) * 2))
        + max(0, min(20, m3 + 10))
        + max(0, min(15, (volume_ratio - 0.8) * 15))
        + max(0, min(5, (pct(high) + 10) * 0.5))
    )

    return {
        "last": last,
        "prev": prev,
        "today": today,
        "m1": m1,
        "m3": m3,
        "m6": pct(old(182)),
        "m9": pct(old(274)),
        "y1": pct(old(365)),
        "y5": pct(old(1826)),
        "high": high,
        "low": low,
        "volume": points[-1]["v"],
        "score": round(score, 1),
        # Keep only the last 10 years of daily points, which is enough for the dashboard.
        "points": points,
    }

def get_index(symbol):
    q = urllib.parse.quote(symbol, safe="")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=5d&interval=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{q}?range=5d&interval=1d",
    ]
    last = None
    for url in urls:
        try:
            j = fetch_url(url)
            result = j.get("chart", {}).get("result")
            if result:
                return result[0]
        except Exception as e:
            last = e
    raise RuntimeError(f"{symbol}: {last}")

def clean_index(result):
    q = result.get("indicators", {}).get("quote", [{}])[0]
    closes = [x for x in q.get("close", []) if x is not None]
    if len(closes) < 2:
        raise RuntimeError("not enough index prices")
    return {
        "last": round(float(closes[-1]), 2),
        "today": round((closes[-1] / closes[-2] - 1) * 100, 2),
    }

def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    stocks = {}
    failures = []

    def fetch_one(item, attempts):
        sym, name = item
        try:
            x = clean(get_chart(sym, attempts=attempts))
            x["name"] = name
            return sym, x, None
        except Exception as e:
            return sym, None, str(e)

    # Personal stocks first, in parallel. This prevents one blocked symbol from
    # holding the whole workflow for several minutes.
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(fetch_one, item, 2) for item in WATCH.items()]
        for f in as_completed(futures):
            sym, x, err = f.result()
            if x:
                stocks[sym] = x
                print(f"OK personal: {sym} ₹{x['last']}")
            else:
                failures.append(f"{sym}: {err}")
                print(f"FAIL personal: {sym}: {err}")

    # Only a small first batch of the broader universe is fetched each run.
    # The dashboard's personal list is the priority; broader coverage can be
    # expanded later once the feed is proven stable.
    broad = [(s, n) for s, n in UNIVERSE.items() if s not in stocks][:20]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(fetch_one, item, 1) for item in broad]
        for f in as_completed(futures):
            sym, x, err = f.result()
            if x:
                stocks[sym] = x
                print(f"OK universe: {sym}")
            else:
                print(f"SKIP universe: {sym}: {err}")

    # Do not publish an empty snapshot. Require at least one personal stock.
    if not stocks:
        raise RuntimeError(
            "No stock data was retrieved. Existing data.json was NOT replaced. "
            "Check the Yahoo Finance endpoint/rate limit and rerun."
        )

    # If every personal stock failed, fail the workflow rather than showing false success.
    personal_ok = [s for s in WATCH if s in stocks]
    if not personal_ok:
        raise RuntimeError(
            "All five personal stocks failed: " + "; ".join(failures)
        )

    markets = {}
    for name, sym in [("NIFTY", "^NSEI"), ("SENSEX", "^BSESN")]:
        try:
            markets[name] = clean_index(get_index(sym))
        except Exception as e:
            print(f"SKIP index {name}: {e}")

    out = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance chart endpoint via GitHub Actions",
        "personalStocksUpdated": personal_ok,
        "stockFailures": failures,
        "stocks": stocks,
        "markets": markets,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    print(
        f"Published {len(stocks)} stocks; "
        f"personal stocks OK: {len(personal_ok)}/5; "
        f"indices: {len(markets)}."
    )

if __name__ == "__main__":
    main()
