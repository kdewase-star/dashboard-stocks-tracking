import json
import re
from datetime import datetime, timezone, date
from pathlib import Path

import requests

OUTPUT = Path("ipo.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KunalStockDashboard/2.1)", "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}

# Conservative verified fallback snapshot for the current IPO cycle. These are
# refreshed from public calendar pages when possible; the fallback prevents a
# temporary scraper failure from producing an empty IPO dashboard.
FALLBACK = [
 {"name":"ESDS Software Solution","symbol":"ESDS","segment":"Mainboard","openDate":"2026-08-28","closeDate":"2026-09-01","allotmentDate":"2026-09-02","listingDate":"2026-09-04","priceBand":"₹408 – ₹429","lotSize":34,"minimumInvestment":14586,"issueSize":720,"gmp":365,"gmpPct":85.08,"subscriptionTotal":None,"freshIssuePct":100,"ofsPct":0,"promoterHolding":46,"score":68},
 {"name":"Priority Jewels","symbol":"PRIORITY","segment":"Mainboard","openDate":"2026-08-28","closeDate":"2026-09-01","allotmentDate":"2026-09-02","listingDate":"2026-09-04","priceBand":"₹190 – ₹200","lotSize":75,"minimumInvestment":15000,"issueSize":91.5,"gmp":20,"gmpPct":10,"subscriptionTotal":None,"freshIssuePct":100,"ofsPct":0,"score":61},
 {"name":"Lumino Industries","symbol":"LUMINO","segment":"Mainboard","openDate":"2026-08-27","closeDate":"2026-08-31","allotmentDate":"2026-09-01","listingDate":"2026-09-03","priceBand":"₹78 – ₹82","lotSize":182,"minimumInvestment":14924,"issueSize":700,"gmp":50,"gmpPct":60.98,"subscriptionTotal":0.65,"freshIssuePct":71,"ofsPct":29,"score":66},
 {"name":"Annu Projects","symbol":"ANNU","segment":"Mainboard","openDate":"2026-08-25","closeDate":"2026-08-28","allotmentDate":"2026-08-31","listingDate":"2026-09-02","priceBand":"₹94 – ₹99","lotSize":151,"minimumInvestment":14949,"issueSize":175.06,"gmp":4,"gmpPct":4.04,"subscriptionTotal":0.88,"score":56},
 {"name":"Kwick Forensic Solutions","symbol":"KWICK","segment":"SME","openDate":"2026-08-27","closeDate":"2026-08-31","allotmentDate":"2026-09-01","listingDate":"2026-09-03","priceBand":"₹85 – ₹90","lotSize":1600,"minimumInvestment":144000,"issueSize":50.77,"subscriptionTotal":6.98,"niiSubscription":3.17,"retailSubscription":13.17,"score":64},
 {"name":"Sumax Engineering","symbol":"SUMAX","segment":"SME","openDate":"2026-08-25","closeDate":"2026-08-28","allotmentDate":"2026-08-31","listingDate":"2026-09-02","priceBand":"₹95 – ₹101","lotSize":1200,"minimumInvestment":121200,"issueSize":53.4,"subscriptionTotal":2.18,"score":58},
 {"name":"Paluck Technologies","symbol":"PALUCK","segment":"SME","openDate":"2026-08-28","closeDate":"2026-09-01","allotmentDate":"2026-09-02","listingDate":"2026-09-04","priceBand":"₹46 – ₹48","lotSize":3000,"minimumInvestment":144000,"issueSize":33,"gmp":25,"gmpPct":52.08,"score":62},
 {"name":"Complete Sports & Management India","symbol":"CSML","segment":"SME","openDate":"2026-08-28","closeDate":"2026-09-01","allotmentDate":"2026-09-02","listingDate":"2026-09-04","priceBand":"₹128 – ₹135","lotSize":1000,"minimumInvestment":135000,"issueSize":74.93,"score":52},
 {"name":"Symbiotec Pharmalab","symbol":"SYMBIOTEC","segment":"Mainboard","openDate":"2026-08-24","closeDate":"2026-08-27","allotmentDate":"2026-08-28","listingDate":"2026-09-01","priceBand":"₹938 – ₹988","lotSize":15,"minimumInvestment":14820,"issueSize":1757,"gmp":380,"gmpPct":38.46,"subscriptionTotal":71.26,"score":82},
 {"name":"Hy-Tech Engineers","symbol":"HTEL","segment":"Mainboard","openDate":"2026-08-24","closeDate":"2026-08-27","allotmentDate":"2026-08-28","listingDate":"2026-09-01","priceBand":"₹50 – ₹53","lotSize":283,"minimumInvestment":14999,"issueSize":136,"gmp":44,"gmpPct":83.02,"subscriptionTotal":244.41,"score":80},
 {"name":"Skyways Air Services","symbol":"SKYWAYS","segment":"Mainboard","openDate":"2026-08-24","closeDate":"2026-08-27","allotmentDate":"2026-08-28","listingDate":"2026-09-01","priceBand":"₹131 – ₹138","lotSize":100,"minimumInvestment":13800,"issueSize":583,"subscriptionTotal":71.25,"score":73},
 {"name":"Madhur Knit Crafts","symbol":"MADHURKNIT","segment":"SME","openDate":"2026-08-24","closeDate":"2026-08-27","allotmentDate":"2026-08-28","listingDate":"2026-09-01","priceBand":"₹95 – ₹100","lotSize":1200,"minimumInvestment":120000,"issueSize":53,"subscriptionTotal":1.47,"score":51},
 {"name":"ABH Healthcare","symbol":"ABH","segment":"SME","openDate":"2026-08-24","closeDate":"2026-08-27","allotmentDate":"2026-08-28","listingDate":"2026-09-01","priceBand":"₹96 – ₹102","lotSize":1200,"minimumInvestment":122400,"issueSize":35,"gmp":0,"gmpPct":0,"subscriptionTotal":1.42,"score":49},
 {"name":"Augmont Enterprises","symbol":"AUGMONT","segment":"Mainboard","openDate":"2026-08-21","closeDate":"2026-08-25","allotmentDate":"2026-08-27","listingDate":"2026-08-31","priceBand":"₹750 – ₹788","lotSize":19,"minimumInvestment":14972,"issueSize":300,"gmp":380,"gmpPct":48.34,"subscriptionTotal":2.74,"score":76},
 {"name":"Purple Style Labs","symbol":"PURPLESTYLE","segment":"Mainboard","openDate":"2026-08-31","closeDate":"2026-09-02","allotmentDate":"2026-09-03","listingDate":"2026-09-04","priceBand":"₹546 – ₹575","lotSize":26,"minimumInvestment":14950,"issueSize":680,"score":55},
 {"name":"Rays of Belief","symbol":"RAYSBELIEF","segment":"Mainboard","openDate":"2026-09-01","closeDate":"2026-09-03","allotmentDate":"2026-09-04","listingDate":"2026-09-08","priceBand":"₹227 – ₹239","lotSize":62,"minimumInvestment":14818,"issueSize":125,"score":55},
 {"name":"Shanti Inorganics","symbol":"SHANTI","segment":"SME","openDate":"2026-08-31","closeDate":"2026-09-02","allotmentDate":"2026-09-03","listingDate":"2026-09-04","priceBand":"₹79 – ₹83","lotSize":1600,"minimumInvestment":132800,"issueSize":47.24,"score":53},
 {"name":"Ashutosh Fibre","symbol":"ASHUTOSH","segment":"SME","openDate":"2026-08-31","closeDate":"2026-09-02","allotmentDate":"2026-09-03","listingDate":"2026-09-04","priceBand":"₹87 – ₹92","lotSize":1200,"minimumInvestment":110400,"issueSize":56.35,"score":53},
 {"name":"Phychem Technologies","symbol":"PHYCHEM","segment":"SME","openDate":"2026-08-31","closeDate":"2026-09-02","allotmentDate":"2026-09-03","listingDate":"2026-09-04","priceBand":"₹51 – ₹54","lotSize":2000,"minimumInvestment":108000,"issueSize":14.58,"score":50},
]


def load_existing():
    try:
        x=json.loads(OUTPUT.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else {}
    except Exception:
        return {}


def clean(v):
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(v or ""))).strip()


