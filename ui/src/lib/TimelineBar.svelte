<script>
  export let readings = []   // [{ts, value}]
  export let fromTs   = 0
  export let toTs     = Date.now() / 1000

  // Index 0 = off/inactive (dim), 1+ = active states cycling through accent colours
  const PALETTE = [
    { bg: 'var(--border)',   opacity: 0.7  },  // 0 — off
    { bg: 'var(--green)',    opacity: 0.85 },  // 1
    { bg: 'var(--accent)',   opacity: 0.85 },  // 2
    { bg: '#f0a030',         opacity: 0.85 },  // 3
    { bg: 'var(--red)',      opacity: 0.85 },  // 4
    { bg: '#c792ea',         opacity: 0.85 },  // 5
    { bg: '#3ecfcf',         opacity: 0.85 },  // 6
    { bg: '#f0e060',         opacity: 0.75 },  // 7
  ]

  $: tRange = Math.max(toTs - fromTs, 1)

  $: segments = (() => {
    if (!readings.length) return []
    const segs = []
    for (let i = 0; i < readings.length; i++) {
      const r    = readings[i]
      const next = readings[i + 1]
      const segFrom = Math.max(r.ts, fromTs)
      const segTo   = Math.min(next ? next.ts : toTs, toTs)
      if (segTo <= segFrom) continue
      const x  = ((segFrom - fromTs) / tRange) * 100
      const w  = ((segTo   - segFrom) / tRange) * 100
      const vi = Math.round(Math.abs(r.value)) % PALETTE.length
      segs.push({ x, w, value: r.value, vi, ...PALETTE[vi] })
    }
    return segs
  })()

  $: uniqueVals = [...new Set(readings.map(r => Math.round(Math.abs(r.value))))]
    .sort((a, b) => a - b)

  function fmtTs(ts) {
    const d = new Date(ts * 1000)
    if (tRange <= 7200)
      return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    if (tRange <= 86400 * 2)
      return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
    return d.toLocaleDateString([], {month: 'short', day: 'numeric'})
  }

  $: xTicks = Array.from({length: 6}, (_, i) => ({
    pct:   (i / 5) * 100,
    label: fmtTs(fromTs + (i / 5) * tRange),
    i,
  }))
</script>

{#if readings.length === 0}
  <div class="empty">No data</div>
{:else}
  <div class="timeline">
    <div class="bar">
      {#each segments as s}
        <div
          class="seg"
          style="left:{s.x.toFixed(2)}%; width:{s.w.toFixed(2)}%; background:{s.bg}; opacity:{s.opacity}"
          title="Value: {s.value}"
        ></div>
      {/each}
    </div>

    <div class="x-axis">
      {#each xTicks as t}
        <span
          class="x-lbl"
          style="left:{t.pct}%{t.i === 0 ? '' : t.i === 5 ? '; transform:translateX(-100%)' : '; transform:translateX(-50%)'}"
        >{t.label}</span>
      {/each}
    </div>

    {#if uniqueVals.length > 1}
      <div class="legend">
        {#each uniqueVals as vi}
          {@const p = PALETTE[vi % PALETTE.length]}
          <span class="legend-chip" style="background:{p.bg}; opacity:{p.opacity}">{vi}</span>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .timeline { display: flex; flex-direction: column; gap: 2px; }

  .bar {
    position: relative;
    height: 28px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    overflow: hidden;
  }
  .seg { position: absolute; top: 0; bottom: 0; min-width: 1px; }

  .x-axis { position: relative; height: 18px; }
  .x-lbl {
    position: absolute;
    top: 0;
    font-size: 0.62rem;
    color: var(--text-muted);
    white-space: nowrap;
    font-family: ui-monospace, monospace;
  }

  .legend { display: flex; gap: 0.3rem; flex-wrap: wrap; padding-top: 2px; }
  .legend-chip {
    font-size: 0.65rem;
    padding: 1px 7px;
    border-radius: 3px;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }

  .empty { color: var(--text-muted); font-size: 0.75rem; text-align: center; padding: 0.75rem 0; }
</style>
