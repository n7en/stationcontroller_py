<script>
  export let value      = 1.0
  export let title      = 'SWR'
  export let thresholds = { good: 1.5, warning: 2.0, critical: 3.0 }

  const MIN = 1.0

  $: MAX = thresholds.critical + (thresholds.critical - thresholds.warning)

  $: scale = (v) => Math.max(0, Math.min(100, (v - MIN) / (MAX - MIN) * 100))

  $: zones = [
    { from: MIN,                 to: thresholds.good,     cls: 'good' },
    { from: thresholds.good,     to: thresholds.warning,  cls: 'warn' },
    { from: thresholds.warning,  to: thresholds.critical, cls: 'crit' },
    { from: thresholds.critical, to: MAX,                 cls: 'over' },
  ]

  $: pos = scale(value)

  $: col = value > 0 && value < thresholds.good    ? 'var(--green)'
         : value < thresholds.warning               ? '#f0a030'
         : 'var(--red)'

  $: display = value > 0 && isFinite(value) ? value.toFixed(2) : '—'
</script>

<div class="swr-card">
  <div class="swr-header">
    <span class="swr-label">{title}</span>
    <span class="swr-val" style="color:{col}">{display}</span>
  </div>
  <div class="swr-row">
    <span class="swr-scale">1.0</span>
    <div class="swr-bar">
      <!-- Colored zone segments, clipped to rounded rect -->
      <div class="zones">
        {#each zones as z}
          <div class="zone zone-{z.cls}" style="width:{scale(z.to) - scale(z.from)}%"></div>
        {/each}
      </div>
      <!-- Needle sits outside the zones clip so it can extend above/below -->
      <div class="needle" style="left:{pos}%"></div>
    </div>
    <span class="swr-scale">{MAX.toFixed(1)}</span>
  </div>
</div>

<style>
  .swr-card {
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
    display: flex; flex-direction: column; gap: 0.45rem;
  }
  .swr-header { display: flex; justify-content: space-between; align-items: baseline; }
  .swr-label  { font-size: 0.78rem; color: var(--text-muted); }
  .swr-val    { font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; }

  .swr-row  { display: flex; align-items: center; gap: 0.4rem; }
  .swr-scale{ font-size: 0.7rem; color: var(--text-muted); white-space: nowrap; }

  .swr-bar {
    position: relative;
    flex: 1;
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
    box-shadow: 0 0 5px rgba(0, 0, 0, 0.7);
    transition: left 0.25s ease;
    pointer-events: none;
  }
</style>
