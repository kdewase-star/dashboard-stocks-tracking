import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path("ipo.json")
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; KunalStockDashboard/1.0)"}


def load():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"version":"3.0","updatedAt":None,"ipos":[]}


def norm(s):
    return re.sub(r"[^a-z0-9]","",(s or "").lower())


def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=30)
    r.raise_for_status()
    return r.text


def parse_groww_subscription():
    """
    Best-effort parser. The updater never replaces good values with empty/null.
    If Groww changes HTML, the seeded snapshot is retained.
    """
    html=fetch("https://groww.in/ipo/subscription")
    text=re.sub(r"\s+"," ",html)
    out={}
    names=[
        "Annu Projects","Lumino Industries","Priority Jewels","ESDS Software Solution",
        "Sumax Engineering","Kwick Forensic","Paluck Technologies",
        "Complete Sports and Management","Skyways Air Services","ABH Healthcare",
        "Madhur Knit Crafts","Symbiotec Pharmalab","Hy-tech Engineers"
    ]
    for name in names:
        i=text.lower().find(name.lower())
        if i<0: continue
        chunk=text[i:i+1500]
        nums=re.findall(r"(\d+(?:\.\d+)?)x",chunk)
        if nums:
            out[norm(name)]={"subscriptionTotal":float(nums[-1])}
    return out


def status(item):
    today=datetime.now().date()
    def d(k):
        try:
            return datetime.fromisoformat(str(item.get(k))).date()
        except Exception:
            return None
    o,c,a,l=d("openDate"),d("closeDate"),d("allotmentDate"),d("listingDate")
    if l and today>=l:return "LISTED"
    if c and today>c:return "BIDDING ENDED"
    if o and c and o<=today<=c:return "LIVE"
    if o and today<o:return "UPCOMING"
    if a and today>=a:return "ALLOTMENT PENDING"
    return "STATUS UNCONFIRMED"


def main():
    data=load()
    old=data.get("ipos",[])
    try:
        fresh=parse_groww_subscription()
    except Exception as exc:
        print("IPO live refresh unavailable:",repr(exc))
        fresh={}

    for item in old:
        if not isinstance(item,dict): continue
        key=norm(item.get("name"))
        if key in fresh and fresh[key].get("subscriptionTotal") is not None:
            item["subscriptionTotal"]=fresh[key]["subscriptionTotal"]
        item["status"]=status(item)

    # Keep the seed snapshot; do not publish an empty scrape.
    data["updatedAt"]=datetime.now(timezone.utc).isoformat()
    data["gmpDisclaimer"]="GMP is unofficial and must not be treated as a guaranteed listing price or return."
    OUT.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    print("IPO records preserved:",len(data.get("ipos",[])))


if __name__=="__main__":
    main()
