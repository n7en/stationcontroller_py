<script>
  export let value      = 1.0
  export let title      = 'SWR'
  export let thresholds = { good: 1.5, warning: 2.0, critical: 3.0 }

  const MIN = 1.0

  $: MAX   = thresholds.critical + (thresholds.critical - thresholds.warning)
  $: range = MAX - MIN

  $: scale = v => Math.max(0, Math.min(100, (v - MIN) / range * 100))

  $: zones = [
    { from: MIN,                 to: thresholds.good,     cls: 'good' },
    { from: thresholds.good,     to: thresholds.warning,  cls: 'warn' },
    { from: thresholds.warning,  to: thresholds.critical, cls: 'crit' },
    { from: thresholds.critical, to: MAX,                 cls: 'over' },
  ]

  $: pos = scale(value)

  $: col = value > 0 && value < thresholds.good   ? 'var(--green)'
         : value < thresholds.warning              ? '#f0a030'
         : 'var(--red)'

  $: display = value > 0 && isFinite(value) ? value.toFixed(2) : '—'

  $: ticks = (() => {
    const out   = []
    const steps = Math.round(range * 10)
    for (let i = 0; i <= steps; i++) {
      const v   = Math.round((MIN + i * 0.1) * 10) / 10
      const pct = scale(v)

      const isWarn = Math.abs(v - thresholds.good)    < 0.005
      const isCrit = Math.abs(v - thresholds.warning)  < 0.005
      const isInt  = Math.abs(v % 1.0)                 < 0.005
      const isHalf = !isInt && Math.abs((v * 2) % 1.0) < 0.005

      const kind = isWarn ? 'warn'
                 : isCrit ? 'crit'
                 : isInt  ? 'major'
                 : isHalf ? 'half'
                 : 'minor'

      out.push({ v, pct, kind, showLabel: isWarn || isCrit || isInt })
    }
    return out
  })()

  $: labelTicks = ticks.filter(t => t.showLabel)
</script>

<div class="swr-card">
  <div class="swr-header">
    <span class="swr-label">{title}</span>
    <span class="swr-val" style="color:{col}">{display}</span>
  </div>

  <div class="swr-track">
    <!-- Coloured zone bar + needle -->
    <div class="swr-bar">
      <div class="zones">
        {#each zones as z}
          <div class="zone zone-{z.cls}" style="width:{scale(z.to) - scale(z.from)}%"></div>
        {/each}
      </div>
      <div class="needle" style="left:{pos}%"></div>
    </div>

    <!-- Tick ruler — every 0.1, bold at 1.5 and 2.0 -->
    <div class="tick-ruler">
      {#each ticks as t}
        <div class="tick tick-{t.kind}" style="left:{t.pct}%"></div>
      {/each}
    </div>

    <!-- Scale labels -->
    <div class="label-ruler">
      {#each labelTicks as t, i}
        <span
          class="lbl lbl-{t.kind}"
          style="left:{t.pct}%; transform:translateX({i === 0 ? '0%' : i === labelTicks.length - 1 ? '-100%' : '-50%'})"
        >{t.v.toFixed(1)}</span>
      {/each}
    </div>
  </div>
</div>

<style>
  .swr-card {
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
    display: flex; flex-direction: column; justify-content: center; gap: 0.4rem;
    height: 100%; box-sizing: border-box;
  }
  .swr-header { display: flex; justify-content: space-between; align-items: baseline; }
  .swr-label  { font-size: 0.78rem; color: var(--text-muted); }
  .swr-val    { font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; }

  .swr-track  { display: flex; flex-direction: column; }

  /* Bar */
  .swr-bar {
    position: relative;
    height: 10px;
  }
  .zones {
    position: absolute;
    inset: 0;
    display: flex;
    border-radius: 5px;
    overflow: hidden;
  }
  .zone { height: 100%; flex-shrink: 0; }
  .zone-good { background: var(--green); opacity: 0.45; }
  .zone-warn { background: #f0a030;     opacity: 0.45; }
  .zone-crit { background: var(--red);  opacity: 0.45; }
  .zone-over { background: #992222;     opacity: 0.45; }

  .needle {
    position: absolute;
    top: -3px; bottom: -3px;
    width: 3px;
    border-radius: 2px;
    background: var(--text);
    transform: translateX(-50%);
    box-shadow: 0 0 5px rgba(0,0,0,0.7);
    transition: left 0.25s ease;
    pointer-events: none;
  }

  /* Tick ruler */
  .tick-ruler {
    position: relative;
    height: 9px;
    margin-top: 2px;
  }
  .tick {
    position: absolute;
    bottom: 0;
    transform: translateX(-50%);
  }
  .tick-minor { width: 1px;  height: 3px; background: var(--text-muted); opacity: 0.35; }
  .tick-half  { width: 1px;  height: 5px; background: var(--text-muted); opacity: 0.55; }
  .tick-major { width: 1px;  height: 5px; background: var(--text-muted); opacity: 0.80; }
  .tick-warn  { width: 2px;  height: 8px; background: #f0a030; }
  .tick-crit  { width: 2px;  height: 8px; background: var(--red); }

  /* Scale labels */
  .label-ruler {
    position: relative;
    height: 14px;
    margin-top: 1px;
  }
  .lbl {
    position: absolute;
    top: 0;
    font-size: 0.62rem;
    color: var(--text-muted);
    white-space: nowrap;
    line-height: 1;
  }
  .lbl-warn  { color: #f0a030; font-weight: 600; }
  .lbl-crit  { color: var(--red); font-weight: 600; }
</style>
