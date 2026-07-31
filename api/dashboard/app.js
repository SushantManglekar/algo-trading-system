const state = { configuration: null, selectedSymbol: null, candles: [] };
const $ = (id) => document.getElementById(id);
const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value || 0));
const number = (value) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(Number(value || 0));

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Request failed (${response.status})`); }
  return response.json();
}

function setText(id, value) { $(id).textContent = value; }
function setDot(id, enabled) { $(id).className = `dot ${enabled ? "on" : "off"}`; }

function renderConfiguration(configuration) {
  state.configuration = configuration;
  state.selectedSymbol ||= configuration.symbols[0] || null;
  const live = configuration.mode === "live";
  $("mode-badge").textContent = configuration.mode.toUpperCase();
  $("mode-badge").className = `badge ${live ? "badge-live" : "badge-paper"}`;
  setText("config-version", `Version ${configuration.version}`);
  $("mode").value = configuration.mode;
  $("automatic-orders").checked = configuration.place_orders_automatically;
  $("monitoring-enabled").checked = configuration.monitoring_enabled;
  $("symbols").value = configuration.symbols.join(", ");
  $("interval").value = configuration.strategy.interval;
  $("fast-period").value = configuration.strategy.fast_period;
  $("slow-period").value = configuration.strategy.slow_period;
  $("risk-per-trade").value = configuration.risk_policy.risk_per_trade_fraction;
  $("daily-loss").value = configuration.risk_policy.max_daily_loss_fraction;
  $("max-positions").value = configuration.risk_policy.max_open_positions;
  setText("watchlist-count", `${configuration.symbols.length} symbol${configuration.symbols.length === 1 ? "" : "s"}`);
  setDot("monitoring-dot", configuration.monitoring_enabled);
  setText("monitoring-status", configuration.monitoring_enabled ? "Monitoring enabled" : "Monitoring paused");
  setDot("automation-dot", configuration.place_orders_automatically);
  setText("automation-status", configuration.place_orders_automatically ? "Automatic orders enabled" : "Automatic orders disabled");
  renderWatchlist();
}

function renderWatchlist() {
  const parent = $("watchlist"); parent.replaceChildren();
  for (const symbol of state.configuration.symbols) {
    const button = document.createElement("button"); button.type = "button";
    button.className = `watch-item ${symbol === state.selectedSymbol ? "active" : ""}`;
    const title = document.createElement("span"); title.textContent = symbol;
    const detail = document.createElement("small"); detail.textContent = symbol === state.selectedSymbol ? "Chart selected" : "View chart";
    button.append(title, detail);
    button.onclick = async () => { state.selectedSymbol = symbol; renderWatchlist(); await loadChart(); };
    parent.append(button);
  }
  if (!state.configuration.symbols.length) parent.innerHTML = '<p class="panel-note">Add symbols in the configuration panel.</p>';
}

function renderAccount(account, positions) {
  setText("equity", money(account.equity)); setText("cash", money(account.cash)); setText("buying-power", money(account.buying_power));
  const daily = Number(account.equity) - Number(account.previous_close_equity || account.equity);
  const target = $("daily-pnl"); target.textContent = `${daily >= 0 ? "+" : ""}${money(daily)}`; target.className = daily >= 0 ? "positive" : "negative";
  setText("position-count", String(positions.length));
}

function renderTable(id, rows, columns, emptyText) {
  const target = $(id); target.replaceChildren();
  if (!rows.length) { target.innerHTML = `<tr><td colspan="${columns.length}" class="muted">${emptyText}</td></tr>`; return; }
  rows.forEach((row) => { const tr = document.createElement("tr"); columns.forEach((column) => { const td = document.createElement("td"); const value = column(row); td.textContent = value.text ?? value; if (value.className) td.className = value.className; tr.append(td); }); target.append(tr); });
}

function renderSignals(signals) {
  setText("signal-count", `${signals.length} total`); const parent = $("signals"); parent.replaceChildren();
  signals.slice(0, 5).forEach((signal) => {
    const card = document.createElement("div"); card.className = "signal approved";
    const title = document.createElement("strong"); title.textContent = `${signal.symbol} ${signal.direction}`;
    const detail = document.createElement("span"); detail.textContent = `${signal.strategy} · ${signal.reason}`;
    card.append(title, detail); parent.append(card);
  });
  if (!signals.length) parent.innerHTML = '<p class="panel-note">No approved signals have been generated yet.</p>';
}

async function loadChart() {
  const symbol = state.selectedSymbol; setText("chart-symbol", symbol || "Select a symbol"); setText("chart-interval", state.configuration?.strategy.interval || "--");
  if (!symbol) { state.candles = []; drawChart(); return; }
  const end = new Date(); const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
  try { state.candles = await api(`/market/candles/${symbol}?interval=${encodeURIComponent(state.configuration.strategy.interval)}&start_at=${encodeURIComponent(start.toISOString())}&end_at=${encodeURIComponent(end.toISOString())}`); }
  catch (error) { state.candles = []; $("chart-empty").textContent = error.message; }
  drawChart();
}

function drawChart() {
  const canvas = $("price-chart"), empty = $("chart-empty"), candles = state.candles;
  if (!candles.length) { canvas.style.display = "none"; empty.style.display = "block"; return; }
  canvas.style.display = "block"; empty.style.display = "none";
  const width = canvas.clientWidth, height = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr; canvas.height = height * dpr; const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, width, height);
  const visible = candles.slice(-120), prices = visible.flatMap((c) => [Number(c.high), Number(c.low)]); const low = Math.min(...prices), high = Math.max(...prices), span = Math.max(high - low, 0.01);
  const pad = { left: 10, right: 44, top: 16, bottom: 20 }, chartW = width - pad.left - pad.right, chartH = height - pad.top - pad.bottom;
  const y = (price) => pad.top + (high - price) / span * chartH;
  ctx.strokeStyle = "rgba(148,166,191,.18)"; ctx.fillStyle = "#94a6bf"; ctx.font = "11px system-ui";
  for (let i = 0; i < 4; i += 1) { const price = low + span * i / 3; const yy = y(price); ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(width - pad.right, yy); ctx.stroke(); ctx.fillText(price.toFixed(2), width - pad.right + 5, yy + 3); }
  const step = chartW / Math.max(visible.length, 1), body = Math.max(2, step * .65);
  visible.forEach((candle, index) => { const x = pad.left + index * step + step / 2; const up = Number(candle.close) >= Number(candle.open); ctx.strokeStyle = up ? "#56e3b1" : "#ff7f86"; ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(x, y(Number(candle.high))); ctx.lineTo(x, y(Number(candle.low))); ctx.stroke(); const top = Math.min(y(Number(candle.open)), y(Number(candle.close))); const bodyHeight = Math.max(1, Math.abs(y(Number(candle.open)) - y(Number(candle.close)))); ctx.fillRect(x - body / 2, top, body, bodyHeight); });
}

async function refresh() {
  $("system-badge").textContent = "Refreshing";
  try {
    const [configuration, trading, account, positions, orders, signals] = await Promise.all([api("/control"), api("/trading/status"), api("/trading/account"), api("/trading/positions"), api("/trading/orders"), api("/signals")]);
    renderConfiguration(configuration); renderAccount(account, positions); renderSignals(signals);
    setText("provider-status", `Market data: ${trading.market_data_provider}`); setText("worker-status", trading.pipeline_running ? "Worker: running" : "Worker: paused");
    $("system-badge").textContent = "System healthy";
    renderTable("positions", positions, [(r) => r.symbol, (r) => number(r.quantity), (r) => money(r.market_value), (r) => ({ text: money(r.unrealized_pnl), className: Number(r.unrealized_pnl) >= 0 ? "positive" : "negative" })], "No open positions");
    renderTable("orders", orders, [(r) => r.symbol, (r) => r.side.toUpperCase(), (r) => number(r.quantity), (r) => r.status.replaceAll("_", " ")], "No orders recorded");
    await loadChart();
  } catch (error) { $("system-badge").textContent = "Connection issue"; $("form-message").textContent = error.message; }
}

$("control-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const current = state.configuration; if (!current) return;
  const mode = $("mode").value, automatic = $("automatic-orders").checked;
  let liveConfirmation = null, automationConfirmation = null;
  if (mode === "live" && current.mode !== "live") liveConfirmation = window.prompt("Type ENABLE_LIVE_TRADING to confirm live mode") || null;
  if (automatic && (!current.place_orders_automatically || mode !== current.mode)) automationConfirmation = window.prompt(`Type ${mode === "live" ? "ENABLE_LIVE_AUTOMATION" : "ENABLE_PAPER_AUTOMATION"} to enable automatic orders`) || null;
  const payload = { mode, place_orders_automatically: automatic, monitoring_enabled: $("monitoring-enabled").checked, symbols: $("symbols").value.split(",").map((item) => item.trim()).filter(Boolean), strategy: { ...current.strategy, interval: $("interval").value, fast_period: Number($("fast-period").value), slow_period: Number($("slow-period").value) }, risk_policy: { ...current.risk_policy, risk_per_trade_fraction: $("risk-per-trade").value, max_daily_loss_fraction: $("daily-loss").value, max_open_positions: Number($("max-positions").value) }, expected_version: current.version, live_confirmation: liveConfirmation, automation_confirmation: automationConfirmation };
  try { $("form-message").textContent = "Applying configuration..."; const configuration = await api("/control", { method: "PUT", body: JSON.stringify(payload) }); renderConfiguration(configuration); $("form-message").textContent = "Configuration applied and audited."; await refresh(); }
  catch (error) { $("form-message").textContent = error.message; }
});
$("refresh-button").addEventListener("click", refresh);
window.addEventListener("resize", () => drawChart());
refresh(); setInterval(refresh, 30000);
