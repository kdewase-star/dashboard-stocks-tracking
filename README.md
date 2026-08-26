# Kunal Stock Dashboard V5

This version removes browser-side finance API calls.

Architecture:

`GitHub Actions -> data.json -> GitHub Pages dashboard`

Files:
- `index.html` — dashboard
- `updater.py` — fetches delayed public market data
- `.github/workflows/update-data.yml` — scheduled updater
- `data.json` — generated market snapshot

The updater runs every 15 minutes on weekdays and can also be run manually from GitHub Actions.

After uploading these files:
1. Open GitHub → Actions.
2. Select **Update market data**.
3. Tap **Run workflow** once.
4. Wait for the green tick.
5. Refresh the dashboard.

The scheduled workflow runs on the default branch. GitHub notes that scheduled workflows can be delayed under load.
