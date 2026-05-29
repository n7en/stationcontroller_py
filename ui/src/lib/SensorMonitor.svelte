<script>
  import { onMount, onDestroy } from 'svelte'
  import { sensors, labels } from '../stores/ws.js'
  import LineChart from './LineChart.svelte'
  import { formatUnit } from './utils.js'

  /** Display label shown above the cards */
  export let title  = 'Sensors'
  /** (name: string, info: {value, unit, ts}) => boolean */
  export let detect = (_name, _info) => false

  const RANGES = [
    { label: '15m', secs: 900    },
    { label: '30m', secs: 1_800  },
    { label: '1H',  secs: 3_600  },
    { label: '2H',  secs: 7_200  },
    { label: '6H',  secs: 21_600 },
  ]

  const COLORS = [
    'var(--accent)',
    'var(--green)',
    '#f0a030',
    '#c792ea',
    '#3ecfcf',
    'var(--red)',
  ]

  const MAX_SECS = 6 * 3600

  let rangeSecs = 900
  let history   = {}
  let loaded    = new Set()
  let now       = Date.now() / 1000
  let ticker

  $: fromTs = now - rangeSecs

  $: matchedSensors = Object.entries($sensors)
    .filter(([name, info]) => detect(name, info))
    .sort(([a], [b]) => a.localeCompare(b))

  // Append live readings
  let lastTs = {}
  $: {
    const cutoff = Date.now() / 1000 - MAX_SECS
    for (const [name, info] of Object.entries($sensors)) {
      if (!detect(name, info)) continue
      if (info.ts != null && info.ts !== lastTs[name]) {
        lastTs[name] = info.ts
        const arr = (history[name] ?? []).filter(r => r.ts > cutoff)
        history[name] = [...arr, { ts: info.ts, value: info.value }]
        history = { ...history }
        now = Date.now() / 1000
      }
    }
  }

  // Fetch API history for newly detected sensors
  $: {
    for (const [name] of matchedSensors) {
      if (!loaded.has(name)) {
        loaded = new Set([...loaded, name])
        fetchHistory(name)
      }
    }
  }

  async function fetchHistory(name) {
    const since = (Date.now() / 1000 - MAX_SECS).toFixed(0)
    try {
      const res = await fetch(
        `/api/history/sensors?name=${encodeURIComponent(name)}&since=${since}&limit=3000`
      )
      if (res.ok) {
        const data = await res.json()
        const live   = history[name] ?? []
        const merged = [...data, ...live]
        const seen   = new Set()
        history[name] = merged
          .filter(r => { if (seen.has(r.ts)) return false; seen.add(r.ts); return true })
          .sort((a, b) => a.ts - b.ts)
        history = { ...history }
      }
    } catch { /* telemetry may be disabled — live-only is fine */ }
  }

  onMount(() => {
    ticker = setInterval(() => { now = Date.now() / 1000 }, 15_000)
  })
  onDestroy(() => clearInterval(ticker))

  $: colorOf = (name) => {
    const idx = matchedSensors.findIndex(([n]) => n === name)
    return COLORS[idx % COLORS.length]
  }

  function visibleReadings(name) {
    return (history[name] ?? []).filter(r => r.ts >= fromTs)
  }

  function fmtValue(name) {
    const info = $sensors[name]
    if (!info || info.value == null) return '—'
    const v = +info.value
    return Math.abs(v) < 100 ? v.toFixed(2) : v.toFixed(1)
  }
</script>

<div class="sensor-monitor">

  <div class="toolbar">
    <span class="section-lbl">{title}</span>
    <div class="range-btns">
      {#each RANGES as r}
        <button
          class="range-btn"
          class:active={rangeSecs === r.secs}
          on:click={() => rangeSecs = r.secs}
        >{r.label}</button>
      {/each}
    </div>
  </div>

  {#if matchedSensors.length === 0}
    <div class="empty">No {title.toLowerCase()} sensors detected yet.</div>
  {:else}
    <div class="card-grid" style="--cols:{Math.min(matchedSensors.length, 2)}">
      {#each matchedSensors as [name, info] (name)}
        {@const readings = visibleReadings(name)}
        {@const color    = colorOf(name)}
        <div class="card">
          <div class="card-header">
            <span class="card-name">{$labels[name] ?? name}</span>
            <span class="card-value" style="color:{color}">{fmtValue(name)}</span>
            <span class="card-unit">{formatUnit(info.unit ?? '')}</span>
          </div>
          <LineChart
            {readings}
            {fromTs}
            toTs={now}
            {color}
            unit={formatUnit(info.unit ?? '')}
          />
        </div>
      {/each}
    </div>
  {/if}

</div>

<style>
  .sensor-monitor { display: flex; flex-direction: column; gap: 0.6rem; }

  .toolbar { display: flex; align-items: center; gap: 0.75rem; }

  .section-lbl {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .range-btns { display: flex; gap: 0.2rem; }

  .range-btn {
    padding: 0.22rem 0.55rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.75rem;
    transition: all 0.12s;
  }
  .range-btn:hover  { background: var(--border); color: var(--text); }
  .range-btn.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(var(--cols, 2), 1fr);
    gap: 0.6rem;
  }
  @media (max-width: 700px) { .card-grid { grid-template-columns: 1fr; } }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.55rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .card-header {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }

  .card-name {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--text);
    font-family: ui-monospace, monospace;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .card-value {
    font-size: 1.05rem;
    font-weight: 700;
    font-family: ui-monospace, monospace;
    flex-shrink: 0;
  }

  .card-unit {
    font-size: 0.72rem;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .empty {
    color: var(--text-muted);
    font-size: 0.82rem;
    padding: 1.5rem 1rem;
    border: 1px dashed var(--border);
    border-radius: 6px;
    text-align: center;
  }
</style>
