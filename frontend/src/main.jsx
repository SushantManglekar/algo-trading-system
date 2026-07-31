import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function Toggle({ checked, onChange, label }) {
  return <label className="flex cursor-pointer items-center justify-between gap-5 rounded-xl border border-slate-100 px-3 py-3 text-sm dark:border-slate-800">
    <span className="font-medium">{label}</span>
    <input aria-label={label} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="peer sr-only" />
    <span className="relative h-6 w-11 rounded-full bg-slate-200 transition after:absolute after:left-1 after:top-1 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow-sm after:transition peer-checked:bg-blue-600 peer-checked:after:translate-x-5 dark:bg-slate-700" />
  </label>;
}

function Sparkline({ positive = true }) {
  const path = positive ? "M2 39 C17 30 24 35 35 26 S55 31 69 17 S87 25 103 8" : "M2 12 C18 19 25 17 38 26 S58 19 70 31 S89 26 103 40";
  return <svg viewBox="0 0 105 48" className="h-11 w-24 overflow-visible" aria-hidden="true">
    <path d={path} fill="none" stroke={positive ? "#2563eb" : "#ef4444"} strokeWidth="3" strokeLinecap="round" />
  </svg>;
}

function PriceChart({ candles }) {
  const data = candles.slice(-50);
  const chart = useMemo(() => {
    if (!data.length) return { points: [], low: 0, high: 0, latest: null };
    const values = data.flatMap((item) => [Number(item.high), Number(item.low)]);
    const low = Math.min(...values); const high = Math.max(...values); const range = Math.max(high - low, 0.01);
    return { low, high, latest: data.at(-1), points: data.map((item, index) => ({
      x: 8 + index * (272 / Math.max(data.length - 1, 1)),
      y: 110 - ((Number(item.close) - low) / range) * 92,
    })) };
  }, [data]);
  if (!chart.points.length) return <div className="grid h-full place-items-center text-sm text-slate-400">Historical candles will appear here.</div>;
  const line = chart.points.map((point) => `${point.x},${point.y}`).join(" ");
  const labels = [chart.high, chart.low + (chart.high - chart.low) / 2, chart.low];
  return <svg className="h-full w-full" viewBox="0 0 340 126" preserveAspectRatio="none" role="img" aria-label="Historical closing-price chart with price scale">
    {[18, 64, 110].map((y) => <line key={y} x1="0" y1={y} x2="284" y2={y} stroke="currentColor" strokeOpacity="0.08" />)}
    <polyline points={line} fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx={chart.points.at(-1).x} cy={chart.points.at(-1).y} r="4" fill="#2563eb" stroke="white" strokeWidth="2" />
    {labels.map((price, index) => <text key={price} x="292" y={22 + index * 46} fill="currentColor" fillOpacity="0.5" fontSize="9">${price.toFixed(2)}</text>)}
  </svg>;
}

function OhlcValue({ label, value }) {
  return <span className="whitespace-nowrap text-[11px] text-slate-400">{label} <b className="ml-1 font-semibold text-slate-700 dark:text-slate-200">${value.toFixed(2)}</b></span>;
}

