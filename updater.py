import json, time, urllib.request, urllib.parse
from datetime import datetime, timezone

WATCH = {
    "ABB": "ABB India",
    "BDL": "Bharat Dynamics",
    "BPCL": "BPCL",
    "BEL": "Bharat Electronics",
    "CUPID": "Cupid",
}

UNIVERSE = {
    "RELIANCE":"Reliance Industries","TCS":"Tata Consultancy Services","HDFCBANK":"HDFC Bank",
    "ICICIBANK":"ICICI Bank","INFY":"Infosys","SBIN":"State Bank of India","BHARTIARTL":"Bharti Airtel",
    "ITC":"ITC","LT":"Larsen & Toubro","AXISBANK":"Axis Bank","KOTAKBANK":"Kotak Mahindra Bank",
    "M&M":"Mahindra & Mahindra","SUNPHARMA":"Sun Pharma","MARUTI":"Maruti Suzuki",
    "HINDUNILVR":"Hindustan Unilever","TITAN":"Titan Company","HAL":"Hindustan Aeronautics",
    "ADANIENT":"Adani Enterprises","ADANIPORTS":"Adani Ports","NTPC":"NTPC","POWERGRID":"Power Grid",
    "ONGC":"ONGC","COALINDIA":"Coal India","TATASTEEL":"Tata Steel","JSWSTEEL":"JSW Steel",
    "HINDALCO":"Hindalco","TRENT":"Trent","ETERNAL":"Eternal","INDIGO":"InterGlobe Aviation",
    "BAJFINANCE":"Bajaj Finance","BAJAJFINSV":"Bajaj Finserv","WIPRO":"Wipro","TECHM":"Tech Mahindra",
    "HCLTECH":"HCL Technologies","LTIM":"LTIMindtree","ASIANPAINT":"Asian Paints",
    "ULTRACEMCO":"UltraTech Cement","TATAMOTORS":"Tata Motors","TATACONSUM":"Tata Consumer",
    "NESTLEIND":"Nestle India","CIPLA":"Cipla","DRREDDY":"Dr Reddy's Laboratories",
    "EICHERMOT":"Eicher Motors","HEROMOTOCO":"Hero MotoCorp","TVSMOTOR":"TVS Motor",
    "INDUSINDBK":"IndusInd Bank","PNB":"Punjab National Bank","CANBK":"Canara Bank",
    "IRFC":"IRFC","RVNL":"Rail Vikas Nigam","IREDA":"IREDA","NHPC":"NHPC","HUDCO":"HUDCO",
    "SUZLON":"Suzlon Energy","YESBANK":"Yes Bank","IDEA":"Vodafone Idea","IOC":"Indian Oil",
    "GAIL":"GAIL","BHEL":"BHEL"
}
ALL = dict(UNIVERSE)
ALL.update(WATCH)

UA = "Mozilla/5.0 (compatible; KunalStockDashboard/5.3)"

def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(r.read().decode("utf-8"))

def batch_live(symbols):
    base = "http://65.0.104.9/stock/list?symbols=" + urllib.parse.quote(",".join(symbols), safe=",.-&") + "&res=num"
    return fetch_json(base, timeout=20)

