/* IPO renderer fix
   Replace the existing IPO row renderer with this function.
   It deliberately reads listingGains, longTerm and risk from
   separate properties so values cannot shift between columns.
*/

function ipoStatusClass(status) {
  const s = String(status || "").toUpperCase();
  if (s === "LIVE") return "ipo-live";
  if (s === "BIDDING ENDED") return "ipo-ended";
  if (s === "UPCOMING") return "ipo-upcoming";
  return "ipo-listed";
}

function scoreClass(score) {
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

  [...(ipos || [])].forEach(ipo => {
    const a = ipo.analysis || {};
    const score = Number(a.score);

    const low = Number(ipo.minInvestmentLow);
    const high = Number(ipo.minInvestmentHigh);

    let minInvestment = ipo.minInvestment || "-";
    if (Number.isFinite(low) && Number.isFinite(high)) {
      minInvestment =
        `₹${(low / 100000).toFixed(2)}L - ₹${(high / 100000).toFixed(2)}L`;
    }

    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td class="name">
        <strong>${ipo.name || "-"}</strong>
        <span class="ticker">${ipo.type || ""}</span>
      </td>

      <td>
        <span class="ipo-status ${ipoStatusClass(ipo.status)}">
          ${ipo.status || "-"}
        </span>
      </td>

      <td>₹${ipo.priceLow ?? "-"} - ₹${ipo.priceHigh ?? "-"}</td>

      <td>
        ${ipo.lotSize ?? "-"}
        <span class="ticker">${ipo.retailMinLots ?? 1} lot(s)</span>
      </td>

      <td>
        <strong>${minInvestment}</strong>
        <span class="ticker">${ipo.retailMinShares ?? "-"} shares</span>
      </td>

      <td>
        ${ipo.subscription == null ? "-" : `${ipo.subscription}×`}
      </td>

      <td>
        ${ipo.gmp == null ? "-" : `₹${ipo.gmp}`}
      </td>

      <td>
        <span class="ipo-score ${scoreClass(score)}">
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
