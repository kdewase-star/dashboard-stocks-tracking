"""
Reliable IPO updater for Kunal's Stock Dashboard.

Goals:
- Discover actual IPO detail pages, not navigation/category pages.
- Keep LIVE IPOs first.
- Then BIDDING ENDED.
- Then UPCOMING.
- Remove LISTED/expired IPOs from active feed.
- Preserve the last good snapshot if scraping fails.
- Keep IPO fields separate:
    price, lot, minimum investment, subscription, GMP,
    open/close/allotment/listing dates.
- Never invent subscription/GMP when unavailable.
"""

import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


OUT = Path("ipo.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

DISCOVERY_URLS = [
    "https://groww.in/ipo",
    "https://groww.in/ipo/sme",
]

STATUS_ORDER = {
    "LIVE": 1,
    "BIDDING ENDED": 2,
    "UPCOMING": 3,
}


# ---------------------------------------------------------
# HTTP
# ---------------------------------------------------------

def get(url, timeout=30):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------
# TEXT HELPERS
# ---------------------------------------------------------

def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def number(value):
    if value is None:
        return None

    value = str(value)
    value = value.replace(",", "")
    value = value.replace("₹", "")
    value = value.replace("Rs.", "")
    value = value.replace("Rs", "")

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:
        return float(match.group(0))
    except Exception:
        return None


def integer(value):
    n = number(value)

    if n is None:
        return None

    return int(round(n))


def parse_date(value):
    if not value:
        return None

    value = clean(value)

    formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %b, %Y",
        "%d %B, %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt
            ).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


# ---------------------------------------------------------
# DATE EXTRACTION
# ---------------------------------------------------------

def extract_date(text, labels):
    text = clean(text)

    for label in labels:

        pattern = (
            re.escape(label)
            + r"\s*[:\-]?\s*"
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"(?:[a-z]*)\s*,?\s*\d{4})"
        )

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:
            parsed = parse_date(match.group(1))

            if parsed:
                return parsed

    return None


# ---------------------------------------------------------
# PRICE BAND
# ---------------------------------------------------------

