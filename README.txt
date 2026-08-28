IPO Dashboard Fix v13
======================

This ZIP fixes the two IPO issues discussed:

1. SME minimum investment
   Paluck Technologies:
   - Price: ₹46–₹48
   - Lot: 3,000 shares
   - Retail minimum: 2 lots
   - Shares required: 6,000
   - Investment: ₹2.76L–₹2.88L

2. Analysis columns
   Listing Gains, Long Term and Risk are now read from independent
   fields:
     analysis.listingGains
     analysis.longTerm
     analysis.risk

Files:
- ipo_updater.py       Replace your existing updater.
- ipo_renderer_fix.js  Add/replace the IPO rendering function.
- ipo_fix.css          Add to the <style> section of index.html.

Important:
Do NOT remove your existing IPO records and replace them with only
the Paluck record in production. Merge the same data model into your
existing multi-IPO updater. The supplied updater is a structurally
correct reference for the fix.

After updating:
1. Run the GitHub Action that updates IPO data.
2. Confirm ipo.json contains minInvestmentLow,
   minInvestmentHigh, retailMinLots and analysis as separate fields.
3. Hard-refresh the dashboard.

Do not assign an IPO's score, listing-gain outlook, long-term outlook,
or risk by copying values between columns.