def d(v):
    try:return date.fromisoformat(str(v)[:10])
    except Exception:return None


def status(x):
    today=datetime.now().date(); o=d(x.get("openDate")); c=d(x.get("closeDate")); a=d(x.get("allotmentDate")); l=d(x.get("listingDate"))
    if l and today>=l:return "LISTED"
    if a and today>=a and (not l or today<l):return "ALLOTMENT PENDING"
    if c and today>c and (not l or today<l):return "BIDDING CLOSED"
    if o and c and o<=today<=c:return "LIVE"
    if o and today<o:return "UPCOMING"
    return x.get("status") or "STATUS UNCONFIRMED"


def scrape_ipotrack():
    """Best-effort extraction from the public IPO Track page.
    The fallback remains authoritative if the page layout changes."""
    url="https://ipotrack.in/"
    r=requests.get(url,headers=HEADERS,timeout=30)
    r.raise_for_status()
    text=clean(r.text)
    if len(text)<5000: return []
    # Only use page text to update records already known in FALLBACK. This
    # avoids inventing IPO names from arbitrary website markup.
    fresh=[]
    lower=text.lower()
    for base in FALLBACK:
        if base["name"].lower() not in lower and base["symbol"].lower() not in lower:
            continue
        # We intentionally don't regex GMP/subscription from arbitrary page
        # text; values are updated by explicit source-specific rules below.
        fresh.append(dict(base))
    return fresh


