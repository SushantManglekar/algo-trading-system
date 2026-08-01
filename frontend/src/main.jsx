import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const EXCHANGE_TIME_ZONE = "America/New_York";
const VIEW_WIDTH = 640;
const VIEW_HEIGHT = 252;
const PLOT_LEFT = 12;
const PLOT_RIGHT = 550;
const PLOT_TOP = 14;
const PLOT_BOTTOM = 192;
const MAX_DISPLAY_POINTS = 720;
const MAX_LIVE_SERIES_POINTS = 1_200;
const LIVE_POINT_INTERVAL_MS = 150;

const CHART_RANGES = {
  "1D": { days: 1, interval: "1m", tickDriven: true },
  "1W": { days: 7, interval: "5m" },
  "1M": { days: 30, interval: "30m" },
  "3M": { days: 90, interval: "1d" },
  "6M": { days: 182, interval: "1d" },
  "1Y": { days: 365, interval: "1d" },
  "3Y": { days: 1_095, interval: "1d" },
  "5Y": { days: 1_826, interval: "1d" },
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function formatPrice(value, maximumFractionDigits = 2) {
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: maximumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

function pointFromTick(tick) {
  const price = Number(tick.price);
  if (!Number.isFinite(price) || !tick.timestamp) return null;
  return { timestamp: tick.timestamp, price, source: "tick" };
}

function pointFromCandle(candle) {
  const price = Number(candle.close);
  if (!Number.isFinite(price) || !(candle.end_at || candle.start_at)) return null;
  return {
    timestamp: candle.end_at || candle.start_at,
    price,
    source: "candle",
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
  };
}

function normalizePoints(points) {
  return points
    .filter(Boolean)
    .filter((point) => Number.isFinite(point.price) && Number.isFinite(Date.parse(point.timestamp)))
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
}

function samplePoints(points, maximum = MAX_DISPLAY_POINTS) {
  if (points.length <= maximum) return points;
  const step = (points.length - 1) / (maximum - 1);
  return Array.from({ length: maximum }, (_, index) => points[Math.round(index * step)]);
}

function capLiveSeries(points) {
  if (points.length <= MAX_LIVE_SERIES_POINTS) return points;
  return samplePoints(points, MAX_DISPLAY_POINTS);
}

function mergeLivePoint(points, incoming) {
  const last = points.at(-1);
  if (!last) return [incoming];
  const incomingTime = Date.parse(incoming.timestamp);
  const lastTime = Date.parse(last.timestamp);
  if (incomingTime < lastTime) return points;
  if (incomingTime - lastTime <= LIVE_POINT_INTERVAL_MS) {
    return [...points.slice(0, -1), incoming];
  }
  return capLiveSeries([...points, incoming]);
}

async function loadChartSeries(symbol, range, start, end, signal) {
  const configuration = CHART_RANGES[range];
  const parameters = `start_at=${encodeURIComponent(start.toISOString())}&end_at=${encodeURIComponent(end.toISOString())}`;
  if (configuration.tickDriven) {
    const ticks = await request(`/market/ticks/${symbol}?${parameters}&max_points=${MAX_DISPLAY_POINTS}`, { signal });
    const points = normalizePoints(ticks.map(pointFromTick));
    if (points.length >= 2) return { points, source: "ticks" };
  }
  const candles = await request(`/market/candles/${symbol}?interval=${configuration.interval}&${parameters}`, { signal });
  return { points: normalizePoints(candles.map(pointFromCandle)), source: "candles" };
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: EXCHANGE_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function formatAxisTimestamp(timestamp, range) {
  if (range === "1D") return formatTime(timestamp);
  const options = range === "1W"
    ? { weekday: "short", day: "numeric" }
    : range === "1M" || range === "3M" || range === "6M"
      ? { month: "short", day: "numeric" }
      : { month: "short", year: "2-digit" };
  return new Intl.DateTimeFormat("en-US", { timeZone: EXCHANGE_TIME_ZONE, ...options }).format(new Date(timestamp));
}

function formatHoverTimestamp(timestamp, range) {
  const date = new Date(timestamp);
  const time = new Intl.DateTimeFormat("en-US", {
    timeZone: EXCHANGE_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  if (range === "1D") return `${time} ET`;
  const dateText = new Intl.DateTimeFormat("en-US", {
    timeZone: EXCHANGE_TIME_ZONE,
    weekday: range === "1W" ? "short" : undefined,
    month: "short",
    day: "numeric",
    year: range === "1Y" || range === "3Y" || range === "5Y" ? "numeric" : undefined,
  }).format(date);
  return range === "1W" ? `${dateText} · ${time} ET` : dateText;
}

function buildLinePath(points) {
  if (!points.length) return "";
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

function nearestIndexByTimestamp(points, target) {
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (Date.parse(points[middle].timestamp) < target) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return low;
  const previous = low - 1;
  return Math.abs(Date.parse(points[low].timestamp) - target) < Math.abs(Date.parse(points[previous].timestamp) - target) ? low : previous;
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

function PriceChart({ points, range, transitionKey, loading, live, source }) {
  const gradientId = useId().replaceAll(":", "");
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const hoverFrame = useRef(null);
  const targetHoverIndex = useRef(null);
  const domainRef = useRef(null);
  const data = useMemo(() => samplePoints(points), [points]);

  useEffect(() => {
    targetHoverIndex.current = null;
    setHoveredIndex(null);
  }, [transitionKey]);
  useEffect(() => () => {
    if (hoverFrame.current !== null) cancelAnimationFrame(hoverFrame.current);
  }, []);

  const chart = useMemo(() => {
    if (!data.length) return { points: [], domain: { low: 0, high: 1 }, upward: true, first: null, latest: null };
    const prices = data.map((point) => point.price);
    const minimum = Math.min(...prices);
    const maximum = Math.max(...prices);
    const rawRange = Math.max(maximum - minimum, Math.abs(maximum) * 0.002, 0.01);
    const padded = { low: minimum - rawRange * 0.15, high: maximum + rawRange * 0.15 };
    const prior = domainRef.current;
    const shouldResetDomain = !prior || prior.transitionKey !== transitionKey;
    const domain = shouldResetDomain
      ? padded
      : {
          low: padded.low < prior.low ? padded.low : prior.low,
          high: padded.high > prior.high ? padded.high : prior.high,
        };
    domainRef.current = { ...domain, transitionKey };
    const firstTime = Date.parse(data[0].timestamp);
    const lastTime = Math.max(Date.parse(data.at(-1).timestamp), firstTime + 1);
    const verticalRange = Math.max(domain.high - domain.low, 0.01);
    return {
      points: data.map((point) => ({
        ...point,
        x: PLOT_LEFT + ((Date.parse(point.timestamp) - firstTime) / (lastTime - firstTime)) * (PLOT_RIGHT - PLOT_LEFT),
        y: PLOT_BOTTOM - ((point.price - domain.low) / verticalRange) * (PLOT_BOTTOM - PLOT_TOP),
      })),
      domain,
      upward: data.at(-1).price >= data[0].price,
      first: data[0],
      latest: data.at(-1),
      firstTime,
      lastTime,
    };
  }, [data, transitionKey]);

  const linePath = useMemo(() => buildLinePath(chart.points), [chart.points]);
  const areaPath = useMemo(() => linePath ? `${linePath} L ${PLOT_RIGHT} ${PLOT_BOTTOM} L ${PLOT_LEFT} ${PLOT_BOTTOM} Z` : "", [linePath]);
  const hovered = hoveredIndex === null ? null : chart.points[hoveredIndex];
  const activePoint = hovered || chart.latest;
  const color = chart.upward ? "#20d6a3" : "#fb5a62";
  const priceLabels = Array.from({ length: 4 }, (_, index) => chart.domain.high - ((chart.domain.high - chart.domain.low) * index) / 3);
  const axisPoints = chart.points.length ? [chart.points[0], chart.points[Math.floor(chart.points.length / 2)], chart.points.at(-1)] : [];

  const selectPoint = (event) => {
    if (!chart.points.length) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - bounds.left) / bounds.width) * VIEW_WIDTH;
    const clampedX = Math.max(PLOT_LEFT, Math.min(PLOT_RIGHT, viewX));
    const targetTime = chart.firstTime + ((clampedX - PLOT_LEFT) / (PLOT_RIGHT - PLOT_LEFT)) * (chart.lastTime - chart.firstTime);
    const nextIndex = nearestIndexByTimestamp(chart.points, targetTime);
    if (targetHoverIndex.current === nextIndex) return;
    targetHoverIndex.current = nextIndex;
    if (hoverFrame.current !== null) return;
    hoverFrame.current = requestAnimationFrame(() => {
      hoverFrame.current = null;
      setHoveredIndex(targetHoverIndex.current);
    });
  };
  const clearHover = () => {
    targetHoverIndex.current = null;
    if (hoverFrame.current !== null) cancelAnimationFrame(hoverFrame.current);
    hoverFrame.current = null;
    setHoveredIndex(null);
  };

  return <div className="flex min-h-0 flex-1 flex-col rounded-2xl bg-[#20242a] p-3 text-white shadow-inner">
    <div className="mb-2 flex min-h-11 items-center justify-between gap-3 px-1">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">{hovered ? "Selected point" : "Latest price"}</p>
        <div className="mt-0.5 flex items-baseline gap-2"><span className="text-xl font-semibold tracking-tight">{activePoint ? formatPrice(activePoint.price) : "-"}</span>{activePoint && <span className="text-xs text-slate-400">{formatHoverTimestamp(activePoint.timestamp, range)}</span>}</div>
      </div>
      <div className="flex items-center gap-2 text-[11px] font-medium text-slate-400"><i className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.9)]" : "bg-slate-600"}`} />{loading ? "Updating" : source === "ticks" ? "Tick detail" : "Live price"}</div>
    </div>
    <div className="relative min-h-[128px] flex-1">
      {!chart.points.length && <div className="grid h-full place-items-center text-sm text-slate-400">Historical prices will appear here.</div>}
      {!!chart.points.length && <svg className="h-full w-full cursor-crosshair touch-none" viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none" role="img" aria-label={`Interactive ${range} historical price chart`} onPointerMove={selectPoint} onPointerLeave={clearHover}>
        <defs>
          <linearGradient id={`price-fill-${gradientId}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.15" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient>
          <filter id={`price-glow-${gradientId}`} x="-10%" y="-20%" width="120%" height="140%"><feGaussianBlur stdDeviation="1.5" /></filter>
        </defs>
        <g className="chart-layer-enter" key={transitionKey}>
          {priceLabels.map((price) => <line key={price} x1={PLOT_LEFT} y1={PLOT_TOP + ((chart.domain.high - price) / (chart.domain.high - chart.domain.low)) * (PLOT_BOTTOM - PLOT_TOP)} x2={PLOT_RIGHT} y2={PLOT_TOP + ((chart.domain.high - price) / (chart.domain.high - chart.domain.low)) * (PLOT_BOTTOM - PLOT_TOP)} stroke="white" strokeOpacity="0.055" />)}
          <path d={areaPath} fill={`url(#price-fill-${gradientId})`} />
          <path d={linePath} fill="none" stroke={color} strokeOpacity="0.2" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" filter={`url(#price-glow-${gradientId})`} />
          <path d={linePath} fill="none" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          <circle cx={chart.latest.x} cy={chart.latest.y} r="3.4" fill={color} stroke="#20242a" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
          {hovered && <><line x1={hovered.x} y1={PLOT_TOP} x2={hovered.x} y2={PLOT_BOTTOM} stroke="white" strokeOpacity="0.26" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" /><line x1={PLOT_LEFT} y1={hovered.y} x2={PLOT_RIGHT} y2={hovered.y} stroke={color} strokeOpacity="0.26" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" /><circle cx={hovered.x} cy={hovered.y} r="3.8" fill="#20242a" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" /><rect x={PLOT_RIGHT + 8} y={Math.max(PLOT_TOP, Math.min(PLOT_BOTTOM - 16, hovered.y - 8))} width="72" height="16" rx="4" fill={color} /><text x={PLOT_RIGHT + 44} y={Math.max(PLOT_TOP + 11, Math.min(PLOT_BOTTOM - 5, hovered.y + 3))} fill="#10231e" textAnchor="middle" fontSize="8" fontWeight="700">{formatPrice(hovered.price)}</text></>}
        </g>
        {priceLabels.map((price) => <text key={`label-${price}`} x={PLOT_RIGHT + 10} y={PLOT_TOP + ((chart.domain.high - price) / (chart.domain.high - chart.domain.low)) * (PLOT_BOTTOM - PLOT_TOP) + 3} fill="white" fillOpacity="0.83" fontSize="10">{formatPrice(price)}</text>)}
        {axisPoints.map((point, index) => <text key={`${point.timestamp}-${index}`} x={point.x} y={224} fill="white" fillOpacity="0.78" fontSize="10" textAnchor={index === 0 ? "start" : index === axisPoints.length - 1 ? "end" : "middle"}>{formatAxisTimestamp(point.timestamp, range)}</text>)}
      </svg>}
    </div>
  </div>;
}

function OhlcValue({ label, value }) {
  return <span className="whitespace-nowrap text-[11px] text-slate-400">{label} <b className="ml-1 font-semibold text-slate-700 dark:text-slate-200">{formatPrice(value)}</b></span>;
}

function Watchlist({ symbols, selectedSymbol, onSelect, onAdd, monitoringEnabled, pipelineRunning }) {
  const [symbol, setSymbol] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    const candidate = symbol.trim().toUpperCase();
    if (!candidate) return;
    if (await onAdd(candidate)) setSymbol("");
  };
  return <aside className="panel hidden min-h-0 flex-col p-4 lg:flex"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Watchlist</h2><span className="text-xs text-slate-400">{symbols.length}</span></div><form onSubmit={submit} className="mt-3 flex gap-2"><input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs font-medium uppercase outline-none transition placeholder:normal-case focus:border-blue-500 focus:ring-2 focus:ring-blue-100 dark:border-slate-700 dark:bg-slate-950 dark:focus:ring-blue-950" placeholder="Add ticker" aria-label="Add stock ticker" /><button className="rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white transition hover:bg-blue-700" type="submit">Add</button></form><div className="mt-3 space-y-1 overflow-y-auto">{symbols.map((ticker) => <button key={ticker} onClick={() => onSelect(ticker)} className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm font-medium transition ${ticker === selectedSymbol ? "bg-blue-600 text-white shadow-md shadow-blue-600/20" : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"}`}><span>{ticker}</span><span className={`h-1.5 w-1.5 rounded-full ${ticker === selectedSymbol ? "bg-white" : "bg-blue-500"}`} /></button>)}{!symbols.length && <p className="px-1 py-3 text-xs leading-5 text-slate-400">Type a US ticker above to start a watchlist.</p>}</div><div className="mt-auto rounded-xl bg-blue-50 p-3 dark:bg-blue-950/40"><p className="text-xs font-semibold text-blue-700 dark:text-blue-300">{monitoringEnabled ? "Monitoring active" : "Monitoring paused"}</p><p className="mt-1 text-[11px] leading-4 text-blue-600/80 dark:text-blue-300/70">{pipelineRunning ? "Live worker connected" : "Worker waiting"}</p></div></aside>;
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
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5 dark:border-slate-800"><div><p className="metric-label">Control plane</p><h2 className="mt-1 text-lg font-semibold">Trading settings</h2></div><button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full text-xl text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Close settings">x</button></div>
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
  const [series, setSeries] = useState([]);
  const [chartRange, setChartRange] = useState("1D");
  const [chartSource, setChartSource] = useState("candles");
  const [chartLive, setChartLive] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartTransitionKey, setChartTransitionKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem("dashboard-theme") === "dark");
  const [error, setError] = useState("");
  const chartCache = useRef(new Map());
  const seriesRef = useRef([]);
  const activeChartRef = useRef({ symbol: null, range: null, cacheKey: null, source: "candles" });
  const pendingTick = useRef(null);
  const tickFlushTimer = useRef(null);
  const rangeConfiguration = CHART_RANGES[chartRange];

  const refresh = async () => {
    try {
      const [control, status, account, positions, orders, signals] = await Promise.all([request("/control"), request("/trading/status"), request("/trading/account"), request("/trading/positions"), request("/trading/orders"), request("/signals")]);
      setConfiguration(control);
      setSnapshot({ status, account, positions, orders, signals });
      setSelectedSymbol((current) => control.symbols.includes(current) ? current : control.symbols[0] || null);
      setError("");
    } catch (reason) { setError(reason.message); }
  };

  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 30000); return () => window.clearInterval(timer); }, []);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("dashboard-theme", dark ? "dark" : "light"); }, [dark]);

  useEffect(() => {
    if (!selectedSymbol) {
      seriesRef.current = [];
      activeChartRef.current = { symbol: null, range: null, cacheKey: null, source: "candles" };
      setSeries([]);
      setChartLoading(false);
      return undefined;
    }
    const end = new Date();
    const start = new Date(end.getTime() - rangeConfiguration.days * 86_400_000);
    const cacheKey = `${selectedSymbol}:${chartRange}`;
    const controller = new AbortController();
    const applySeries = (result) => {
      const next = normalizePoints(result.points);
      seriesRef.current = next;
      activeChartRef.current = { symbol: selectedSymbol, range: chartRange, cacheKey, source: result.source };
      chartCache.current.set(cacheKey, { points: next, source: result.source });
      setSeries(next);
      setChartSource(result.source);
      setChartTransitionKey((current) => current + 1);
    };
    const cached = chartCache.current.get(cacheKey);
    if (cached) applySeries(cached);
    setChartLoading(!cached);
    loadChartSeries(selectedSymbol, chartRange, start, end, controller.signal)
      .then((result) => { if (!controller.signal.aborted) applySeries(result); })
      .catch((reason) => {
        if (reason.name !== "AbortError" && !cached) {
          seriesRef.current = [];
          setSeries([]);
          setError(`Could not load ${selectedSymbol} chart: ${reason.message}`);
        }
      })
      .finally(() => { if (!controller.signal.aborted) setChartLoading(false); });
    return () => controller.abort();
  }, [selectedSymbol, chartRange, rangeConfiguration.days]);

  useEffect(() => {
    if (!selectedSymbol) { setChartLive(false); return undefined; }
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${window.location.host}/ws/ticks`);
    let active = true;
    const flushTick = () => {
      tickFlushTimer.current = null;
      const incoming = pendingTick.current;
      pendingTick.current = null;
      const context = activeChartRef.current;
      if (!active || !incoming || context.symbol !== selectedSymbol || !context.cacheKey) return;
      const next = mergeLivePoint(seriesRef.current, incoming);
      seriesRef.current = next;
      chartCache.current.set(context.cacheKey, { points: next, source: context.source });
      setSeries(next);
    };
    socket.onopen = () => { if (active) setChartLive(true); };
    socket.onclose = () => { if (active) setChartLive(false); };
    socket.onerror = () => { if (active) setChartLive(false); };
    socket.onmessage = ({ data }) => {
      try {
        const message = JSON.parse(data);
        if (message.event !== "tick" || message.data?.symbol !== selectedSymbol) return;
        const incoming = pointFromTick(message.data);
        if (!incoming) return;
        pendingTick.current = incoming;
        if (tickFlushTimer.current === null) tickFlushTimer.current = window.setTimeout(flushTick, LIVE_POINT_INTERVAL_MS);
      } catch { if (active) setChartLive(false); }
    };
    return () => {
      active = false;
      socket.close();
      if (tickFlushTimer.current !== null) window.clearTimeout(tickFlushTimer.current);
      tickFlushTimer.current = null;
      pendingTick.current = null;
    };
  }, [selectedSymbol]);

  const save = async (payload, preferredSymbol = null, closeSettings = true) => {
    try {
      const next = await request("/control", { method: "PUT", body: JSON.stringify(payload) });
      setConfiguration(next);
      setSelectedSymbol((current) => preferredSymbol && next.symbols.includes(preferredSymbol) ? preferredSymbol : next.symbols.includes(current) ? current : next.symbols[0] || null);
      if (closeSettings) setSettingsOpen(false);
      setError("");
      await refresh();
      return true;
    } catch (reason) {
      setError(reason.message);
      return false;
    }
  };
  const addToWatchlist = async (symbol) => {
    if (!configuration) { setError("The control configuration is still loading. Please try again."); return false; }
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol)) { setError("Enter a valid US stock ticker, for example AAPL or MSFT."); return false; }
    if (configuration.symbols.includes(symbol)) { setSelectedSymbol(symbol); setError(""); return true; }
    return save({ mode: configuration.mode, place_orders_automatically: configuration.place_orders_automatically, monitoring_enabled: configuration.monitoring_enabled, symbols: [...configuration.symbols, symbol], strategy: configuration.strategy, risk_policy: configuration.risk_policy, expected_version: configuration.version }, symbol, false);
  };

  const account = snapshot.account;
  const dailyPnl = account ? Number(account.equity) - Number(account.previous_close_equity || account.equity) : 0;
  const isPaper = configuration?.mode !== "live";
  const marketSummary = useMemo(() => {
    if (!series.length) return null;
    const prices = series.map((point) => point.price);
    const first = series[0];
    const latest = series.at(-1);
    const close = latest.price;
    const change = close - first.price;
    return { open: first.price, close, high: Math.max(...prices), low: Math.min(...prices), change, changePercent: first.price ? (change / first.price) * 100 : 0 };
  }, [series]);

  return <div className="h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
    <main className="mx-auto flex h-full max-w-[1600px] flex-col px-5 py-5 lg:px-8">
      <header className="flex shrink-0 items-center justify-between gap-4"><div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-bold text-white shadow-lg shadow-blue-600/25">A</div><div><p className="metric-label">Automated investing</p><h1 className="text-lg font-semibold tracking-tight">Trading dashboard</h1></div></div><div className="flex items-center gap-2"><span className={`hidden rounded-full px-3 py-1.5 text-xs font-semibold sm:inline ${isPaper ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300" : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"}`}>{isPaper ? "Paper mode" : "Live mode"}</span><button onClick={() => setDark(!dark)} className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-[10px] font-semibold text-slate-500 transition hover:text-blue-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300" aria-label="Toggle colour theme">{dark ? "Light" : "Dark"}</button><button onClick={() => setSettingsOpen(true)} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700">Settings</button></div></header>
      {error && <div className="mt-3 shrink-0 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</div>}
      <section className="mt-5 grid shrink-0 grid-cols-2 gap-3 lg:grid-cols-4"><Metric label="Portfolio value" value={account ? money.format(account.equity) : "-"} /><Metric label="Buying power" value={account ? money.format(account.buying_power) : "-"} /><Metric label="Today" value={account ? `${dailyPnl >= 0 ? "+" : ""}${money.format(dailyPnl)}` : "-"} positive={dailyPnl >= 0} /><Metric label="Open positions" value={String(snapshot.positions.length)} /></section>
      <section className="mt-4 grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[210px_minmax(0,1fr)_300px]">
        <Watchlist symbols={configuration?.symbols || []} selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} onAdd={addToWatchlist} monitoringEnabled={configuration?.monitoring_enabled} pipelineRunning={snapshot.status?.pipeline_running} />
        <section className="panel flex min-h-0 flex-col overflow-hidden p-5">
          <div className="flex items-start justify-between gap-4"><div><p className="metric-label">Market overview</p><div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1"><h2 className="text-2xl font-semibold tracking-tight">{selectedSymbol || "Select a symbol"}</h2>{marketSummary && <><span className="text-xl font-semibold">{formatPrice(marketSummary.close)}</span><span className={`text-xs font-semibold ${marketSummary.change >= 0 ? "text-emerald-600" : "text-red-500"}`}>{marketSummary.change >= 0 ? "+" : ""}{formatPrice(marketSummary.change)} ({marketSummary.changePercent.toFixed(2)}%)</span></>}</div></div><div className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-300">{chartRange === "1D" ? "Tick line" : rangeConfiguration.interval}</div></div>
          <div className="mt-3 flex items-center justify-between gap-3"><div className="flex gap-3 overflow-hidden">{marketSummary ? <><OhlcValue label="O" value={marketSummary.open} /><OhlcValue label="H" value={marketSummary.high} /><OhlcValue label="L" value={marketSummary.low} /><OhlcValue label="C" value={marketSummary.close} /></> : <span className="text-xs text-slate-400">Prices appear when data is available.</span>}</div><div className="flex max-w-[70%] shrink-0 gap-0.5 overflow-x-auto rounded-xl bg-slate-50 p-1 dark:bg-slate-800">{Object.keys(CHART_RANGES).map((range) => <button key={range} onClick={() => setChartRange(range)} className={`rounded-lg px-2.5 py-1.5 text-[10px] font-semibold transition ${chartRange === range ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white" : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"}`}>{range}</button>)}</div></div>
          <div className="mt-3 min-h-0 flex-1"><PriceChart points={series} range={chartRange} transitionKey={chartTransitionKey} loading={chartLoading} live={chartLive} source={chartSource} /></div>
          <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-800"><span className="flex items-center gap-1.5"><i className={`h-1.5 w-1.5 rounded-full ${chartLive ? "bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,.8)]" : "bg-slate-300 dark:bg-slate-700"}`} />{chartLive ? "Live ticks connected" : "Connecting live feed"}</span><span>{series.length ? `${series.length} price points` : "No prices yet"}</span></div>
        </section>
        <aside className="panel min-h-0 p-5"><div className="flex items-center justify-between"><div><p className="metric-label">Strategy</p><h2 className="mt-1 text-sm font-semibold">EMA crossover</h2></div><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${configuration?.place_orders_automatically ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300"}`}>{configuration?.place_orders_automatically ? "Auto on" : "Signals only"}</span></div><div className="mt-4 space-y-2 overflow-y-auto">{snapshot.signals.slice(0, 4).map((signal) => <div key={`${signal.symbol}-${signal.timestamp}`} className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"><div className="flex items-center justify-between"><span className="text-sm font-semibold">{signal.symbol}</span><span className="text-xs font-semibold text-blue-600 dark:text-blue-400">{signal.direction}</span></div><p className="mt-1 truncate text-xs text-slate-400">{signal.reason}</p></div>)}{!snapshot.signals.length && <div className="rounded-xl bg-slate-50 p-4 text-sm leading-5 text-slate-400 dark:bg-slate-800/60">No decisions yet. Signals appear here after completed candles are evaluated.</div>}</div></aside>
      </section>
      <section className="mt-4 grid shrink-0 grid-cols-1 gap-4 lg:grid-cols-2"><div className="panel p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Positions</h2><span className="text-xs text-slate-400">Broker snapshot</span></div><DataRows rows={snapshot.positions.slice(0, 2)} empty="No open positions" render={(position) => <><span className="font-semibold">{position.symbol}</span><span>{quantity.format(position.quantity)} shares</span><span className={Number(position.unrealized_pnl) >= 0 ? "text-emerald-600" : "text-red-500"}>{money.format(position.unrealized_pnl)}</span></>} /></div><div className="panel p-4"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Activity</h2><span className="text-xs text-slate-400">Recent orders</span></div><DataRows rows={snapshot.orders.slice(0, 2)} empty="No orders recorded" render={(order) => <><span className="font-semibold">{order.symbol}</span><span>{String(order.side).toUpperCase()} · {quantity.format(order.quantity)}</span><span className="capitalize text-slate-500">{order.status.replaceAll("_", " ")}</span></>} /></div></section>
    </main>
    {settingsOpen && configuration && <SettingsDrawer configuration={{ ...configuration, symbols: configuration.symbols.join(", ") }} onClose={() => setSettingsOpen(false)} onSave={save} error={error} />}
  </div>;
}

function Metric({ label, value, positive }) { return <article className="panel flex items-center justify-between p-4"><div><p className="metric-label">{label}</p><p className={`mt-1 text-xl font-semibold tracking-tight ${positive === false ? "text-red-500" : positive ? "text-emerald-600" : ""}`}>{value}</p></div>{label === "Today" && <Sparkline positive={positive} />}</article>; }
function DataRows({ rows, empty, render }) { return <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">{rows.length ? rows.map((row) => <div key={row.symbol} className="grid grid-cols-3 gap-2 py-2.5 text-xs text-slate-500 dark:text-slate-400">{render(row)}</div>) : <p className="py-3 text-sm text-slate-400">{empty}</p>}</div>; }

createRoot(document.getElementById("root")).render(<App />);
