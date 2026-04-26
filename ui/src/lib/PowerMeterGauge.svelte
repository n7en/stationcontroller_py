<script>
  export let value  = 0
  export let max    = 1500
  export let color  = '#4e9af1'
  export let title  = ''
  export let unit   = 'W'

  const R  = 50
  const SW = 10

  $: pct   = Math.min(Math.max(value / max, 0), 1)
  $: endX  = +(R * Math.cos(Math.PI * (1 - pct))).toFixed(3)
  $: endY  = +(-R * Math.sin(Math.PI * (1 - pct))).toFixed(3)
  $: lg    = pct > 0.5 ? 1 : 0

  // CCW arc (sweep=0) so it curves through the top of the SVG
  $: arc   = pct < 0.001 ? ''
           : pct > 0.999 ? `M ${-R} 0 A ${R} ${R} 0 1 0 ${R} 0`
           : `M ${-R} 0 A ${R} ${R} 0 ${lg} 0 ${endX} ${endY}`

  $: display = value >= 1000 ? (value / 1000).toFixed(1) + 'k' : Math.round(value)
  $: maxLbl  = max  >= 1000 ? (max  / 1000).toFixed(max % 1000 ? 1 : 0) + 'k' : String(max)
</script>

<div class="gauge">
  <!-- viewBox: 14px side margin, 6px top margin above arc apex, 34px below center for labels -->
  <svg viewBox="-64 -56 128 90" aria-label="{title}: {display}{unit}">
    <!-- Background track -->
    <path
      d="M {-R} 0 A {R} {R} 0 1 0 {R} 0"
      fill="none" stroke="var(--border)" stroke-width={SW} stroke-linecap="round"
    />
    <!-- Value arc -->
    {#if arc}
      <path d={arc} fill="none" stroke={color} stroke-width={SW} stroke-linecap="round" />
    {/if}
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
    display: flex; flex-direction: column; align-items: center;
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
  }
  svg { width: 100%; max-width: 180px; overflow: visible; }
  .val   { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .unit  { font-size: 10px; }
  .scale { font-size: 9px; }
  .title { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.15rem; text-align: center; }
</style>
