import json
from datetime import datetime, date

OUTPUT_FILE = "ipo.json"

# IMPORTANT:
# Keep raw IPO facts separate from analysis.
# retail_min_lots is the minimum number of lots required for the
# retail application. Do NOT assume it is always 1.

IPOS = [
    {
        "name": "Paluck Technologies",
        "symbol": "PALUCK",
        "type": "SME",

        "priceLow": 46,
        "priceHigh": 48,
        "lotSize": 3000,
        "retailMinLots": 2,

        "openDate": "2026-08-28",
        "closeDate": "2026-09-01",
        "allotmentDate": "2026-09-02",
        "listingDate": "2026-09-04",

        "subscription": None,
        "gmp": None,

        "analysis": {
            "score": None,
            "listingGains": "Pending",
            "longTerm": "Pending",
            "risk": "High",
            "positives": [],
            "negatives": []
        }
    }
]

def calculate(ipo):
    shares = ipo["lotSize"] * ipo["retailMinLots"]
    ipo["retailMinShares"] = shares
    ipo["minInvestmentLow"] = ipo["priceLow"] * shares
    ipo["minInvestmentHigh"] = ipo["priceHigh"] * shares
    ipo["minInvestment"] = (
        f"₹{ipo['minInvestmentLow']/100000:.2f}L - "
        f"₹{ipo['minInvestmentHigh']/100000:.2f}L"
    )

def get_status(ipo):
    today = date.today()
    op = datetime.strptime(ipo["openDate"], "%Y-%m-%d").date()
    cl = datetime.strptime(ipo["closeDate"], "%Y-%m-%d").date()
    li = datetime.strptime(ipo["listingDate"], "%Y-%m-%d").date()

    if today < op:
        return "UPCOMING"
    if op <= today <= cl:
        return "LIVE"
    if cl < today < li:
        return "BIDDING ENDED"
    return "LISTED"

for ipo in IPOS:
    calculate(ipo)
    ipo["status"] = get_status(ipo)
    ipo["lastUpdated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

order = {"LIVE": 1, "BIDDING ENDED": 2, "UPCOMING": 3, "LISTED": 4}
IPOS.sort(key=lambda x: (order.get(x["status"], 99), x["openDate"]))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump({
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ipos": IPOS
    }, f, indent=2, ensure_ascii=False)

print(f"Wrote {len(IPOS)} IPO records to {OUTPUT_FILE}")
