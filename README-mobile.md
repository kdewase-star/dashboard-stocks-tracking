# US Stock Watcher — mobile app

This is a mobile-first PWA companion for `kdewase-star/dashboard-stocks-tracking`.

## Files
- `mobile.html` — mobile app UI
- `mobile-manifest.json` — standalone app manifest
- `sw-mobile.js` — offline cache/service worker

## Install in the existing GitHub Pages repo
Copy these three files into the repository root. The existing `icons/` folder is reused.

Then open:
`https://<your-github-pages-host>/mobile.html`

On Android Chrome choose **Add to Home screen**.

## Data
The app reads the repository's `data.json` and refreshes every 5 minutes. It recognizes common quote fields and falls back to the saved reference prices shown in the dashboard when a current field is unavailable.

The 26-watchlist symbols are the user's configured favourites, with informational dip thresholds:
- daily move <= -4%
- 20-trading-day drawdown <= -7% when supplied by the data
- daily move <= -10% (sharp dip)

Background push notifications still require a push service/server; this version evaluates the snapshot on app refresh.
