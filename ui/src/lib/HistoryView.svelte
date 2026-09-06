<script>
  import { onMount } from 'svelte'
  import LineChart   from './LineChart.svelte'
  import TimelineBar from './TimelineBar.svelte'
  import { formatUnit } from './utils.js'

  const RANGES = [
    { label: '1H',  secs: 3_600    },
    { label: '6H',  secs: 21_600   },
    { label: '24H', secs: 86_400   },
    { label: '7D',  secs: 604_800  },
    { label: '30D', secs: 2_592_000 },
  ]

  const LINE_COLORS = [
    'var(--accent)',
    'var(--green)',
    '#f0a030',
    '#c792ea',
    '#3ecfcf',
    'var(--red)',
  ]

  let rangeSecs  = 3_600
  let sensors    = {}           // {name: {value, unit, source}}
  let selected   = []           // ordered list of active sensor names
  let histData   = {}           // {name: [{ts, value, unit}]}
  let loading    = new Set()
  let toTs       = Date.now() / 1000

  $: fromTs = toTs - rangeSecs

  onMount(loadSensors)

  async function loadSensors() {
    const res = await fetch('/api/sensors')
    if (res.ok) sensors = await res.json()
  }

  async function fetchHistory(name) {
    loading = new Set([...loading, name])
    try {
      const url = `/api/history/sensors?name=${encodeURIComponent(name)}&since=${fromTs.toFixed(3)}&limit=3000`
      const res = await fetch(url)
      if (res.ok) histData = { ...histData, [name]: await res.json() }
    } finally {
      loading = new Set([...loading].filter(n => n !== name))
    }
  }

  async function toggleSensor(name) {
    if (selected.includes(name)) {
      selected = selected.filter(n => n !== name)
    } else {
      selected = [...selected, name]
      if (!histData[name]) await fetchHistory(name)
    }
  }

  async function setRange(secs) {
    rangeSecs = secs
    toTs      = Date.now() / 1000
    await Promise.all(selected.map(fetchHistory))
  }

  async function refresh() {
    toTs = Date.now() / 1000
    await Promise.all(selected.map(fetchHistory))
  }

  // Group sensors by device type extracted from their source field
  $: groups = (() => {
    const g = {}
    for (const [name, info] of Object.entries(sensors)) {
      const src   = (info.source ?? '').split(':')
      const type  = src[0] || name.split('_')[0] || 'other'
      const inst  = src[1]
      const label = inst ? `${type} · ${inst}` : type
      if (!g[label]) g[label] = []
      g[label].push({ name, unit: info.unit ?? '' })
    }
    return Object.fromEntries(
      Object.entries(g)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, v.sort((a, b) => a.name.localeCompare(b.name))])
    )
  })()

  // Assign a stable color per selected sensor
  $: colorFor = name => LINE_COLORS[selected.indexOf(name) % LINE_COLORS.length]

  // Auto-detect chart type: timeline if all values are integers and ≤10 distinct values
  function chartType(data) {
    if (!data?.length) return 'line'
    const vals   = data.map(r => r.value)
    const allInt = vals.every(v => v % 1 === 0)
    const unique = new Set(vals)
    return allInt && unique.size <= 10 ? 'timeline' : 'line'
  }
</script>

<div class="history">

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="range-btns">
      {#each RANGES as r}
        <button
          class="range-btn"
          class:active={rangeSecs === r.secs}
          on:click={() => setRange(r.secs)}
        >{r.label}</button>
      {/each}
    </div>
    <button class="refresh-btn" on:click={refresh} title="Refresh">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
           stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
        <path d="M23 4v6h-6M1 20v-6h6"/>
        <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
      </svg>
      Refresh
    </button>
  </div>

  <!-- Sensor picker -->
  <div class="picker">
    {#each Object.entries(groups) as [group, items]}
      <div class="group">
        <span class="group-label">{group}</span>
        <div class="chips">
          {#each items as s}
            <button
              class="chip"
              class:active={selected.includes(s.name)}
              on:click={() => toggleSensor(s.name)}
            >
              {s.name}{#if s.unit}&nbsp;<span class="chip-unit">{formatUnit(s.unit)}</span>{/if}
            </button>
          {/each}
        </div>
      </div>
    {/each}
  </div>

  <!-- Charts area -->
  {#if selected.length === 0}
    <div class="hint">Select sensors above to view their history.</div>
  {:else}
    <div class="charts">
      {#each selected as name}
        {@const type = chartType(histData[name])}
        <div class="chart-card">
          <div class="chart-header">
            <span class="chart-name">{name}</span>
            {#if sensors[name]?.unit}
              <span class="chart-unit">{formatUnit(sensors[name].unit)}</span>
            {/if}
            <span class="chart-type-badge">{type}</span>
            {#if loading.has(name)}
              <span class="loading-txt">loading…</span>
            {/if}
          </div>

          {#if histData[name] !== undefined}
            {#if type === 'timeline'}
              <TimelineBar readings={histData[name]} {fromTs} {toTs} />
            {:else}
              <LineChart
                readings={histData[name]}
                {fromTs}
                {toTs}
                color={colorFor(name)}
                unit={formatUnit(sensors[name]?.unit ?? '')}
              />
            {/if}
          {:else if !loading.has(name)}
            <div class="no-data">No data</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

</div>

<style>
  .history { display: flex; flex-direction: column; gap: 0.75rem; }

  /* ── Toolbar ── */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .range-btns { display: flex; gap: 0.2rem; }
  .range-btn {
    padding: 0.28rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.12s;
  }
  .range-btn:hover  { background: var(--border); color: var(--text); }
  .range-btn.active {
    background: var(--accent-dim);
    color: var(--accent);
    border-color: var(--accent);
  }
  .refresh-btn {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.28rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.8rem;
    margin-left: auto;
    transition: all 0.12s;
  }
  .refresh-btn:hover { background: var(--border); color: var(--text); }

  /* ── Sensor picker ── */
  .picker {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.6rem 0.75rem;
    max-height: 200px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .group {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
  }
  .group-label {
    flex-shrink: 0;
    min-width: 130px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    padding-top: 0.22rem;
  }
  .chips { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .chip {
    padding: 0.18rem 0.55rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.73rem;
    font-family: ui-monospace, monospace;
    transition: all 0.1s;
    white-space: nowrap;
  }
  .chip:hover  { background: var(--border); color: var(--text); }
  .chip.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }
  .chip-unit   { font-size: 0.62rem; opacity: 0.65; }

  /* ── Hint ── */
  .hint {
    color: var(--text-muted);
    font-size: 0.85rem;
    text-align: center;
    padding: 2.5rem 1rem;
    border: 1px dashed var(--border);
    border-radius: 6px;
  }

  /* ── Charts ── */
  .charts { display: flex; flex-direction: column; gap: 0.75rem; }
  .chart-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.55rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .chart-header {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
    font-size: 0.78rem;
  }
  .chart-name      { font-weight: 600; color: var(--text); font-family: ui-monospace, monospace; }
  .chart-unit      { color: var(--text-muted); font-size: 0.7rem; }
  .chart-type-badge {
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
    background: var(--border);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .loading-txt { color: var(--text-muted); font-size: 0.7rem; margin-left: auto; }
  .no-data     { color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 1.5rem; }
</style>
