<script>
  export let radioState = null

  function fmtFreq(hz) {
    if (!hz) return '—'
    if (hz >= 1e9) return (hz / 1e9).toFixed(3) + ' GHz'
    if (hz >= 1e6) return (hz / 1e6).toFixed(4) + ' MHz'
    return (hz / 1e3).toFixed(1) + ' kHz'
  }
</script>

<div class="radio-status" class:ptt={radioState?.ptt} class:offline={!radioState?.connected}>
  <div class="radio-row">
    <span class="freq">{fmtFreq(radioState?.frequency_hz)}</span>
    <span class="mode">{radioState?.mode ?? '—'}</span>
    {#if radioState?.ptt}
      <span class="ptt-badge">TX</span>
    {/if}
  </div>
  <div class="radio-row sub">
    <span class:offline-text={!radioState?.connected}>
      {radioState?.connected ? 'Radio connected' : 'Radio offline'}
    </span>
  </div>
</div>

<style>
  .radio-status {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    transition: border-color 0.2s;
  }
  .radio-status.ptt { border-color: var(--red); }
  .radio-row { display: flex; align-items: center; gap: 0.75rem; }
  .radio-row.sub { margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-muted); }
  .freq { font-size: 1.4rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .mode { font-size: 0.85rem; background: var(--surface); padding: 0.1rem 0.4rem; border-radius: 4px; }
  .ptt-badge { background: var(--red); color: #fff; border-radius: 4px; padding: 0.1rem 0.4rem; font-size: 0.75rem; font-weight: 700; animation: pulse 0.8s ease-in-out infinite alternate; }
  .offline-text { color: var(--red); }
  @keyframes pulse { from { opacity: 1 } to { opacity: 0.5 } }
</style>
