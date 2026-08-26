import json, time, urllib.request, urllib.parse
from datetime import datetime, timezone

WATCH = {
    "ABB": "ABB India", "BDL": "Bharat Dynamics", "BPCL": "BPCL",
    "BEL": "Bharat Electronics", "CUPID": "Cupid"
}
UNIVERSE = {
"RELIANCE":"Reliance Industries","TCS":"Tata Consultancy Services","HDFCBANK":"HDFC Bank",
"ICICIBANK":"ICICI Bank","INFY":"Infosys","SBIN":"State Bank of India","BHARTIARTL":"Bharti Airtel",
"ITC":"ITC","LT":"Larsen & Toubro","AXISBANK":"Axis Bank","KOTAKBANK":"Kotak Mahindra Bank",
"M&M":"Mahindra & Mahindra","SUNPHARMA":"Sun Pharma","MARUTI":"Maruti Suzuki","HINDUNILVR":"Hindustan Unilever",
"TITAN":"Titan Company","BEL":"Bharat Electronics","BDL":"Bharat Dynamics","HAL":"Hindustan Aeronautics",
"ADANIENT":"Adani Enterprises","ADANIPORTS":"Adani Ports","NTPC":"NTPC","POWERGRID":"Power Grid",
"ONGC":"ONGC","COALINDIA":"Coal India","BPCL":"BPCL","TATASTEEL":"Tata Steel","JSWSTEEL":"JSW Steel",
"HINDALCO":"Hindalco","TRENT":"Trent","ETERNAL":"Eternal","INDIGO":"InterGlobe Aviation",
"BAJFINANCE":"Bajaj Finance","BAJAJFINSV":"Bajaj Finserv","WIPRO":"Wipro","TECHM":"Tech Mahindra",
"HCLTECH":"HCL Technologies","LTIM":"LTIMindtree","ASIANPAINT":"Asian Paints","ULTRACEMCO":"UltraTech Cement",
"TATAMOTORS":"Tata Motors","TATACONSUM":"Tata Consumer","NESTLEIND":"Nestle India","CIPLA":"Cipla",
"DRREDDY":"Dr Reddy's Laboratories","EICHERMOT":"Eicher Motors","HEROMOTOCO":"Hero MotoCorp",
"TVSMOTOR":"TVS Motor","INDUSINDBK":"IndusInd Bank","PNB":"Punjab National Bank","CANBK":"Canara Bank",
"IRFC":"IRFC","RVNL":"Rail Vikas Nigam","IREDA":"IREDA","NHPC":"NHPC","HUDCO":"HUDCO",
"SUZLON":"Suzlon Energy","YESBANK":"Yes Bank","IDEA":"Vodafone Idea","IOC":"Indian Oil",
"GAIL":"GAIL","BHEL":"BHEL","CUPID":"Cupid"
}
ALL = dict(UNIVERSE)
ALL.update(WATCH)

def get(sym, rng="10y"):
    q = urllib.parse.quote(sym + ".NS", safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval=1d&events=div%2Csplits"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def get_index(symbol):
    q=urllib.parse.quote(symbol,safe="")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=5d&interval=1d"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())

def clean(result):
    ts=result["timestamp"]; c=result["indicators"]["quote"][0].get("close",[])
    v=result["indicators"]["quote"][0].get("volume",[])
    pts=[]
    for t,close,vol in zip(ts,c,v):
        if close is not None: pts.append({"t":t,"c":round(close,4),"v":vol or 0})
    if len(pts)<2: raise ValueError("not enough prices")
    last=pts[-1]["c"]; prev=pts[-2]["c"]
    def old(days):
        target=time.time()-days*86400
        p=pts[0]
        for x in pts:
            if x["t"]<=target:p=x
            else:break
        return p["c"]
    def pct(base): return round((last/base-1)*100,2) if base else None
    year=pts[-252:]; high=max(x["c"] for x in year); low=min(x["c"] for x in year)
    vol=[x["v"] for x in pts[-21:-1] if x["v"]]
    avg=sum(vol)/len(vol) if vol else 0
    ratio=(pts[-1]["v"]/avg) if avg else 1
    today=pct(prev); m1=pct(old(30)); m3=pct(old(91))
    score=max(0,min(35,(today+3)*4))+max(0,min(25,(m1+5)*2))+max(0,min(20,m3+10))+max(0,min(15,(ratio-.8)*15))+max(0,min(5,(pct(high)+10)*.5))
    return {"last":last,"prev":prev,"today":today,"m1":m1,"m3":m3,"m6":pct(old(182)),
            "m9":pct(old(274)),"y1":pct(old(365)),"y5":pct(old(1826)),
            "high":high,"low":low,"volume":pts[-1]["v"],"score":round(score,1),
            "points":pts}

def main():
    stocks={}
    for sym,name in ALL.items():
        try:
            x=clean(get(sym))
            x["name"]=name
            stocks[sym]=x
        except Exception as e:
            print(f"SKIP {sym}: {e}")
    markets={}
    for name,sym in [("NIFTY","^NSEI"),("SENSEX","^BSESN")]:
        try:
            r=get_index(sym)["chart"]["result"][0]
            q=r["indicators"]["quote"][0]; c=[x for x in q.get("close",[]) if x is not None]
            if len(c)>=2: markets[name]={"last":c[-1],"today":round((c[-1]/c[-2]-1)*100,2)}
        except Exception as e: print(f"SKIP {name}: {e}")
    out={"updatedAt":datetime.now(timezone.utc).isoformat(),"source":"Yahoo Finance chart endpoint via GitHub Actions","stocks":stocks,"markets":markets}
    with open("data.json","w",encoding="utf-8") as f: json.dump(out,f,separators=(",",":"))
    print(f"Wrote {len(stocks)} stocks and {len(markets)} indices.")

if __name__=="__main__": main()
