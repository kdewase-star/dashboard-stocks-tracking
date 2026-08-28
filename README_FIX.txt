KUNAL STOCK DASHBOARD — ROOT CAUSE FIX

Replace these files:
1. index.html
2. ipo_updater.py
3. ipo.json
4. .github/workflows/update-data.yml
5. sw.js

DO NOT replace updater.py.

ROOT CAUSES FOUND
-----------------
1. Historical data:
The previous browser history hydrator iterated over watchlist objects but
passed the entire object into the history fetcher. That produced requests
using "[object Object]" instead of symbols such as TCS/INFY/RELIANCE.
The new version normalizes each entry to its symbol before fetching history.

It also:
- fills 1M/3M/6M/9M/1Y/5Y/all-time
- uses the latest historical close if a newly added stock has no current record
- fetches missing history automatically
- keeps existing good history unchanged

2. IPO:
The repository's ipo.json currently contains:
    "ipos": []

The old ipo_updater.py could finish successfully while producing zero IPO
records because it only inspected pages and returned an empty parsed list.
That is why GitHub Actions was green while the IPO tab was empty.

The new updater:
- has a current-cycle fallback snapshot
- calculates current status
- keeps live/upcoming/closed-but-not-listed issues
- removes issues after their listing date
- refuses to write an empty IPO snapshot

3. Workflow:
Validation now FAILS if ipo.json contains zero records, so an empty IPO
dataset can no longer be silently published as a successful update.

4. Cache:
Service-worker cache version is bumped so Android Chrome receives the new
index instead of the previous cached version.

IMPORTANT:
The current IPO fallback is based on public IPO information checked on
28 Aug 2026. Live scraping itself was not executable from this environment
because outbound network DNS is unavailable here. The GitHub Action will try
the live public source first and use the fallback if that source is temporarily
unavailable.
