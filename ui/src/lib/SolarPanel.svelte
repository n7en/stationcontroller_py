<script>
  import { onMount, onDestroy } from 'svelte'

  let solar   = null
  let error   = null
  let loading = true
  let interval

  async function loadSolar() {
    try {
      const r = await fetch('/api/dx/solar')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      solar = d.solar
      error = null
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  // Colour-code by quality
  function kColor(k) {
    if (k == null) return 'var(--muted)'
    if (k <= 2) return 'var(--green, #66bb6a)'
    if (k <= 4) return '#f0a030'
    return 'var(--red, #ef5350)'
  }
  function condColor(c) {
    if (!c) return 'var(--muted)'
    const lc = c.toLowerCase()
    if (lc === 'good') return 'var(--green, #66bb6a)'
    if (lc === 'fair') return '#f0a030'
    return 'var(--red, #ef5350)'
  }

  const HF_LABELS = {
    '80m-40m-day':   '80/40m Day',  '80m-40m-night': '80/40m Night',
    '30m-20m-day':   '30/20m Day',  '30m-20m-night': '30/20m Night',
    '17m-15m-day':   '17/15m Day',  '17m-15m-night': '17/15m Night',
    '12m-10m-day':   '12/10m Day',  '12m-10m-night': '12/10m Night',
  }

  onMount(() => {
    loadSolar()
    interval = setInterval(loadSolar, 600_000)   // 10 min
  })
  onDestroy(() => clearInterval(interval))
</script>

<div class="solar-panel">
  {#if error}
    <div class="solar-error">{error}</div>
  {:else if loading}
    <div class="solar-empty">Loading solar data…</div>
  {:else if !solar}
    <div class="solar-empty">No solar data available</div>
  {:else}
    <!-- Key indices row -->
    <div class="indices">
      <div class="idx-box">
        <span class="idx-label">SFI</span>
        <span class="idx-val">{solar.sfi ?? '—'}</span>
      </div>
      <div class="idx-box">
        <span class="idx-label">A</span>
        <span class="idx-val">{solar.a_index ?? '—'}</span>
      </div>
      <div class="idx-box">
        <span class="idx-label">K</span>
        <span class="idx-val" style="color:{kColor(solar.k_index)}">{solar.k_index ?? '—'}</span>
      </div>
      {#if solar.sunspots != null}
      <div class="idx-box">
        <span class="idx-label">SSN</span>
        <span class="idx-val">{solar.sunspots}</span>
      </div>
      {/if}
      {#if solar.xray}
      <div class="idx-box">
        <span class="idx-label">X-ray</span>
        <span class="idx-val">{solar.xray}</span>
      </div>
      {/if}
    </div>

    {#if solar.geomag_storm_desc}
      <div class="summary">{solar.geomag_storm_desc}
        {#if solar.geomag_storm_scale > 0}
          <span class="scale-badge warn">G{solar.geomag_storm_scale}</span>
        {/if}
      </div>
    {/if}
    {#if solar.band_conditions_desc}
      <div class="summary">{solar.band_conditions_desc}</div>
    {/if}

    <!-- HF band conditions grid -->
    {#if solar.hf_conditions && Object.keys(solar.hf_conditions).length > 0}
      <div class="hf-grid">
        {#each Object.entries(HF_LABELS) as [key, label]}
          {#if solar.hf_conditions[key]}
            <div class="hf-row">
              <span class="hf-label">{label}</span>
              <span class="hf-cond" style="color:{condColor(solar.hf_conditions[key])}">
                {solar.hf_conditions[key]}
              </span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .solar-panel { display: flex; flex-direction: column; gap: 6px; }
  .indices { display: flex; gap: 6px; flex-wrap: wrap; }
  .idx-box {
    display: flex; flex-direction: column; align-items: center;
    background: var(--surface2, #252540); border-radius: 4px;
    padding: 4px 10px; min-width: 44px;
  }
  .idx-label { font-size: 0.65rem; color: var(--muted, #888); text-transform: uppercase; }
  .idx-val { font-size: 1.05rem; font-weight: 700; color: var(--text, #e0e0e0); }
  .summary { font-size: 0.78rem; color: var(--muted, #aaa); }
  .scale-badge {
    font-size: 0.7rem; border-radius: 3px; padding: 1px 4px; margin-left: 4px; font-weight: 600;
  }
  .scale-badge.warn { background: #f0a03022; color: #f0a030; }
  .hf-grid { display: flex; flex-direction: column; gap: 2px; margin-top: 2px; }
  .hf-row { display: flex; justify-content: space-between; font-size: 0.75rem; }
  .hf-label { color: var(--muted, #888); }
  .hf-cond { font-weight: 600; }
  .solar-error { color: var(--red, #ef5350); font-size: 0.8rem; }
  .solar-empty { color: var(--muted, #888); font-size: 0.8rem; text-align: center; padding: 8px; }
</style>