def yahoo_chart(sym):
    q = urllib.parse.quote(sym + ".NS", safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=10y&interval=1d&events=div%2Csplits"
    return fetch_json(url, timeout=12)["chart"]["result"][0]

def pct(a,b):
    return round((a/b-1)*100,2) if b else None

def enrich_with_history(sym, live):
    try:
        r = yahoo_chart(sym)
        ts = r.get("timestamp",[])
        q = r.get("indicators",{}).get("quote",[{}])[0]
        closes = q.get("close",[])
        vols = q.get("volume",[])
        pts=[{"t":int(t),"c":round(float(c),4),"v":int(vols[i] or 0) if i<len(vols) else 0}
             for i,(t,c) in enumerate(zip(ts,closes)) if c is not None]
        if len(pts)<2:
            raise RuntimeError("not enough history")
        last=float(live.get("last_price") or pts[-1]["c"])
        prev=float(live.get("last_price") or pts[-2]["c"]) - float(live.get("change") or 0)
        def old(days):
            target=time.time()-days*86400
            x=pts[0]
            for p in pts:
                if p["t"]<=target:x=p
                else:break
            return x["c"]
        year=pts[-252:]
        high=max(x["c"] for x in year);low=min(x["c"] for x in year)
        m1=pct(last,old(30));m3=pct(last,old(91))
        score=max(0,min(100,(live.get("percent_change") or 0)*3+max(0,m1)*1.5+max(0,m3)*.5+10))
        return {
            "name": live.get("company_name") or WATCH.get(sym) or UNIVERSE.get(sym) or sym,
            "last": last, "prev": prev,
            "today": float(live.get("percent_change") or 0),
            "m1":m1,"m3":m3,"m6":pct(last,old(182)),"m9":pct(last,old(274)),
            "y1":pct(last,old(365)),"y5":pct(last,old(1826)),
            "high":high,"low":low,"volume":live.get("volume") or pts[-1]["v"],
            "score":round(score,1),"marketCap":live.get("market_cap"),
            "pe":live.get("pe_ratio"),"sector":live.get("sector"),
            "points":pts
        }
    except Exception as e:
        # Live data is still useful even if historical enrichment fails.
        return {
            "name": live.get("company_name") or WATCH.get(sym) or UNIVERSE.get(sym) or sym,
            "last":live.get("last_price"),"prev":None,
            "today":live.get("percent_change"),"m1":None,"m3":None,"m6":None,
            "m9":None,"y1":None,"y5":None,"high":None,"low":None,
            "volume":live.get("volume"),"score":None,
            "marketCap":live.get("market_cap"),"pe":live.get("pe_ratio"),
            "sector":live.get("sector"),"points":[],"historyError":str(e)
        }

def main():
    symbols=list(ALL.keys())
    live={}
    # Batch requests, 20 symbols at a time, to minimize rate-limit exposure.
    for i in range(0,len(symbols),20):
        batch=symbols[i:i+20]
        try:
            j=batch_live(batch)
            for item in j.get("stocks",[]):
                sym=item.get("symbol")
                if sym: live[sym]=item
            print(f"Batch {i//20+1}: received {len(j.get('stocks',[]))}/{len(batch)}")
        except Exception as e:
            print(f"Batch failed: {e}")
        time.sleep(1)

    stocks={}
    for sym,item in live.items():
        stocks[sym]=enrich_with_history(sym,item)

    personal_ok=[s for s in WATCH if s in stocks and stocks[s].get("last") is not None]
    if not personal_ok:
        raise RuntimeError(
            "The batch Indian-stock API returned no usable personal stocks. "
            "Existing data.json was NOT replaced."
        )

    # Preserve previous data if the batch source returns only a partial snapshot.
    try:
        with open("data.json","r",encoding="utf-8") as f:
            previous=json.load(f)
    except Exception:
        previous={}

    # Don't overwrite good historical data with a tiny partial response.
    if len(stocks) < 5 and previous.get("stocks"):
        for sym,old in previous["stocks"].items():
            if sym not in stocks:
                stocks[sym]=old

    out={
        "updatedAt":datetime.now(timezone.utc).isoformat(),
        "source":"Indian Stock Market API batch endpoint; historical enrichment via public chart endpoint",
        "personalStocksUpdated":personal_ok,
        "stocks":stocks,
        "markets":{}
    }
    # The batch endpoint is stock-focused; index values are optional.
    with open("data.json","w",encoding="utf-8") as f:
        json.dump(out,f,separators=(",",":"))
    print(f"Published {len(stocks)} stocks; personal stocks OK {len(personal_ok)}/5.")

if __name__=="__main__":
    main()
