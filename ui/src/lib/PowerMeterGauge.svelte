<script>
  export let value  = 0
  export let max    = 1500
  export let color  = '#4e9af1'
  export let title  = ''
  export let unit   = 'W'

  const R       = 50
  const SW      = 10
  const TICK_R  = R - SW / 2 - 2   // 43 — just inside the arc inner edge

  const arcTicks = Array.from({ length: 21 }, (_, i) => {
    const p     = i / 20
    const isMaj = i % 5 === 0
    const angle = Math.PI * (1 - p)
    const ca    = Math.cos(angle)
    const sa    = Math.sin(angle)
    const ro    = TICK_R
    const ri    = isMaj ? ro - 5 : ro - 2.5
    return {
      x1: +(ro * ca).toFixed(2), y1: +(-ro * sa).toFixed(2),
      x2: +(ri * ca).toFixed(2), y2: +(-ri * sa).toFixed(2),
      isMaj,
    }
  })

  $: pct   = Math.min(Math.max(value / max, 0), 1)
  $: endX  = +(R * Math.cos(Math.PI * (1 - pct))).toFixed(3)
  $: endY  = +(-R * Math.sin(Math.PI * (1 - pct))).toFixed(3)
  // CW arc (sweep=1) — curves through the top of the SVG; partial arcs always < 180° so large-arc=0
  $: arc   = pct < 0.001 ? ''
           : pct > 0.999 ? `M ${-R} 0 A ${R} ${R} 0 1 1 ${R} 0`
           : `M ${-R} 0 A ${R} ${R} 0 0 1 ${endX} ${endY}`

  $: display = value >= 1000 ? (value / 1000).toFixed(1) + 'k' : Math.round(value)
  $: maxLbl  = max  >= 1000 ? (max  / 1000).toFixed(max % 1000 ? 1 : 0) + 'k' : String(max)
</script>

<div class="gauge">
  <!-- viewBox: 14px side margin, 6px top margin above arc apex, 34px below center for labels -->
  <svg viewBox="-64 -56 128 90" aria-label="{title}: {display}{unit}">
    <!-- Background track -->
    <path
      d="M {-R} 0 A {R} {R} 0 1 1 {R} 0"
      fill="none" stroke="var(--border)" stroke-width={SW} stroke-linecap="round"
    />
    <!-- Value arc -->
    {#if arc}
      <path d={arc} fill="none" stroke={color} stroke-width={SW} stroke-linecap="round" />
    {/if}
    <!-- Tick marks -->
    {#each arcTicks as t}
      <line x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
        stroke="var(--text-muted)"
        stroke-width={t.isMaj ? 1.5 : 0.75}
        opacity={t.isMaj ? 0.65 : 0.35}
      />
    {/each}
    <!-- Numeric readout -->
    <text x="0" y="10" text-anchor="middle" class="val"  fill={color}>{display}</text>
    <text x="0" y="24" text-anchor="middle" class="unit" fill="var(--text-muted)">{unit}</text>
    <!-- Scale endpoints -->
    <text x={-R - 6} y="2" text-anchor="end"   class="scale" fill="var(--text-muted)">0</text>
    <text x={ R + 6} y="2" text-anchor="start" class="scale" fill="var(--text-muted)">{maxLbl}</text>
  </svg>
  {#if title}<div class="title">{title}</div>{/if}
</div>

<style>
  .gauge {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
    height: 100%; box-sizing: border-box;
  }
  svg { width: 100%; max-width: 180px; overflow: visible; }
  .val   { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .unit  { font-size: 10px; }
  .scale { font-size: 9px; }
  .title { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem; text-align: center; }
</style>
