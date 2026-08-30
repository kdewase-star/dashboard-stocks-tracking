"""
IPO updater for dashboard-stocks-tracking.

Designed to preserve the dashboard's multi-IPO behaviour instead of
hard-coding a single IPO. It discovers current/open/upcoming IPOs from
Groww's IPO listing pages, then enriches each issue from its detail page.

Key fixes:
- SME minimum application uses the published minimum application amount
  / minimum lot count, rather than blindly assuming one lot.
- Listing Gains, Long Term and Risk are separate analysis fields.
- LIVE -> BIDDING ENDED -> UPCOMING -> LISTED ordering.
- Listed/expired IPOs are excluded from the active IPO feed.
- If a source temporarily fails, the last non-empty ipo.json is retained.
"""

import json
import re
import time
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT = Path("ipo.json")
GROWW_LIST = "https://groww.in/ipo"
GROWW_SME = "https://groww.in/ipo/sme"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139 Safari/537.36"
    )
}

STATUS_ORDER = {
    "LIVE": 1,
    "BIDDING ENDED": 2,
    "UPCOMING": 3,
    "LISTED": 4,
}


def get(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("₹", "").replace("Rs.", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def date_iso(s):
    if not s:
        return None
    s = clean(s)
    for fmt in ("%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def extract_date_after(text, labels):
    text = clean(text)
    for label in labels:
        m = re.search(
            re.escape(label) +
            r"\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
            text, re.I
        )
        if m:
            return date_iso(m.group(1))
    return None


def extract_band(text):
    m = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*₹?\s*([\d,]+(?:\.\d+)?)",
        text
    )
    if not m:
        return None, None
    return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))


