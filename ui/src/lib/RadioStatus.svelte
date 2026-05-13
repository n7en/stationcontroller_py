<script>
  /** @type {import('../stores/ws.js').radio extends import('svelte/store').Writable<infer T> ? T : never} */
  export let radioState = null

  function fmtFreq(hz) {
    if (hz == null) return '—'
    if (hz >= 1e9) return (hz / 1e9).toFixed(4) + ' GHz'
    if (hz >= 1e6) return (hz / 1e6).toFixed(4) + ' MHz'
    return (hz / 1e3).toFixed(1) + ' kHz'
  }

  function fmtBw(hz) {
    if (hz == null || hz === 0) return null
    if (hz >= 1000) return (hz / 1000).toFixed(1) + ' kHz'
    return hz + ' Hz'
  }

  // Hamlib STRENGTH: -54 = S0, 0 ≈ S9, +60 = S9+60dB. Map to 0–100%.
  function signalPct(s) {
    if (s == null) return 0
    return Math.round(Math.min(100, Math.max(0, (s + 54) / 114 * 100)))
  }

  function signalLabel(s) {
    if (s == null) return '—'
    const db = Math.round(s)
    if (db <= -54) return 'S0'
    if (db >= 0) return db > 0 ? `S9+${db}` : 'S9'
    const sval = Math.round((db + 54) / 6) + 1
    return `S${Math.min(9, sval)}`
  }

  function powerPct(r) {
    if (r == null) return 0
    return Math.round(r * 100)
  }
</script>

<div class="radio-panel" class:ptt={radioState?.ptt} class:offline={!radioState?.connected}>

  <!-- Frequency + mode row -->
  <div class="freq-row">
    <span class="freq">{fmtFreq(radioState?.frequency_hz)}</span>
    <div class="badges">
      {#if radioState?.mode}
        <span class="badge mode">{radioState.mode}</span>
      {/if}
      {#if radioState?.vfo}
        <span class="badge vfo">{radioState.vfo}</span>
      {/if}
      {#if fmtBw(radioState?.bandwidth_hz)}
        <span class="badge bw">{fmtBw(radioState.bandwidth_hz)}</span>
      {/if}
      {#if radioState?.ptt}
        <span class="badge tx">TX</span>
      {/if}
    </div>
  </div>

  <!-- Sub-band row -->
  {#if radioState?.connected && radioState?.sub_frequency_hz}
    <div class="sub-row">
      <span class="sub-label">SUB</span>
      <span class="sub-freq">{fmtFreq(radioState.sub_frequency_hz)}</span>
      {#if radioState.sub_mode}
        <span class="badge mode sub-badge">{radioState.sub_mode}</span>
      {/if}
      {#if fmtBw(radioState.sub_bandwidth_hz)}
        <span class="badge bw sub-badge">{fmtBw(radioState.sub_bandwidth_hz)}</span>
      {/if}
    </div>
  {/if}

  <!-- Meters row -->
  {#if radioState?.connected}
    <div class="meters-row">
      <div class="meter">
        <span class="meter-label">RX</span>
        <div class="bar-track">
          <div class="bar-fill signal" style="width:{signalPct(radioState.signal_strength)}%"></div>
        </div>
        <span class="meter-val">{signalLabel(radioState.signal_strength)}</span>
      </div>
      <div class="meter">
        <span class="meter-label">PWR</span>
        <div class="bar-track">
          <div class="bar-fill power" style="width:{powerPct(radioState.rf_power)}%"></div>
        </div>
        <span class="meter-val">
          {radioState.rf_power != null ? powerPct(radioState.rf_power) + '%' : '—'}
        </span>
      </div>
    </div>
  {/if}

  <!-- Status row -->
  <div class="status-row">
    <span class="status-dot" class:ok={radioState?.connected}></span>
    <span class="status-text" class:offline-text={!radioState?.connected}>
      {radioState?.connected ? 'Connected' : 'Offline'}
    </span>
    {#if radioState?.info}
      <span class="info-text">{radioState.info}</span>
    {/if}
  </div>

</div>

<style>
  .radio-panel {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.85rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    transition: border-color 0.2s;
  }
  .radio-panel.ptt    { border-color: var(--red); }
  .radio-panel.offline { border-color: var(--border); opacity: 0.75; }

  /* ── Frequency ── */
  .freq-row {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    flex-wrap: wrap;
  }
  .freq {
    font-size: 1.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
    flex-shrink: 0;
  }
  .badges {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-wrap: wrap;
  }
  .badge {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 3px;
    white-space: nowrap;
  }
  .badge.mode { background: var(--accent-dim); color: var(--accent); }
  .badge.vfo  { background: rgba(62,207,142,0.1); color: var(--green); }
  .badge.bw   { background: var(--surface); color: var(--text-muted); border: 1px solid var(--border); }
  .badge.tx   {
    background: var(--red);
    color: #fff;
    animation: pulse 0.8s ease-in-out infinite alternate;
  }

  /* ── Sub-band ── */
  .sub-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .sub-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    width: 2rem;
    flex-shrink: 0;
  }
  .sub-freq {
    font-size: 0.95rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text-muted);
  }
  .sub-badge { font-size: 0.65rem; }

  /* ── Meters ── */
  .meters-row {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .meter {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
  }
  .meter-label {
    width: 2rem;
    color: var(--text-muted);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    flex-shrink: 0;
  }
  .bar-track {
    flex: 1;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    min-width: 60px;
    max-width: 220px;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
  }
  .bar-fill.signal { background: var(--green); }
  .bar-fill.power  { background: var(--accent); }
  .ptt .bar-fill.power { background: var(--red); }
  .meter-val {
    width: 3.5rem;
    text-align: right;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }

  /* ── Status ── */
  .status-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.75rem;
    color: var(--text-muted);
  }
  .status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
    transition: background 0.3s;
  }
  .status-dot.ok { background: var(--green); box-shadow: 0 0 5px var(--green); }
  .status-text { flex-shrink: 0; }
  .offline-text { color: var(--red); }
  .info-text {
    color: var(--text-muted);
    font-size: 0.72rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .info-text::before { content: '·'; margin-right: 0.3rem; }

  @keyframes pulse { from { opacity: 1 } to { opacity: 0.5 } }
</style>
