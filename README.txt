# Kunal's Stock Dashboard — Complete Update

Replace/create these files in the repository:

1. index.html — replace
2. sw.js — replace
3. manifest.json — replace
4. updater.py — KEEP the existing working repository version
5. ipo_updater.py — create
6. history-cache.json — create
7. .github/workflows/update-data.yml — replace

IMPORTANT:
The package intentionally does NOT overwrite updater.py because the repository's
current updater contains the working NSE/current-price pipeline. The updater
already contains Yahoo historical fetching and resilient cached-value handling.

After uploading:
- Commit the files.
- Go to Actions → Update Market Data → Run workflow.
- Wait for the workflow to finish.
- Open the dashboard and hard-refresh once.

The dashboard changes include:
- IPO decision summary
- score displayed in score colour
- IPO status badges
- active vs listed handling
- historical fallback for user-added stocks
- service-worker cache bump
