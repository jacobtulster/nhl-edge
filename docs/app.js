function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function odds(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(2);
}

function evText(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}

function evClass(value) {
  if (value == null || Number.isNaN(value)) return "";
  return value > 0 ? "ev-pos" : "ev-neg";
}

function topSide(game) {
  if (!game.best_side || game.best_ev == null) return "—";
  const team =
    game.best_side === "home"
      ? game.home_abbreviation
      : game.away_abbreviation;
  const hot = game.best_ev > 0 ? " hot" : "";
  return `<span class="pill${hot}">${team} · ${evText(game.best_ev)}</span>`;
}

function fmtU(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}u`;
}

function fmtRoi(summary) {
  if (!summary || summary.roi == null) return "—";
  const v = Number(summary.roi) * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let equityChart = null;

async function loadBoard() {
  const meta = document.getElementById("meta");
  const rows = document.getElementById("rows");
  const footnote = document.getElementById("footnote");

  try {
    const response = await fetch(`./ev_board.json?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    meta.textContent = data.generated_at_et
      ? `Updated ${data.generated_at_et} · ${data.game_count || 0} games · trained on ${data.training_games || 0} games`
      : "Board not generated yet — waiting for the first hourly run.";

    footnote.textContent = data.note || "";

    if (!data.games || data.games.length === 0) {
      rows.innerHTML =
        '<tr><td colspan="7">No upcoming games on the board right now.</td></tr>';
      return;
    }

    rows.innerHTML = data.games
      .map((game) => {
        return `<tr>
          <td class="matchup">${game.away_abbreviation} @ ${game.home_abbreviation}</td>
          <td>${pct(game.home_win_probability)}</td>
          <td>${odds(game.home_decimal)}</td>
          <td class="${evClass(game.home_ev)}">${evText(game.home_ev)}</td>
          <td>${odds(game.away_decimal)}</td>
          <td class="${evClass(game.away_ev)}">${evText(game.away_ev)}</td>
          <td>${topSide(game)}</td>
        </tr>`;
      })
      .join("");
  } catch (error) {
    meta.textContent = "Could not load the board.";
    rows.innerHTML = `<tr><td colspan="7">${error.message}</td></tr>`;
  }
}

function renderRoiCards(summary) {
  const root = document.getElementById("roi-cards");
  const s = summary || {};
  const profitCls =
    s.profit_u > 0 ? "ev-pos" : s.profit_u < 0 ? "ev-neg" : "";
  const roiCls = s.roi > 0 ? "ev-pos" : s.roi < 0 ? "ev-neg" : "";
  root.innerHTML = [
    ["ROI", fmtRoi(s), roiCls],
    ["Profit", fmtU(s.profit_u), profitCls],
    ["Record", `${s.w || 0}-${s.l || 0}-${s.p || 0}`, ""],
    ["Graded", `${s.graded || 0}/${s.picks || 0}`, ""],
  ]
    .map(
      ([k, v, cls]) =>
        `<div class="card"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`
    )
    .join("");
}

function renderEquity(equity) {
  const ctx = document.getElementById("equity-chart");
  if (equityChart) equityChart.destroy();
  const rows = equity || [];
  if (!rows.length) {
    equityChart = new Chart(ctx, {
      type: "line",
      data: { labels: ["—"], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          title: {
            display: true,
            text: "No graded picks yet",
            color: "#9aaba1",
          },
        },
      },
    });
    return;
  }

  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: rows.map((r) => String(r.n)),
      datasets: [
        {
          label: "Above 0",
          data: rows.map((r) => r.pos),
          borderColor: "rgba(62,207,142,0.15)",
          backgroundColor: "rgba(62, 207, 142, 0.28)",
          fill: "origin",
          pointRadius: 0,
          tension: 0.15,
          order: 2,
        },
        {
          label: "Below 0",
          data: rows.map((r) => r.neg),
          borderColor: "rgba(240,113,120,0.15)",
          backgroundColor: "rgba(240, 113, 120, 0.28)",
          fill: "origin",
          pointRadius: 0,
          tension: 0.15,
          order: 2,
        },
        {
          label: "Equity",
          data: rows.map((r) => r.cum),
          borderColor: "#e08a4f",
          backgroundColor: "transparent",
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.15,
          borderWidth: 2,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#9aaba1",
            filter: (item) => item.text === "Equity",
          },
        },
        tooltip: {
          callbacks: {
            title(items) {
              const i = items[0] && items[0].dataIndex;
              const t = rows[i];
              return t ? t.matchup : "";
            },
            label(item) {
              if (item.dataset.label !== "Equity") return null;
              const t = rows[item.dataIndex];
              if (!t) return "";
              return `${t.team || t.side} · ${t.result} ${fmtU(t.profit)} → ${fmtU(t.cum)}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Graded pick #", color: "#9aaba1" },
          ticks: { color: "#9aaba1" },
          grid: { color: "rgba(42,52,47,0.55)" },
        },
        y: {
          title: { display: true, text: "Cumulative units", color: "#9aaba1" },
          ticks: { color: "#9aaba1" },
          grid: { color: "rgba(42,52,47,0.55)" },
          grace: "8%",
        },
      },
    },
  });
}

function renderPicksTable(picks) {
  const body = document.getElementById("picks-rows");
  if (!picks || !picks.length) {
    body.innerHTML =
      '<tr><td colspan="7">No tracked picks yet — they appear after the next hourly run when a topside has EV ≥ 0.</td></tr>';
    return;
  }
  body.innerHTML = picks
    .map((p) => {
      const r = String(p.result || "").toUpperCase();
      const resPill =
        r === "W" ? "pill hot" : r === "L" ? "pill bad" : r === "P" ? "pill" : "pill";
      const when = p.loggedAt ? new Date(p.loggedAt).toLocaleString() : "—";
      const matchup = `${p.away_abbreviation || "?"} @ ${p.home_abbreviation || "?"}`;
      const profit =
        r === "W" || r === "L" || r === "P" ? fmtU(p.profit) : "—";
      return `<tr>
        <td>${escapeHtml(when)}</td>
        <td class="matchup">${escapeHtml(matchup)}</td>
        <td><span class="pill">${escapeHtml(p.takeTeam || p.team || p.takeSide || "")}</span></td>
        <td>${odds(p.decimal)}<div class="submeta">${escapeHtml(p.lineBook || "")}</div></td>
        <td class="${evClass(p.ev)}">${evText(p.ev)}</td>
        <td><span class="${resPill}">${r || "OPEN"}</span></td>
        <td class="${p.profit > 0 ? "ev-pos" : p.profit < 0 ? "ev-neg" : ""}">${profit}</td>
      </tr>`;
    })
    .join("");
}

async function loadPicks() {
  const meta = document.getElementById("roi-meta");
  try {
    const response = await fetch(`./picks.json?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const summary = data.summary || {};
    meta.textContent = data.updatedAt
      ? `Ledger ${new Date(data.updatedAt).toLocaleString()} · ${summary.picks || 0} picks`
      : "Ledger ready";
    renderRoiCards(summary);
    renderEquity(data.equity || []);
    renderPicksTable(data.picks || []);
  } catch (error) {
    meta.textContent = "Picks ledger not published yet.";
    renderRoiCards({});
    renderEquity([]);
    document.getElementById("picks-rows").innerHTML =
      `<tr><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
  }
}

loadBoard();
loadPicks();
