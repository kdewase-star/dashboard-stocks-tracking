"""
IPO updater for dashboard-stocks-tracking
=========================================

This version fixes the main problem in the previous updater:

1. It does NOT scrape Groww navigation links as IPOs.
2. It uses Moneycontrol IPO listing pages for the IPO universe and schedule.
3. It uses IPO Watch subscription data as a cross-check when available.
4. It calculates status from actual open/close/allotment/listing dates.
5. It supports:
      LIVE
      ALLOTMENT PENDING
      BIDDING ENDED
      UPCOMING
      LISTED
6. Listed IPOs are removed from the active dashboard.
7. It keeps minimum investment separate from price/lot data.
8. It keeps Listing Gains / Long Term / Risk separate.
9. It never replaces a good ipo.json with an empty result.

Install:
    pip install requests beautifulsoup4

Run:
    python ipo_updater.py
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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# Moneycontrol gives us the actual IPO universe and schedule.
DISCOVERY_URLS = [
    "https://www.moneycontrol.com/ipo/open-ipos/",
    "https://www.moneycontrol.com/ipo/upcoming-ipos/",
    "https://www.moneycontrol.com/ipo/closed-ipos/",
    "https://www.moneycontrol.com/ipo/mainline/",
    "https://www.moneycontrol.com/ipo/sme/",
]

# IPO Watch is useful as a second source for live subscription.
SUBSCRIPTION_URL = (
    "https://ipowatch.in/ipo-subscription-status-today/"
)

STATUS_ORDER = {
    "LIVE": 1,
    "ALLOTMENT PENDING": 2,
    "BIDDING ENDED": 3,
    "UPCOMING": 4,
    "NOT CONFIRMED": 5,
    "LISTED": 6,
}


# =========================================================
# HTTP
# =========================================================

session = requests.Session()
session.headers.update(HEADERS)


def get(url, timeout=30):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


# =========================================================
# GENERIC HELPERS
# =========================================================

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def number(value):
    if value is None:
        return None

    s = str(value)
    s = s.replace(",", "")
    s = s.replace("₹", "")
    s = s.replace("Rs.", "")
    s = s.replace("Rs", "")

    match = re.search(r"-?\d+(?:\.\d+)?", s)

    if not match:
        return None

    try:
        return float(match.group(0))
    except Exception:
        return None


def parse_date(value):
    if not value:
        return None

    value = clean(value)

    formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value, fmt
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def first_date(text, labels):
    text = clean(text)

    for label in labels:
        pattern = (
            re.escape(label)
            + r"\s*[:\-]?\s*"
            r"(\d{1,2}\s+"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"[a-z]*"
            r"(?:,)?\s+\d{4})"
        )

        match = re.search(
            pattern,
            text,
            re.I,
        )

        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed

    return None


def date_from_range(text, labels):
    """
    Handles strings such as:
       IPO opens for subscription on 28 Aug, 2026
       and closes on 01 Sep, 2026
    """

    text = clean(text)

    open_date = None
    close_date = None

    open_patterns = [
        r"opens?\s+(?:for\s+subscription\s+)?on\s+"
        r"(\d{1,2}\s+\w+\s*,?\s+\d{4})",
        r"open\s+date\s+"
        r"(\d{1,2}\s+\w+\s*,?\s+\d{4})",
    ]

    close_patterns = [
        r"closes?\s+(?:for\s+subscription\s+)?on\s+"
        r"(\d{1,2}\s+\w+\s*,?\s+\d{4})",
        r"close\s+date\s+"
        r"(\d{1,2}\s+\w+\s*,?\s+\d{4})",
    ]

    for p in open_patterns:
        m = re.search(p, text, re.I)
        if m:
            open_date = parse_date(m.group(1))
            if open_date:
                break

    for p in close_patterns:
        m = re.search(p, text, re.I)
        if m:
            close_date = parse_date(m.group(1))
            if close_date:
                break

    return open_date, close_date


# =========================================================
# URL / NAME HELPERS
# =========================================================

def is_ipo_detail_url(url):
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.netloc.lower() not in {
        "moneycontrol.com",
        "www.moneycontrol.com",
    }:
        return False

    path = parsed.path.lower()

    # Moneycontrol detail pages normally end in -ipodetail.
    return (
        "/ipo/" in path
        and "ipodetail" in path
    )


def normalise_name(name):
    name = clean(name)

    name = re.sub(
        r"\s+IPO\s*$",
        "",
        name,
        flags=re.I,
    )

    name = re.sub(
        r"\s+Ltd\.?$",
        " Ltd",
        name,
        flags=re.I,
    )

    return name.strip()


def name_from_url(url):
    slug = url.rstrip("/").split("/")[-1]

    slug = re.sub(
        r"-ipodetail$",
        "",
        slug,
        flags=re.I,
    )

    slug = re.sub(
        r"[-_]+",
        " ",
        slug,
    )

    return normalise_name(
        slug.title()
    )


# =========================================================
# MONEYCONTROL DISCOVERY
# =========================================================

def discover_moneycontrol():
    """
    Returns:
        {
            canonical_url: {
                name: ...,
                type: Mainboard/SME
            }
        }
    """

    found = {}

    for listing_url in DISCOVERY_URLS:
        try:
            html = get(listing_url)

            soup = BeautifulSoup(
                html,
                "html.parser",
            )

            for anchor in soup.find_all(
                "a",
                href=True,
            ):
                href = urljoin(
                    "https://www.moneycontrol.com",
                    anchor["href"],
                )

                href = href.split("?")[0].rstrip("/")

                if not is_ipo_detail_url(href):
                    continue

                label = clean(
                    anchor.get_text(
                        " ",
                        strip=True,
                    )
                )

                if not label:
                    label = name_from_url(href)

                name = normalise_name(label)

                # Do not accept generic navigation labels.
                if name.lower() in {
                    "details",
                    "check",
                    "view",
                    "read more",
                    "open",
                    "upcoming",
                    "closed",
                    "listed",
                }:
                    name = name_from_url(href)

                ipo_type = (
                    "SME"
                    if "/ipo/sme" in listing_url.lower()
                    else "Mainboard"
                )

                # If the anchor is under an SME page,
                # keep SME classification.
                found[href] = {
                    "name": name,
                    "type": ipo_type,
                }

        except Exception as exc:
            print(
                "Discovery failed:",
                listing_url,
                "|",
                exc,
            )

    print(
        "Moneycontrol IPO detail pages discovered:",
        len(found),
    )

    return found


# =========================================================
# MONEYCONTROL DETAIL PARSER
# =========================================================

def find_detail_container(anchor):
    """
    Walk upward until a reasonably-sized card/row is found.
    """

    node = anchor

    for _ in range(8):
        node = node.parent

        if node is None:
            break

        text = clean(
            node.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "Open Date" in text
            or "Close Date" in text
            or "Lot Size" in text
            or "Subscription" in text
        ):
            if len(text) < 15000:
                return node

    return anchor.parent


def parse_moneycontrol_detail(url, fallback_name, fallback_type):
    html = get(url)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    page_text = clean(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # -----------------------------------------------------
    # Name
    # -----------------------------------------------------

    name = fallback_name

    h1 = soup.find("h1")

    if h1:
        candidate = normalise_name(
            h1.get_text(
                " ",
                strip=True,
            )
        )

        if candidate:
            name = candidate

    if not name:
        name = name_from_url(url)

    # -----------------------------------------------------
    # Type
    # -----------------------------------------------------

    page_lower = page_text.lower()

    if (
        " sme " in f" {page_lower} "
        or "sme ipo" in page_lower
        or fallback_type == "SME"
    ):
        ipo_type = "SME"
    else:
        ipo_type = "Mainboard"

    # -----------------------------------------------------
    # Dates
    # -----------------------------------------------------

    open_date, close_date = date_from_range(
        page_text
    )

    if not open_date:
        open_date = first_date(
            page_text,
            [
                "Open Date",
                "IPO Open Date",
                "Issue Open",
            ],
        )

    if not close_date:
        close_date = first_date(
            page_text,
            [
                "Close Date",
                "IPO Close Date",
                "Issue Close",
            ],
        )

    allotment_date = first_date(
        page_text,
        [
            "Basis of Allotment",
            "Allotment Date",
        ],
    )

    listing_date = first_date(
        page_text,
        [
            "Listing Date",
            "listing date",
        ],
    )

    # -----------------------------------------------------
    # Price
    # -----------------------------------------------------

    price_low = None
    price_high = None

    price_patterns = [
        r"price band\s+is\s+set\s+at\s+"
        r"₹?\s*([\d,.]+)\s+to\s+₹?\s*([\d,.]+)",

        r"Issue Price\s+₹?\s*([\d,.]+)\s*[-–]\s*"
        r"₹?\s*([\d,.]+)",

        r"₹\s*([\d,.]+)\s*[-–]\s*₹?\s*([\d,.]+)",
    ]

    for pattern in price_patterns:
        m = re.search(
            pattern,
            page_text,
            re.I,
        )

        if m:
            price_low = number(
                m.group(1)
            )
            price_high = number(
                m.group(2)
            )

            if price_low is not None:
                break

    # -----------------------------------------------------
    # Lot
    # -----------------------------------------------------

    lot_size = None

    lot_patterns = [
        r"Lot Size\s*([\d,]+)",
        r"lot size\s*[:\-]?\s*([\d,]+)",
        r"Market Lot\s*([\d,]+)",
    ]

    for pattern in lot_patterns:
        m = re.search(
            pattern,
            page_text,
            re.I,
        )

        if m:
            lot_size = int(
                number(m.group(1))
            )
            break

    # -----------------------------------------------------
    # Subscription
    # -----------------------------------------------------

    subscription = None

    sub_patterns = [
        r"Total\s+([\d.]+)x\s+IPO Dates",
        r"Total\s+([\d.]+)x",
        r"Times Subscribed\s*([\d.]+)x",
        r"Total Subscription\s*([\d.]+)x",
    ]

    for pattern in sub_patterns:
        m = re.search(
            pattern,
            page_text,
            re.I,
        )

        if m:
            subscription = number(
                m.group(1)
            )
            break

    # -----------------------------------------------------
    # Minimum investment
    #
    # For SME IPOs the correct amount must be based on
    # the actual minimum application / lot quantity.
    # If source provides an explicit minimum, use it.
    # Otherwise calculate from upper price band * lot size.
    # -----------------------------------------------------

    published_minimum = None

    minimum_patterns = [
        r"Minimum Investment\s*₹\s*([\d,.]+)",
        r"Min(?:imum)? Investment\s*₹\s*([\d,.]+)",
        r"Minimum investment\s*[:\-]?\s*₹?\s*([\d,.]+)",
    ]

    for pattern in minimum_patterns:
        m = re.search(
            pattern,
            page_text,
            re.I,
        )

        if m:
            published_minimum = number(
                m.group(1)
            )
            break

    calculated_minimum = None

    if (
        price_high is not None
        and lot_size is not None
    ):
        calculated_minimum = (
            price_high * lot_size
        )

    minimum_investment = (
        published_minimum
        if published_minimum is not None
        else calculated_minimum
    )

    # -----------------------------------------------------
    # GMP
    # -----------------------------------------------------

    gmp = None

    gmp_patterns = [
        r"\bGMP\b\s*[:\-]?\s*₹?\s*([\d,.]+)",
        r"Grey Market Premium\s*[:\-]?\s*₹?\s*([\d,.]+)",
    ]

    for pattern in gmp_patterns:
        m = re.search(
            pattern,
            page_text,
            re.I,
        )

        if m:
            gmp = number(
                m.group(1)
            )
            break

    return {
        "name": name,
        "type": ipo_type,
        "url": url,
        "priceLow": price_low,
        "priceHigh": price_high,
        "lotSize": lot_size,
        "minInvestment": minimum_investment,
        "minInvestmentPublished": published_minimum,
        "openDate": open_date,
        "closeDate": close_date,
        "allotmentDate": allotment_date,
        "listingDate": listing_date,
        "subscription": subscription,
        "gmp": gmp,
    }


# =========================================================
# IPO WATCH SUBSCRIPTION CROSS-CHECK
# =========================================================

def normalise_key(name):
    name = re.sub(
        r"[^a-z0-9]",
        "",
        name.lower(),
    )

    name = re.sub(
        r"ltd$",
        "",
        name,
    )

    return name


def get_ipowatch_subscriptions():
    """
    Returns:
        normalized company name -> total subscription

    This is a secondary source. Moneycontrol remains the
    primary source for dates and IPO universe.
    """

    result = {}

    try:
        html = get(
            SUBSCRIPTION_URL
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        text = clean(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        # IPO Watch commonly renders rows as:
        # Company | Type | Closing Date | QIB | NII |
        # Retail | Total | Last Updated

        rows = soup.find_all("tr")

        for row in rows:
            cells = [
                clean(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                )
                for cell in row.find_all(
                    ["td", "th"]
                )
            ]

            if len(cells) < 5:
                continue

            joined = " | ".join(cells)

            if (
                "IPO" in joined
                or "Type" in joined
                or "Closing" in joined
            ):
                continue

            # Find x-value candidates.
            x_values = []

            for cell in cells:
                m = re.fullmatch(
                    r"([\d.]+)\s*x",
                    cell,
                    re.I,
                )

                if m:
                    x_values.append(
                        number(m.group(1))
                    )

            if not x_values:
                continue

            # Total is normally the last x-value.
            total = x_values[-1]

            company = cells[0]

            if company:
                result[
                    normalise_key(company)
                ] = total

    except Exception as exc:
        print(
            "IPO Watch subscription cross-check failed:",
            exc,
        )

    print(
        "IPO Watch subscription records:",
        len(result),
    )

    return result


# =========================================================
# STATUS
# =========================================================

def to_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except Exception:
        return None


def calculate_status(
    open_date,
    close_date,
    allotment_date,
    listing_date,
):
    today = date.today()

    op = to_date(open_date)
    cl = to_date(close_date)
    al = to_date(allotment_date)
    li = to_date(listing_date)

    # Already listed.
    if li and today >= li:
        return "LISTED"

    # Bidding closed and allotment is still pending.
    if (
        cl
        and today > cl
        and al
        and today <= al
    ):
        return "ALLOTMENT PENDING"

    # Bidding closed but allotment is not yet completed.
    if (
        cl
        and today > cl
        and (
            not al
            or today < al
        )
    ):
        return "BIDDING ENDED"

    # Currently accepting applications.
    if (
        op
        and cl
        and op <= today <= cl
    ):
        return "LIVE"

    # Future IPO.
    if op and today < op:
        return "UPCOMING"

    return "NOT CONFIRMED"


# =========================================================
# ANALYSIS
# =========================================================

def calculate_analysis(
    ipo_type,
    price_high,
    subscription,
    gmp,
):
    """
    Transparent quantitative dashboard score.

    This is NOT presented as an "expert consensus" score.
    The UI should label it "Dashboard Score".

    Expert/source ratings can be added later as a separate
    field without mixing them into this score.
    """

    score = 5.0

    positives = []
    negatives = []

    if subscription is not None:

        if subscription >= 50:
            score += 2.0
            positives.append(
                "Exceptionally strong subscription"
            )

        elif subscription >= 20:
            score += 1.5
            positives.append(
                "Very strong subscription"
            )

        elif subscription >= 5:
            score += 0.8
            positives.append(
                "Healthy subscription"
            )

        elif subscription < 1:
            score -= 1.0
            negatives.append(
                "Weak subscription"
            )

    if (
        gmp is not None
        and price_high
        and price_high > 0
    ):

        gmp_pct = (
            gmp / price_high
        ) * 100

        if gmp_pct >= 25:
            score += 1.5
            positives.append(
                "Strong GMP indication"
            )

        elif gmp_pct >= 10:
            score += 0.8
            positives.append(
                "Positive GMP indication"
            )

        elif gmp_pct < 0:
            score -= 0.8
            negatives.append(
                "Negative GMP indication"
            )

    if ipo_type == "SME":

        score -= 0.5

        negatives.append(
            "SME liquidity and risk are higher"
        )

    score = max(
        0,
        min(10, score),
    )

    # Listing gains
    if (
        gmp is not None
        and price_high
        and price_high > 0
    ):

        gmp_pct = (
            gmp / price_high
        ) * 100

        if gmp_pct >= 25:
            listing_gains = "Strong"
        elif gmp_pct >= 10:
            listing_gains = "Positive"
        elif gmp_pct >= 0:
            listing_gains = "Moderate"
        else:
            listing_gains = "Weak"

    elif subscription is not None:

        if subscription >= 20:
            listing_gains = "Positive"
        elif subscription >= 5:
            listing_gains = "Moderate"
        else:
            listing_gains = "Weak"

    else:
        listing_gains = "Insufficient data"

    # Long-term
    if subscription is None:
        long_term = "Insufficient data"
    elif subscription >= 10:
        long_term = "Potentially Positive"
    elif subscription >= 3:
        long_term = "Neutral"
    else:
        long_term = "Caution"

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


# =========================================================
# VALIDATION
# =========================================================

def valid_record(record):
    if not record.get("name"):
        return False

    if not record.get("url"):
        return False

    # A real IPO should have at least some structural data.
    meaningful = [
        record.get("openDate"),
        record.get("closeDate"),
        record.get("priceHigh"),
        record.get("lotSize"),
    ]

    return any(
        value is not None
        for value in meaningful
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("IPO DATA UPDATE - MULTI SOURCE")
    print("=" * 70)

    discovered = discover_moneycontrol()

    if not discovered:
        print(
            "ERROR: No IPO detail pages discovered."
        )

        if OUT.exists():
            print(
                "Preserving previous ipo.json."
            )
            return

        raise RuntimeError(
            "IPO discovery returned zero records."
        )

    ipowatch_subs = (
        get_ipowatch_subscriptions()
    )

    records = []

    for index, (url, meta) in enumerate(
        discovered.items(),
        start=1,
    ):

        try:

            print(
                f"[{index}/{len(discovered)}] "
                f"{meta['name']}"
            )

            record = parse_moneycontrol_detail(
                url=url,
                fallback_name=meta["name"],
                fallback_type=meta["type"],
            )

            # Secondary subscription cross-check.
            key = normalise_key(
                record["name"]
            )

            if key in ipowatch_subs:

                secondary_sub = (
                    ipowatch_subs[key]
                )

                # Prefer the secondary source only
                # when the primary source is missing.
                if record["subscription"] is None:
                    record["subscription"] = (
                        secondary_sub
                    )

            record["status"] = calculate_status(
                record["openDate"],
                record["closeDate"],
                record["allotmentDate"],
                record["listingDate"],
            )

            record["analysis"] = (
                calculate_analysis(
                    ipo_type=record["type"],
                    price_high=record["priceHigh"],
                    subscription=record["subscription"],
                    gmp=record["gmp"],
                )
            )

            record["source"] = {
                "primary": "Moneycontrol",
                "subscriptionCrossCheck": (
                    "IPO Watch"
                ),
            }

            record["lastUpdated"] = (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            if not valid_record(record):
                print(
                    "  SKIPPED: insufficient IPO data"
                )
                continue

            # Listed IPOs are deliberately removed
            # from the active dashboard.
            if record["status"] == "LISTED":

                print(
                    "  LISTED -> excluded"
                )
                continue

            print(
                "  ",
                record["status"],
                "|",
                record["openDate"],
                "->",
                record["closeDate"],
                "| allotment:",
                record["allotmentDate"],
                "| listing:",
                record["listingDate"],
            )

            records.append(record)

        except Exception as exc:

            print(
                "  FAILED:",
                exc,
            )

        time.sleep(0.3)

    # -----------------------------------------------------
    # Deduplicate by URL
    # -----------------------------------------------------

    unique = {}

    for record in records:
        unique[
            record["url"].lower().rstrip("/")
        ] = record

    records = list(
        unique.values()
    )

    # -----------------------------------------------------
    # SAFETY
    # -----------------------------------------------------

    if not records:

        print(
            "ERROR: zero valid IPO records."
        )

        if OUT.exists():
            print(
                "Preserving previous ipo.json."
            )
            return

        raise RuntimeError(
            "No valid IPO records."
        )

    # -----------------------------------------------------
    # Sort:
    # LIVE
    # ALLOTMENT PENDING
    # BIDDING ENDED
    # UPCOMING
    # -----------------------------------------------------

    records.sort(
        key=lambda item: (
            STATUS_ORDER.get(
                item.get("status"),
                99,
            ),
            item.get("openDate")
            or "9999-12-31",
            item.get("name", "").lower(),
        )
    )

    payload = {
        "updatedAt": (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
        "source": (
            "Moneycontrol + IPO Watch"
        ),
        "count": len(records),
        "ipos": records,
    }

    # -----------------------------------------------------
    # Atomic write
    # -----------------------------------------------------

    temporary = OUT.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(OUT)

    print()
    print("=" * 70)
    print(
        "SUCCESS:",
        len(records),
        "active IPO records written."
    )
    print("=" * 70)

    for record in records:
        print(
            record["status"],
            "|",
            record["name"],
        )


if __name__ == "__main__":
    main()
