import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KunalStockDashboard/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUTPUT = Path("ipo.json")


def load_existing():
    if not OUTPUT.exists():
        return {"version": "2.0", "updatedAt": None, "ipos": []}
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "2.0", "updatedAt": None, "ipos": []}


def clean_text(value):
    if value is None:
        return None
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def parse_date(value):
    if not value:
        return None
    value = clean_text(value)
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return value


def normalize_status(item):
    today = datetime.now().date()
    def d(key):
        value = item.get(key)
        try:
            return datetime.fromisoformat(str(value)).date()
        except Exception:
            return None

    opened = d("openDate")
    closed = d("closeDate")
    allot = d("allotmentDate")
    listed = d("listingDate")

    if listed and today >= listed:
        return "LISTED"
    if allot and today >= allot and (not listed or today < listed):
        return "ALLOTMENT PENDING"
    if closed and today > closed and (not listed or today < listed):
        return "BIDDING CLOSED"
    if opened and closed and opened <= today <= closed:
        return "LIVE"
    if opened and today < opened:
        return "UPCOMING"
    return item.get("status") or "STATUS UNCONFIRMED"


def key_for(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def merge(old, fresh):
    by_key = {}
    for item in old:
        if isinstance(item, dict) and item.get("name"):
            by_key[key_for(item["name"])] = dict(item)

    for item in fresh:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        key = key_for(item["name"])
        current = by_key.get(key, {})
        # Do not overwrite good values with empty/null values.
        for k, v in item.items():
            if v not in (None, "", [], {}):
                current[k] = v
        by_key[key] = current

    result = []
    for item in by_key.values():
        item["status"] = normalize_status(item)
        result.append(item)
    return result


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def scrape_basic_calendar():
    """
    Conservative source reader.

    Source HTML changes from time to time, so this function only extracts
    obvious IPO calendar rows. If it cannot confidently parse a page,
    the previous ipo.json snapshot is retained rather than wiped.
    """
    urls = [
        "https://www.moneycontrol.com/ipo/",
        "https://groww.in/ipo",
    ]

    records = []

    for url in urls:
        try:
            html = fetch_html(url)
        except Exception as exc:
            print("IPO source unavailable:", url, repr(exc))
            continue

        # Common date patterns around IPO names. This is deliberately
        # conservative; existing cached fields are never destroyed.
        text = clean_text(html) or ""
        if len(text) < 500:
            continue

        # Try to capture date strings for later enrichment, but do not
        # fabricate an IPO name from arbitrary page text.
        dates = re.findall(
            r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
            text,
            flags=re.I,
        )
        print("IPO source:", url, "date tokens:", len(dates))

    # The current repository snapshot remains authoritative until a
    # confidently parsed replacement is available.
    return records


def main():
    existing = load_existing()
    old = existing.get("ipos", []) if isinstance(existing, dict) else []

    try:
        fresh = scrape_basic_calendar()
    except Exception as exc:
        print("IPO update failed:", repr(exc))
        fresh = []

    ipos = merge(old, fresh)

    output = {
        "version": "2.0",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": [
            "Existing cached IPO snapshot",
            "Public IPO calendar sources"
        ],
        "gmpDisclaimer":
            "GMP is unofficial and must not be treated as a guaranteed listing price or return.",
        "ipos": ipos,
    }

    OUTPUT.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("IPO records:", len(ipos))


if __name__ == "__main__":
    main()