def extract_price_band(text):

    patterns = [
        r"₹\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*₹?\s*([\d,]+(?:\.\d+)?)",
        r"price band\s*[:\-]?\s*₹?\s*([\d,]+)\s*[-–]\s*₹?\s*([\d,]+)",
        r"issue price\s*[:\-]?\s*₹?\s*([\d,]+)\s*[-–]\s*₹?\s*([\d,]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            low = number(match.group(1))
            high = number(match.group(2))

            if low is not None and high is not None:
                return low, high

    return None, None


# ---------------------------------------------------------
# LOT SIZE
# ---------------------------------------------------------

def extract_lot_size(text):

    patterns = [
        r"lot size\s*[:\-]?\s*([\d,]+)",
        r"minimum lot\s*[:\-]?\s*([\d,]+)",
        r"market lot\s*[:\-]?\s*([\d,]+)",
        r"lot\s*[:\-]?\s*([\d,]+)\s*shares",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            value = integer(
                match.group(1)
            )

            if value and value > 0:
                return value

    return None


# ---------------------------------------------------------
# MINIMUM INVESTMENT
# ---------------------------------------------------------

def extract_min_investment(text):

    patterns = [
        r"minimum investment\s*(?:is|of)?\s*₹\s*([\d,]+(?:\.\d+)?)",
        r"min(?:imum)? investment\s*[:\-]?\s*₹\s*([\d,]+(?:\.\d+)?)",
        r"application amount\s*[:\-]?\s*₹\s*([\d,]+(?:\.\d+)?)",
        r"investment amount\s*[:\-]?\s*₹\s*([\d,]+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            value = number(
                match.group(1)
            )

            if value and value > 0:
                return value

    return None


# ---------------------------------------------------------
# SUBSCRIPTION
# ---------------------------------------------------------

def extract_subscription(text):

    patterns = [
        r"Total\s*[:\-]?\s*([\d.]+)\s*x",
        r"Overall\s*[:\-]?\s*([\d.]+)\s*x",
        r"overall subscription\s*[:\-]?\s*([\d.]+)\s*x",
        r"subscription\s*[:\-]?\s*([\d.]+)\s*x",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            value = number(
                match.group(1)
            )

            if value is not None:
                return value

    return None


# ---------------------------------------------------------
# GMP
# ---------------------------------------------------------

def extract_gmp(text):

    patterns = [
        r"\bGMP\b\s*[:\-]?\s*₹?\s*([\d,.]+)",
        r"grey market premium\s*[:\-]?\s*₹?\s*([\d,.]+)",
        r"grey market\s*[:\-]?\s*₹?\s*([\d,.]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            value = number(
                match.group(1)
            )

            if value is not None:
                return value

    return None


# ---------------------------------------------------------
# URL VALIDATION
# ---------------------------------------------------------

EXCLUDED_SLUGS = {
    "ipo",
    "open",
    "closed",
    "upcoming",
    "mainboard",
    "sme",
    "allotment",
    "gmp",
    "reviews",
    "calendar",
    "subscription",
    "ipo-calendar",
    "ipo-news",
    "ipo-analysis",
}


def is_real_ipo_url(url):

    parsed = urlparse(url)

    if parsed.netloc.lower() != "groww.in":
        return False

    path = parsed.path.rstrip("/")

    if not path.startswith("/ipo/"):
        return False

    slug = path.split("/")[-1].lower()

    if not slug:
        return False

    if slug in EXCLUDED_SLUGS:
        return False

    # Exclude category paths.
    category_words = {
        "open",
        "closed",
        "upcoming",
        "mainboard",
        "sme",
        "all",
        "latest",
    }

    if slug in category_words:
        return False

    # Actual IPO pages normally have a descriptive slug.
    if len(slug) < 5:
        return False

    return True


# ---------------------------------------------------------
# DISCOVERY
# ---------------------------------------------------------

def discover_ipo_urls():

    discovered = set()

    for listing_url in DISCOVERY_URLS:

        try:

            html = get(
                listing_url
            )

            soup = BeautifulSoup(
                html,
                "html.parser"
            )

            for anchor in soup.find_all(
                "a",
                href=True
            ):

                href = urljoin(
                    "https://groww.in",
                    anchor["href"]
                )

                href = href.split("?")[0]
                href = href.rstrip("/")

                if is_real_ipo_url(href):
                    discovered.add(href)

        except Exception as exc:

            print(
                "Discovery failed:",
                listing_url,
                exc
            )

    urls = sorted(
        discovered
    )

    print(
        "Valid IPO detail URLs discovered:",
        len(urls)
    )

    for url in urls:
        print(" -", url)

    return urls


# ---------------------------------------------------------
# IPO STATUS
# ---------------------------------------------------------

def ipo_status(
    open_date,
    close_date,
    listing_date
):

    today = date.today()

    op = None
    cl = None
    li = None

    try:
        if open_date:
            op = datetime.strptime(
                open_date,
                "%Y-%m-%d"
            ).date()
    except Exception:
        pass

    try:
        if close_date:
            cl = datetime.strptime(
                close_date,
                "%Y-%m-%d"
            ).date()
    except Exception:
        pass

    try:
        if listing_date:
            li = datetime.strptime(
                listing_date,
                "%Y-%m-%d"
            ).date()
    except Exception:
        pass

    # Listing always wins.
    if li and today >= li:
        return "LISTED"

    # Live bidding.
    if op and cl:
        if op <= today <= cl:
            return "LIVE"

    # Upcoming.
    if op and today < op:
        return "UPCOMING"

    # Bid ended but listing not completed.
    if cl and today > cl:
        return "BIDDING ENDED"

    return "UPCOMING"


# ---------------------------------------------------------
# NAME
# ---------------------------------------------------------

def extract_name(soup, url):

    # H1 is usually better than title.
    h1 = soup.find("h1")

    if h1:

        value = clean(
            h1.get_text(" ", strip=True)
        )

        if value:
            value = re.sub(
                r"\s+IPO.*$",
                "",
                value,
                flags=re.I
            )

            return value.strip()

    if soup.title:

        value = clean(
            soup.title.get_text()
        )

        value = re.sub(
            r"\s+IPO.*$",
            "",
            value,
            flags=re.I
        )

        if value:
            return value.strip()

    slug = url.rstrip("/").split("/")[-1]

    slug = re.sub(
        r"-ipo$",
        "",
        slug,
        flags=re.I
    )

    return slug.replace(
        "-",
        " "
    ).title()


# ---------------------------------------------------------
# TYPE
# ---------------------------------------------------------

def detect_type(text, url):

    first_part = text[:12000].lower()

    if (
        "/ipo/sme" in url.lower()
        or " sme ipo" in first_part
        or "sme ipo" in first_part
    ):
        return "SME"

    return "Mainboard"


# ---------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------

def calculate_analysis(
    ipo_type,
    price_high,
    subscription,
    gmp,
    lot_size,
    min_investment,
):

    """
    Conservative scoring.

    IMPORTANT:
    This does not pretend to be an expert consensus score.
    It only calculates a transparent dashboard score from
    available measurable inputs.

    Missing data does NOT get converted into a fake positive score.
    """

    score = 5.0

    positives = []
    negatives = []

    # Subscription
    if subscription is not None:

        if subscription >= 20:
            score += 1.5
            positives.append(
                "Strong subscription demand"
            )

        elif subscription >= 5:
            score += 0.8
            positives.append(
                "Healthy subscription demand"
            )

        elif subscription < 1:
            score -= 1.0
            negatives.append(
                "Weak subscription demand"
            )

    # GMP
    if (
        gmp is not None
        and price_high
        and price_high > 0
    ):

        gmp_pct = (
            gmp / price_high
        ) * 100

        if gmp_pct >= 20:
            score += 1.2
            positives.append(
                "Strong GMP indication"
            )

        elif gmp_pct >= 8:
            score += 0.7
            positives.append(
                "Positive GMP indication"
            )

        elif gmp_pct < 0:
            score -= 0.8
            negatives.append(
                "Negative GMP indication"
            )

    # SME risk
    if ipo_type == "SME":

        score -= 0.5

        negatives.append(
            "SME IPO carries higher liquidity/risk"
        )

    score = max(
        0,
        min(10, score)
    )

    # Listing gains
    if gmp is not None and price_high:

        gmp_pct = (
            gmp / price_high
        ) * 100

        if gmp_pct >= 20:
            listing_gains = "Strong"
        elif gmp_pct >= 8:
            listing_gains = "Positive"
        elif gmp_pct >= 0:
            listing_gains = "Moderate"
        else:
            listing_gains = "Weak"

    elif subscription is not None:

        if subscription >= 10:
            listing_gains = "Positive"
        elif subscription >= 3:
            listing_gains = "Moderate"
        else:
            listing_gains = "Weak"

    else:
        listing_gains = "Insufficient data"

    # Long term
    if subscription is not None:

        if subscription >= 10:
            long_term = "Potentially Positive"
        elif subscription >= 3:
            long_term = "Neutral"
        else:
            long_term = "Caution"

    else:
        long_term = "Insufficient data"

    # Risk
    if ipo_type == "SME":
        risk = "High"
    elif score >= 7:
        risk = "Low–Medium"
    else:
        risk = "Medium"

    return {
        "score": round(score, 1),
        "listingGains": listing_gains,
        "longTerm": long_term,
        "risk": risk,
        "positives": positives,
        "negatives": negatives,
    }


# ---------------------------------------------------------
# PARSE DETAIL PAGE
# ---------------------------------------------------------

def parse_ipo(url):

    html = get(url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = clean(
        soup.get_text(
            " ",
            strip=True
        )
    )

    name = extract_name(
        soup,
        url
    )

    ipo_type = detect_type(
        text,
        url
    )

    price_low, price_high = (
        extract_price_band(text)
    )

    lot_size = extract_lot_size(
        text
    )

    published_minimum = (
        extract_min_investment(text)
    )

    subscription = (
        extract_subscription(text)
    )

    gmp = extract_gmp(
        text
    )

    open_date = extract_date(
        text,
        [
            "IPO open date",
            "Open date",
            "Issue opens",
        ]
    )

    close_date = extract_date(
        text,
        [
            "IPO close date",
            "Close date",
            "Issue closes",
        ]
    )

    allotment_date = extract_date(
        text,
        [
            "Allotment date",
            "Basis of allotment",
        ]
    )

    listing_date = extract_date(
        text,
        [
            "Tentative listing date",
            "Listing date",
            "IPO listing date",
        ]
    )

    status = ipo_status(
        open_date,
        close_date,
        listing_date
    )

    # -----------------------------------------------------
    # Minimum investment calculation
    # -----------------------------------------------------

    calculated_minimum = None

    if (
        price_high is not None
        and lot_size is not None
    ):
        calculated_minimum = (
            price_high * lot_size
        )

    # Prefer published source amount when it exists.
    minimum_investment = (
        published_minimum
        if published_minimum
        else calculated_minimum
    )

    # -----------------------------------------------------
    # Analysis
    # -----------------------------------------------------

    analysis = calculate_analysis(
        ipo_type=ipo_type,
        price_high=price_high,
        subscription=subscription,
        gmp=gmp,
        lot_size=lot_size,
        min_investment=minimum_investment,
    )

    return {
        "name": name,
        "url": url,
        "type": ipo_type,

        "priceLow": price_low,
        "priceHigh": price_high,

        "lotSize": lot_size,

        "minInvestment": (
            minimum_investment
        ),

        "minInvestmentPublished": (
            published_minimum
        ),

        "openDate": open_date,
        "closeDate": close_date,
        "allotmentDate": allotment_date,
        "listingDate": listing_date,

        "subscription": subscription,
        "gmp": gmp,

        "status": status,

        "analysis": analysis,

        "source": (
            "Groww IPO detail page"
        ),

        "lastUpdated": (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
    }


# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

def valid_ipo(record):

    if not record.get("name"):
        return False

    if not record.get("url"):
        return False

    # Do not allow category pages.
    if not is_real_ipo_url(
        record["url"]
    ):
        return False

    # Must have at least one meaningful IPO field.
    meaningful = [
        record.get("priceHigh"),
        record.get("lotSize"),
        record.get("openDate"),
        record.get("closeDate"),
        record.get("listingDate"),
        record.get("subscription"),
    ]

    return any(
        value is not None
        for value in meaningful
    )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("IPO DATA UPDATE")
    print("=" * 60)

    urls = discover_ipo_urls()

    if not urls:
        print(
            "ERROR: No IPO detail URLs discovered."
        )

        if OUT.exists():
            print(
                "Keeping previous ipo.json"
            )
            return

        raise RuntimeError(
            "No IPO URLs discovered"
        )

    records = []

    for index, url in enumerate(
        urls,
        start=1
    ):

        try:

            print(
                f"[{index}/{len(urls)}] "
                f"Fetching {url}"
            )

            record = parse_ipo(
                url
            )

            if not valid_ipo(
                record
            ):
                print(
                    "  SKIPPED: not a valid IPO record"
                )
                continue

            # Listed IPOs are intentionally
            # excluded from the active dashboard.
            if record["status"] == "LISTED":

                print(
                    "  LISTED -> excluded"
                )

                continue

            records.append(
                record
            )

            print(
                "  OK:",
                record["name"],
                "|",
                record["status"],
                "|",
                record["minInvestment"]
            )

        except Exception as exc:

            print(
                "  FAILED:",
                url,
                exc
            )

        time.sleep(0.4)

    # -----------------------------------------------------
    # SAFETY
    # -----------------------------------------------------

    if not records:

        print(
            "ERROR: Zero valid IPO records."
        )

        if OUT.exists():

            print(
                "Preserving existing ipo.json"
            )

            return

        raise RuntimeError(
            "IPO updater produced zero records"
        )

    # -----------------------------------------------------
    # DEDUPLICATE
    # -----------------------------------------------------

    unique = {}

    for record in records:

        key = (
            record["url"]
            .lower()
            .rstrip("/")
        )

        unique[key] = record

    records = list(
        unique.values()
    )

    # -----------------------------------------------------
    # SORT
    #
    # LIVE
    # BIDDING ENDED
    # UPCOMING
    # -----------------------------------------------------

    records.sort(
        key=lambda item: (
            STATUS_ORDER.get(
                item.get("status"),
                99
            ),

            item.get(
                "openDate"
            ) or "9999-12-31",

            item.get(
                "name",
                ""
            ).lower()
        )
    )

    payload = {
        "updatedAt": (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),

        "source": (
            "Groww IPO detail pages"
        ),

        "count": len(records),

        "ipos": records,
    }

    # -----------------------------------------------------
    # WRITE ATOMICALLY
    # -----------------------------------------------------

    temp = OUT.with_suffix(
        ".tmp"
    )

    temp.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    temp.replace(
        OUT
    )

    print()
    print("=" * 60)
    print(
        "SUCCESS:",
        len(records),
        "active IPOs written"
    )
    print("=" * 60)

    for record in records:

        print(
            record["status"],
            "|",
            record["name"]
        )


if __name__ == "__main__":
    main()