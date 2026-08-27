# Kunal's Stock Dashboard V6

Architecture:

`Public/delayed market data -> GitHub Actions -> data.json -> GitHub Pages`

## Files

- `index.html` — mobile-first dashboard, watchlist, tracking prices, charts, opportunities, categories and IPO UI.
- `updater.py` — isolated current-price/history/market updater with last-good-value preservation.
- `.github/workflows/update-data.yml` — scheduled updater plus manual `workflow_dispatch`.
- `data.json` — generated cached snapshot consumed by the frontend.
- `ipo.json` — explicit IPO-feed schema. It starts empty rather than inventing GMP/subscription data.

## Stability rules

- Personal stock quotes are updated independently.
- A failed quote does not delete its previous cached record.
- A failed historical download does not delete previous history.
- A failed market-index request preserves the last good index snapshot.
- Historical period cells use actual cached historical closes, not prices reconstructed from rounded percentages.
- NIFTY 500 screening is isolated from the personal watchlist pipeline.
- No undocumented NSE historical endpoint is used.

## IPO note

The UI and transparent 0–100 scoring model are wired for IPO data, including GMP, subscription, valuation, fundamentals and issue structure. `ipo.json` is intentionally empty until a stable verified feed is selected. GMP is unofficial and must never be presented as a guaranteed listing price or return.

## Scheduling

GitHub Actions schedules are approximate and can be delayed by GitHub. The workflow keeps manual dispatch and uses staggered weekday schedules around Indian market hours rather than running every five minutes overnight.

## Local checks

Run:

```bash
python test_updater.py
python -m py_compile updater.py
python - <<'PY'
import re
from pathlib import Path
s=Path("index.html").read_text()
Path("/tmp/dashboard.js").write_text(re.search(r"<script>(.*)</script>", s, re.S).group(1))
PY
node --check /tmp/dashboard.js
```

The updater's external NSE/Yahoo requests are not live-tested in the development environment; the unit checks use mock payloads.
