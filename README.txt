DASHBOARD IPO FIX V14
=====================

This package is intentionally a SAFE PATCH, not a replacement dashboard.

Why:
The current repository's ipo_updater.py was overwritten and now contains
only Paluck Technologies. Replacing it with another hard-coded list would
repeat the same problem.

V14 instead discovers the current IPO universe dynamically and enriches
each IPO from its detail page.

Files:
- ipo_updater.py
- ipo_renderer_fix.js
- ipo_fix.css
- requirements-ipo.txt
- README.txt

Install:
pip install -r requirements-ipo.txt

Run:
python ipo_updater.py

Then commit the generated ipo.json.

IMPORTANT:
1. Remove the old hard-coded IPOS=[...] updater logic.
2. Keep your existing index.html; merge the renderer/CSS into it.
3. Remove the "Can Apply?" table column.
4. The table must use separate fields:
   analysis.listingGains
   analysis.longTerm
   analysis.risk
5. Do not publish an empty ipo.json if the source fails.

The updater discovers all current/upcoming IPO pages rather than only
Paluck. It excludes already-listed issues from the active feed.

Paluck:
- ₹46-₹48
- 3,000 shares/lot
- retail minimum 2 lots
- 6,000 shares
- ₹2.76L lower-band value
- ₹2.88L upper-band/cut-off value

The live source may report a single minimum application amount at the
upper/cut-off band. The dashboard retains both calculated band values
when price and lot data are available.