function SettingsDrawer({ configuration, onClose, onSave, error }) {
  const [draft, setDraft] = useState(configuration);
  useEffect(() => setDraft(configuration), [configuration]);
  if (!configuration || !draft) return null;
  const update = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const updateStrategy = (key, value) => setDraft((current) => ({ ...current, strategy: { ...current.strategy, [key]: value } }));
  const updateRisk = (key, value) => setDraft((current) => ({ ...current, risk_policy: { ...current.risk_policy, [key]: value } }));
  const submit = async (event) => {
    event.preventDefault();
    const enteringLive = draft.mode === "live" && configuration.mode !== "live";
    const enablingAuto = draft.place_orders_automatically && (!configuration.place_orders_automatically || draft.mode !== configuration.mode);
    const live_confirmation = enteringLive ? window.prompt("Type ENABLE_LIVE_TRADING to confirm live mode") || null : null;
    const expected = draft.mode === "live" ? "ENABLE_LIVE_AUTOMATION" : "ENABLE_PAPER_AUTOMATION";
    const automation_confirmation = enablingAuto ? window.prompt(`Type ${expected} to enable automatic orders`) || null : null;
    await onSave({ ...draft, symbols: draft.symbols.split(",").map((symbol) => symbol.trim()).filter(Boolean), expected_version: configuration.version, live_confirmation, automation_confirmation });
  };
  return <div className="fixed inset-0 z-50 bg-slate-950/30 backdrop-blur-[2px]">
    <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-2xl dark:bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5 dark:border-slate-800"><div><p className="metric-label">Control plane</p><h2 className="mt-1 text-lg font-semibold">Trading settings</h2></div><button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full text-xl text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Close settings">×</button></div>
      <form onSubmit={submit} className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
        <section><p className="metric-label mb-3">Execution</p><div className="space-y-3"><label className="block text-sm font-medium">Mode<select value={draft.mode} onChange={(event) => update("mode", event.target.value)} className="field"><option value="paper">Paper</option><option value="live">Live</option></select></label><Toggle label="Place orders automatically" checked={draft.place_orders_automatically} onChange={(value) => update("place_orders_automatically", value)} /><Toggle label="Monitor selected symbols" checked={draft.monitoring_enabled} onChange={(value) => update("monitoring_enabled", value)} /></div></section>
        <section><p className="metric-label mb-3">Watchlist and strategy</p><div className="space-y-3"><label className="block text-sm font-medium">Symbols<input className="field" value={draft.symbols} onChange={(event) => update("symbols", event.target.value)} placeholder="AAPL, MSFT, NVDA" /></label><div className="grid grid-cols-2 gap-3"><label className="text-sm font-medium">Interval<select className="field" value={draft.strategy.interval} onChange={(event) => updateStrategy("interval", event.target.value)}><option value="1m">1 minute</option><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="1h">1 hour</option><option value="1d">1 day</option></select></label><label className="text-sm font-medium">Fast EMA<input className="field" type="number" min="2" value={draft.strategy.fast_period} onChange={(event) => updateStrategy("fast_period", Number(event.target.value))} /></label><label className="text-sm font-medium">Slow EMA<input className="field" type="number" min="3" value={draft.strategy.slow_period} onChange={(event) => updateStrategy("slow_period", Number(event.target.value))} /></label></div></div></section>
        <section><p className="metric-label mb-3">Risk limits</p><div className="grid grid-cols-2 gap-3"><label className="text-sm font-medium">Risk / trade<input className="field" type="number" step="0.001" value={draft.risk_policy.risk_per_trade_fraction} onChange={(event) => updateRisk("risk_per_trade_fraction", event.target.value)} /></label><label className="text-sm font-medium">Daily loss limit<input className="field" type="number" step="0.001" value={draft.risk_policy.max_daily_loss_fraction} onChange={(event) => updateRisk("max_daily_loss_fraction", event.target.value)} /></label><label className="text-sm font-medium">Max positions<input className="field" type="number" min="1" value={draft.risk_policy.max_open_positions} onChange={(event) => updateRisk("max_open_positions", Number(event.target.value))} /></label></div></section>
        {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
      </form>
      <div className="border-t border-slate-100 p-6 dark:border-slate-800"><button onClick={submit} className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700">Save changes</button></div>
    </aside>
  </div>;
}

function App() {
  const [configuration, setConfiguration] = useState(null);
  const [snapshot, setSnapshot] = useState({ account: null, positions: [], orders: [], signals: [], status: null });
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [candles, setCandles] = useState([]);
  const [chartRange, setChartRange] = useState("1W");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem("dashboard-theme") === "dark");
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      const [control, status, account, positions, orders, signals] = await Promise.all([request("/control"), request("/trading/status"), request("/trading/account"), request("/trading/positions"), request("/trading/orders"), request("/signals")]);
      setConfiguration(control); setSnapshot({ status, account, positions, orders, signals });
      setSelectedSymbol((selected) => selected || control.symbols[0] || null); setError("");
    } catch (reason) { setError(reason.message); }
  };
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 30000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("dashboard-theme", dark ? "dark" : "light"); }, [dark]);
  useEffect(() => {
    if (!selectedSymbol || !configuration) { setCandles([]); return; }
    const days = { "1D": 1, "1W": 7, "1M": 30, "1Y": 365, MAX: 3650 };
    const end = new Date(); const start = new Date(end.getTime() - days[chartRange] * 86_400_000);
    request(`/market/candles/${selectedSymbol}?interval=${configuration.strategy.interval}&start_at=${encodeURIComponent(start.toISOString())}&end_at=${encodeURIComponent(end.toISOString())}`).then(setCandles).catch(() => setCandles([]));
  }, [selectedSymbol, configuration?.strategy?.interval, chartRange]);
  const save = async (payload) => {
    try { const next = await request("/control", { method: "PUT", body: JSON.stringify(payload) }); setConfiguration(next); setSelectedSymbol(next.symbols[0] || null); setSettingsOpen(false); await refresh(); }
    catch (reason) { setError(reason.message); }
  };
  const account = snapshot.account;
  const dailyPnl = account ? Number(account.equity) - Number(account.previous_close_equity || account.equity) : 0;
  const isPaper = configuration?.mode !== "live";
  const marketSummary = useMemo(() => {
    if (!candles.length) return null;
    const latest = candles.at(-1); const first = candles.at(0);
    const close = Number(latest.close); const change = close - Number(first.open);
    return { open: Number(latest.open), close, high: Number(latest.high), low: Number(latest.low), change, changePercent: (change / Number(first.open)) * 100 };
  }, [candles]);
  return <div className="h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
    <main className="mx-auto flex h-full max-w-[1600px] flex-col px-5 py-5 lg:px-8">
      <header className="flex shrink-0 items-center justify-between gap-4"><div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-bold text-white shadow-lg shadow-blue-600/25">A</div><div><p className="metric-label">Automated investing</p><h1 className="text-lg font-semibold tracking-tight">Trading dashboard</h1></div></div><div className="flex items-center gap-2"><span className={`hidden rounded-full px-3 py-1.5 text-xs font-semibold sm:inline ${isPaper ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300" : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"}`}>{isPaper ? "Paper mode" : "Live mode"}</span><button onClick={() => setDark(!dark)} className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:text-blue-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300" aria-label="Toggle colour theme">{dark ? "☀" : "◐"}</button><button onClick={() => setSettingsOpen(true)} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700">Settings</button></div></header>
      {error && <div className="mt-3 shrink-0 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</div>}
      <section className="mt-5 grid shrink-0 grid-cols-2 gap-3 lg:grid-cols-4"><Metric label="Portfolio value" value={account ? money.format(account.equity) : "—"} /><Metric label="Buying power" value={account ? money.format(account.buying_power) : "—"} /><Metric label="Today" value={account ? `${dailyPnl >= 0 ? "+" : ""}${money.format(dailyPnl)}` : "—"} positive={dailyPnl >= 0} /><Metric label="Open positions" value={String(snapshot.positions.length)} /></section>
      <section className="mt-4 grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[210px_minmax(0,1fr)_300px]">
        <aside className="panel hidden min-h-0 flex-col p-4 lg:flex"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Watchlist</h2><span className="text-xs text-slate-400">{configuration?.symbols.length || 0}</span></div><div className="mt-4 space-y-1 overflow-y-auto">{configuration?.symbols.map((symbol) => <button key={symbol} onClick={() => setSelectedSymbol(symbol)} className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm font-medium transition ${symbol === selectedSymbol ? "bg-blue-600 text-white shadow-md shadow-blue-600/20" : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"}`}><span>{symbol}</span><span className={`h-1.5 w-1.5 rounded-full ${symbol === selectedSymbol ? "bg-white" : "bg-blue-500"}`} /></button>)}</div><div className="mt-auto rounded-xl bg-blue-50 p-3 dark:bg-blue-950/40"><p className="text-xs font-semibold text-blue-700 dark:text-blue-300">{configuration?.monitoring_enabled ? "Monitoring active" : "Monitoring paused"}</p><p className="mt-1 text-[11px] leading-4 text-blue-600/80 dark:text-blue-300/70">{snapshot.status?.pipeline_running ? "Live worker connected" : "Worker waiting"}</p></div></aside>
        <section className="panel flex min-h-0 flex-col p-5"><div className="flex items-start justify-between"><div><p className="metric-label">Market overview</p><div className="mt-1 flex items-baseline gap-3"><h2 className="text-2xl font-semibold tracking-tight">{selectedSymbol || "Select a symbol"}</h2>{marketSummary && <><span className="text-lg font-semibold">${marketSummary.close.toFixed(2)}</span><span className={`text-xs font-semibold ${marketSummary.change >= 0 ? "text-emerald-600" : "text-red-500"}`}>{marketSummary.change >= 0 ? "+" : ""}${marketSummary.change.toFixed(2)} ({marketSummary.changePercent.toFixed(2)}%)</span></>}</div></div><div className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-300">{configuration?.strategy.interval || "—"}</div></div><div className="mt-3 flex items-center justify-between gap-3"><div className="flex gap-3 overflow-hidden">{marketSummary ? <><OhlcValue label="O" value={marketSummary.open} /><OhlcValue label="H" value={marketSummary.high} /><OhlcValue label="L" value={marketSummary.low} /><OhlcValue label="C" value={marketSummary.close} /></> : <span className="text-xs text-slate-400">OHLC values appear when data is available.</span>}</div><div className="flex shrink-0 rounded-lg bg-slate-50 p-1 dark:bg-slate-800">{["1D", "1W", "1M", "1Y", "MAX"].map((range) => <button key={range} onClick={() => setChartRange(range)} className={`rounded-md px-2 py-1 text-[10px] font-semibold transition ${chartRange === range ? "bg-white text-blue-600 shadow-sm dark:bg-slate-700 dark:text-blue-300" : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"}`}>{range}</button>)}</div></div><div className="mt-2 min-h-0 flex-1"><PriceChart candles={candles} /></div><div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-800"><span>{chartRange} performance</span><span>{candles.length ? `${candles.length} candles` : "No saved candles"}</span></div></section>
        <aside className="panel min-h-0 p-5"><div className="flex items-center justify-between"><div><p className="metric-label">Strategy</p><h2 className="mt-1 text-sm font-semibold">EMA crossover</h2></div><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${configuration?.place_orders_automatically ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300"}`}>{configuration?.place_orders_automatically ? "Auto on" : "Signals only"}</span></div><div className="mt-4 space-y-2 overflow-y-auto">{snapshot.signals.slice(0, 4).map((signal) => <div key={`${signal.symbol}-${signal.timestamp}`} className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"><div className="flex items-center justify-between"><span className="text-sm font-semibold">{signal.symbol}</span><span className="text-xs font-semibold text-blue-600 dark:text-blue-400">{signal.direction}</span></div><p className="mt-1 truncate text-xs text-slate-400">{signal.reason}</p></div>)}{!snapshot.signals.length && <div className="rounded-xl bg-slate-50 p-4 text-sm leading-5 text-slate-400 dark:bg-slate-800/60">No decisions yet. Signals appear here after completed candles are evaluated.</div>}</div></aside>
      </section>
      <section className="mt-4 grid shrink-0 grid-cols-1 gap-4 lg:grid-cols-2"><div className="panel p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Positions</h2><span className="text-xs text-slate-400">Broker snapshot</span></div><DataRows rows={snapshot.positions.slice(0, 2)} empty="No open positions" render={(position) => <><span className="font-semibold">{position.symbol}</span><span>{quantity.format(position.quantity)} shares</span><span className={Number(position.unrealized_pnl) >= 0 ? "text-emerald-600" : "text-red-500"}>{money.format(position.unrealized_pnl)}</span></>} /></div><div className="panel p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Activity</h2><span className="text-xs text-slate-400">Recent orders</span></div><DataRows rows={snapshot.orders.slice(0, 2)} empty="No orders recorded" render={(order) => <><span className="font-semibold">{order.symbol}</span><span>{String(order.side).toUpperCase()} · {quantity.format(order.quantity)}</span><span className="capitalize text-slate-500">{order.status.replaceAll("_", " ")}</span></>} /></div></section>
    </main>
    {settingsOpen && <SettingsDrawer configuration={{ ...configuration, symbols: configuration.symbols.join(", ") }} onClose={() => setSettingsOpen(false)} onSave={save} error={error} />}
  </div>;
}

function Metric({ label, value, positive }) { return <article className="panel flex items-center justify-between p-4"><div><p className="metric-label">{label}</p><p className={`mt-1 text-xl font-semibold tracking-tight ${positive === false ? "text-red-500" : positive ? "text-emerald-600" : ""}`}>{value}</p></div>{label === "Today" && <Sparkline positive={positive} />}</article>; }
function DataRows({ rows, empty, render }) { return <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">{rows.length ? rows.map((row) => <div key={row.symbol} className="grid grid-cols-3 gap-2 py-2.5 text-xs text-slate-500 dark:text-slate-400">{render(row)}</div>) : <p className="py-3 text-sm text-slate-400">{empty}</p>}</div>; }

createRoot(document.getElementById("root")).render(<App />);