def extract_lot(text):
    patterns = [
        r"Lot size\s*[:\-]?\s*([\d,]+)",
        r"Minimum lot\s*[:\-]?\s*([\d,]+)",
        r"minimum market lot is\s*([\d,]+)\s*shares",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def extract_min_investment(text):
    patterns = [
        r"₹\s*([\d,]+(?:\.\d+)?)\s*/\s*[\d,]+\s*shares\s*Minimum investment",
        r"₹\s*([\d,]+(?:\.\d+)?)\s*Minimum investment",
        r"minimum investment\s*(?:is|of)?\s*₹\s*([\d,]+(?:\.\d+)?)",
        r"application amount\s*₹\s*([\d,]+(?:\.\d+)?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def extract_subscription(text):
    # Prefer "Total" subscription on Groww pages.
    patterns = [
        r"Total\s+([\d.]+)x",
        r"Total\s+([\d.]+)\s*x",
        r"overall subscription\s*[:\-]?\s*([\d.]+)x",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return float(m.group(1))
    return None


def extract_gmp(text):
    patterns = [
        r"GMP\s*(?:is|at|:)?\s*₹\s*([\d.]+)",
        r"grey market premium\s*(?:is|at|:)?\s*₹\s*([\d.]+)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return float(m.group(1))
    return None


def extract_links(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        href = urljoin("https://groww.in", a["href"])
        label = clean(a.get_text(" ", strip=True))
        if "/ipo/" in href and label:
            out[href] = label
    return out


def discover():
    links = {}
    for url in (GROWW_LIST, GROWW_SME):
        try:
            links.update(extract_links(get(url)))
        except Exception as e:
            print("Discovery failed:", url, e)

    return list(links.keys())


def status_for(open_date, close_date, listing_date):
    today = date.today()

    if open_date:
        op = datetime.strptime(open_date, "%Y-%m-%d").date()
    else:
        op = None

    if close_date:
        cl = datetime.strptime(close_date, "%Y-%m-%d").date()
    else:
        cl = None

    if listing_date:
        li = datetime.strptime(listing_date, "%Y-%m-%d").date()
    else:
        li = None

    if op and today < op:
        return "UPCOMING"
    if op and cl and op <= today <= cl:
        return "LIVE"
    if cl and (not li or today < li) and today > cl:
        return "BIDDING ENDED"
    if li and today >= li:
        return "LISTED"
    return "UPCOMING"


def parse_detail(url):
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    title = clean(soup.title.get_text()) if soup.title else ""
    name = re.sub(r"\s+IPO.*$", "", title, flags=re.I).strip()
    if not name:
        name = url.rstrip("/").split("/")[-1].replace("-", " ").title()

    low, high = extract_band(text)
    lot = extract_lot(text)
    min_inv = extract_min_investment(text)
    sub = extract_subscription(text)
    gmp = extract_gmp(text)

    open_date = extract_date_after(text, ["IPO open date", "Open date"])
    close_date = extract_date_after(text, ["IPO close date", "Close date"])
    allotment = extract_date_after(text, ["Allotment date"])
    listing = extract_date_after(text, ["Tentative listing date", "Listing date", "IPO listing date"])

    # Determine retail minimum lots from the published application amount
    # whenever possible. This is the critical SME fix.
    retail_min_lots = None
    retail_shares = None

    if lot and min_inv and high:
        retail_min_lots = max(1, round(min_inv / (high * lot)))
        retail_shares = lot * retail_min_lots

    # If the page explicitly states "2 lots", use it.
    m = re.search(r"Retail Minimum\s+(\d+)\s+[\d,]+\s+Shares", text, re.I)
    if m:
        retail_min_lots = int(m.group(1))
        if lot:
            retail_shares = lot * retail_min_lots

    # Calculate the range, but retain the published amount as the
    # authoritative minimum when the source gives it explicitly.
    calc_low = calc_high = None
    if low and high and lot and retail_min_lots:
        shares = lot * retail_min_lots
        calc_low = low * shares
        calc_high = high * shares

    if min_inv:
        # Keep source-published minimum at the upper-band/cut-off level.
        # The dashboard can show both low/high when available.
        pass

    if calc_low and calc_high:
        min_display = f"₹{calc_low/100000:.2f}L - ₹{calc_high/100000:.2f}L"
    elif min_inv:
        min_display = f"₹{min_inv/100000:.2f}L"
    else:
        min_display = None

    status = status_for(open_date, close_date, listing)

    # Conservative analytical mapping. Do not mix fields.
    # Score is intentionally not invented when source data is insufficient.
    analysis = {
        "score": None,
        "listingGains": "Pending",
        "longTerm": "Pending",
        "risk": "High" if "SME" in text[:5000] else "Medium",
        "positives": [],
        "negatives": [],
    }

    # Extract explicit source review language where available.
    review = ""
    m = re.search(r"IPOWatch View\s+(.*?)(?:Apply|$)", text, re.I)
    if m:
        review = clean(m.group(1))

    if "long term" in review.lower():
        analysis["longTerm"] = "Positive"
    elif "moderate" in review.lower():
        analysis["longTerm"] = "Moderate"

    return {
        "name": name,
        "url": url,
        "type": "SME" if "/ipo/sme" in url.lower() or "SME" in text[:5000] else "Mainboard",
        "priceLow": low,
        "priceHigh": high,
        "lotSize": lot,
        "retailMinLots": retail_min_lots,
        "retailMinShares": retail_shares,
        "minInvestmentPublished": min_inv,
        "minInvestmentLow": calc_low,
        "minInvestmentHigh": calc_high,
        "minInvestment": min_display,
        "openDate": open_date,
        "closeDate": close_date,
        "allotmentDate": allotment,
        "listingDate": listing,
        "subscription": sub,
        "gmp": gmp,
        "status": status,
        "analysis": analysis,
        "source": "Groww IPO detail page; review cross-check recommended",
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    urls = discover()
    print("Discovered IPO pages:", len(urls))

    records = []
    for url in urls:
        try:
            item = parse_detail(url)

            # Do not keep already-listed/expired issues in the active feed.
            if item["status"] != "LISTED":
                records.append(item)

            print(item["name"], item["status"], item["minInvestment"])
            time.sleep(0.25)

        except Exception as e:
            print("Failed:", url, e)

    # Safety: never replace a healthy existing dataset with an empty one.
    if not records:
        if OUT.exists() and OUT.stat().st_size > 20:
            print("No IPO records fetched; preserving existing ipo.json")
            return
        raise RuntimeError("IPO discovery returned zero records")

    records.sort(
        key=lambda x: (
            STATUS_ORDER.get(x.get("status"), 99),
            x.get("openDate") or "9999-12-31"
        )
    )

    payload = {
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Groww IPO discovery + detail pages",
        "ipos": records
    }

    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Wrote", len(records), "active/upcoming IPOs")


if __name__ == "__main__":
    main()
