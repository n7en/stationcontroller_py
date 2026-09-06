<script>
  export let readings = []   // [{ts, value}]
  export let fromTs   = 0
  export let toTs     = Date.now() / 1000
  export let color    = 'var(--accent)'
  export let unit     = ''

  const W  = 800
  const H  = 150
  const ML = 52, MR = 14, MT = 10, MB = 28
  const PW = W - ML - MR
  const PH = H - MT - MB

  function niceStep(range, target = 5) {
    if (!range || !isFinite(range)) return 1
    const rough = range / target
    const mag   = Math.pow(10, Math.floor(Math.log10(Math.abs(rough) || 1)))
    const norm  = rough / mag
    return (norm < 1.5 ? 1 : norm < 3.5 ? 2 : norm < 7.5 ? 5 : 10) * mag
  }

  $: vals   = readings.map(r => r.value)
  $: yMin0  = vals.length ? Math.min(...vals) : 0
  $: yMax0  = vals.length ? Math.max(...vals) : 1
  $: yRange = Math.max(yMax0 - yMin0, 0.001)
  $: yPad   = yRange * 0.12

  $: step  = niceStep(yRange + yPad * 2)
  $: yMin  = Math.floor((yMin0 - yPad) / step) * step
  $: yMax  = Math.ceil( (yMax0 + yPad) / step) * step

  $: tRange = Math.max(toTs - fromTs, 1)
  $: xOf  = ts => ML + ((ts - fromTs) / tRange) * PW
  $: yOf  = v  => MT + PH - ((v - yMin) / (yMax - yMin)) * PH

  $: yTicks = (() => {
    const out = []
    for (let v = yMin; v <= yMax + step * 0.001; v += step)
      out.push(+(v.toFixed(10)))
    return out
  })()

  $: pathD = readings.length < 2 ? '' :
    'M ' + readings.map(r => `${xOf(r.ts).toFixed(1)},${yOf(r.value).toFixed(1)}`).join(' L ')

  $: areaD = readings.length < 2 ? '' : (() => {
    const bot = (MT + PH).toFixed(1)
    const pts = readings.map(r => `L ${xOf(r.ts).toFixed(1)},${yOf(r.value).toFixed(1)}`).join(' ')
    return `M ${xOf(readings[0].ts).toFixed(1)},${bot} ${pts} L ${xOf(readings[readings.length-1].ts).toFixed(1)},${bot} Z`
  })()

  function fmtTs(ts) {
    const d = new Date(ts * 1000)
    if (tRange <= 7200)
      return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    if (tRange <= 86400 * 2)
      return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    return d.toLocaleDateString([], {month: 'short', day: 'numeric'})
  }

  $: xTicks = Array.from({length: 6}, (_, i) => ({
    x: xOf(fromTs + (i / 5) * tRange),
    label: fmtTs(fromTs + (i / 5) * tRange),
    i,
  }))

  $: fmtV = v => {
    if (Math.abs(v) >= 100000) return (v / 1000).toFixed(0) + 'k'
    if (Math.abs(v) >= 1000)   return (v / 1000).toFixed(1) + 'k'
    if (step >= 1)             return Math.round(v).toString()
    return v.toFixed(step < 0.1 ? 2 : 1)
  }
</script>

{#if readings.length === 0}
  <div class="empty">No data in range</div>
{:else}
  <svg viewBox="0 0 {W} {H}" class="chart-svg">
    <!-- Y grid -->
    {#each yTicks as v}
      <line x1={ML} y1={yOf(v).toFixed(1)} x2={W - MR} y2={yOf(v).toFixed(1)} class="grid" />
    {/each}
    <!-- X grid -->
    {#each xTicks as t}
      <line x1={t.x.toFixed(1)} y1={MT} x2={t.x.toFixed(1)} y2={MT + PH} class="grid x-grid" />
    {/each}

    <!-- Area fill -->
    {#if areaD}
      <path d={areaD} fill={color} opacity="0.09" />
    {/if}

    <!-- Line -->
    {#if pathD}
      <path d={pathD} fill="none" stroke={color} stroke-width="1.5" stroke-linejoin="round" />
    {/if}

    <!-- Y labels -->
    {#each yTicks as v}
      <text x={ML - 5} y={yOf(v) + 3.5} class="lbl" text-anchor="end">{fmtV(v)}</text>
    {/each}

    <!-- X labels -->
    {#each xTicks as t}
      <text
        x={t.x}
        y={H - 3}
        class="lbl"
        text-anchor={t.i === 0 ? 'start' : t.i === 5 ? 'end' : 'middle'}
      >{t.label}</text>
    {/each}

    <!-- Axis borders -->
    <line x1={ML} y1={MT} x2={ML} y2={MT + PH} class="axis" />
    <line x1={ML} y1={MT + PH} x2={W - MR} y2={MT + PH} class="axis" />

    {#if unit}
      <text x={ML + 5} y={MT + 11} class="unit-lbl">{unit}</text>
    {/if}
  </svg>
{/if}

<style>
  .chart-svg { width: 100%; height: auto; display: block; }
  .empty     { color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 2rem 0; }
  .grid      { stroke: var(--border); stroke-width: 0.5; }
  .x-grid    { opacity: 0.5; }
  .axis      { stroke: var(--border); stroke-width: 1; }
  .lbl       { font-size: 10px; fill: var(--text-muted); font-family: ui-monospace, monospace; }
  .unit-lbl  { font-size: 9px; fill: var(--text-muted); font-style: italic; }
</style>