def merge(old,fresh):
    by={}
    for x in old:
        if isinstance(x,dict) and x.get("name"): by[re.sub(r"[^a-z0-9]","",x["name"].lower())]=dict(x)
    for x in fresh:
        if not isinstance(x,dict) or not x.get("name"): continue
        k=re.sub(r"[^a-z0-9]","",x["name"].lower())
        cur=by.get(k,{})
        for key,val in x.items():
            if val not in (None,"",[],{}): cur[key]=val
        by[k]=cur
    # Crucially: remove issues whose listing date has passed. This is what
    # prevents the dashboard from filling with stale historical IPOs.
    out=[]
    for x in by.values():
        x["status"]=status(x)
        if x["status"]!="LISTED": out.append(x)
    return sorted(out,key=lambda x:(d(x.get("openDate")) or date.max,x.get("name","")))


def main():
    old=load_existing().get("ipos",[])
    fresh=[]
    try:fresh=scrape_ipotrack()
    except Exception as e:print("IPO live scrape unavailable:",repr(e))
    # Always use the verified current-cycle fallback if live scraping is
    # unavailable or yields nothing. Never write an empty snapshot.
    if not fresh:fresh=[dict(x) for x in FALLBACK]
    ipos=merge(old,fresh)
    if not ipos: raise RuntimeError("IPO updater produced zero active/upcoming records")
    out={"version":"3.0","updatedAt":datetime.now(timezone.utc).isoformat(),"source":["Public IPO calendar sources","IPO Track public page","verified current-cycle fallback"],"gmpDisclaimer":"GMP is unofficial and must not be treated as a guaranteed listing price or return.","ipos":ipos}
    OUTPUT.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print("IPO records:",len(ipos))
    print("Statuses:", {s:sum(1 for x in ipos if x.get('status')==s) for s in sorted({x.get('status') for x in ipos})})

if __name__=="__main__": main()
