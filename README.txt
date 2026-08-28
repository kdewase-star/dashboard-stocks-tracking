Kunal Stock Dashboard V12 accuracy fix.

Replace index.html, updater.py, ipo_updater.py, ipo.json, history-cache.json, and .github/workflows/update-data.yml.
Run Actions -> Update Market Data manually once after upload.

Important: market-cap values are normalized from NSE raw totalMarketCap (₹ lakh) to ₹ crore. Historical data is stored server-side in history-cache.json, with common added symbols prioritized and NIFTY 500 symbols batched. IPO snapshot uses multi-source public data checked 28 Aug 2026; GMP is unofficial.
