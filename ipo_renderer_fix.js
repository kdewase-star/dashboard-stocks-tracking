/* Merge this renderer into the existing index.html IPO renderer. */

function ipoStatusClass(status) {
  const s = String(status || "").toUpperCase();
  if (s === "LIVE") return "ipo-live";
  if (s === "BIDDING ENDED") return "ipo-ended";
  if (s === "UPCOMING") return "ipo-upcoming";
  return "ipo-listed";
}

function ipoScoreClass(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return "score-na";
  if (n >= 7) return "score-green";
  if (n >= 5) return "score-yellow";
  return "score-red";
}

function renderIPO(ipos) {
  const tbody = document.getElementById("ipoTableBody");
  if (!tbody) return;

  tbody.innerHTML = "";

  (ipos || []).forEach(ipo => {
    const a = ipo.analysis || {};
    const score = Number(a.score);

    const low = Number(ipo.minInvestmentLow);
    const high = Number(ipo.minInvestmentHigh);

    let investment = ipo.minInvestment || "—";
    if (Number.isFinite(low) && Number.isFinite(high)) {
      investment =
        `₹${(low / 100000).toFixed(2)}L - ₹${(high / 100000).toFixed(2)}L`;
    }

    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td class="name">
        <strong>${ipo.name || "—"}</strong>
        <span class="ticker">${ipo.type || ""}</span>
      </td>

      <td>
        <span class="ipo-status ${ipoStatusClass(ipo.status)}">
          ${ipo.status || "—"}
        </span>
      </td>

      <td>₹${ipo.priceLow ?? "—"} - ₹${ipo.priceHigh ?? "—"}</td>

      <td>
        ${ipo.lotSize ?? "—"}
        <span class="ticker">${ipo.retailMinLots ?? "—"} lot(s)</span>
      </td>

      <td>
        <strong>${investment}</strong>
        <span class="ticker">${ipo.retailMinShares ?? "—"} shares</span>
      </td>

      <td>${ipo.subscription == null ? "—" : `${ipo.subscription}×`}</td>

      <td>${ipo.gmp == null ? "—" : `₹${ipo.gmp}`}</td>

      <td>
        <span class="ipo-score ${ipoScoreClass(score)}">
          ${Number.isFinite(score) ? score.toFixed(1) : "—"}
        </span>
      </td>

      <td>${a.listingGains || "—"}</td>
      <td>${a.longTerm || "—"}</td>
      <td>${a.risk || "—"}</td>
    `;

    tbody.appendChild(tr);
  });
}
