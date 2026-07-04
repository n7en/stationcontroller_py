<script>
  import { onMount, onDestroy } from 'svelte'
  import { radio } from '../stores/ws.js'

  export let card = {}   // card config from dashboard YAML

  let spots     = []
  let error     = null
  let loading   = true
  let tuning    = null   // spot id currently being tuned to

  // Filters (can be set via card config or user UI)
  let filterBand      = card.band      || ''
  let filterContinent = card.continent || ''
  let filterMode      = card.mode      || ''

  const CONTINENTS = ['', 'AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA']
  const BANDS = ['', '160m', '80m', '60m', '40m', '30m', '20m', '17m',
                 '15m', '12m', '10m', '6m', '2m', '70cm']
  // Matches spot mode or mode_type (PHONE/CW/DIGI are Spothole mode types)
  const MODES = ['', 'CW', 'SSB', 'PHONE', 'FT8', 'FT4', 'RTTY', 'DIGI']

  let interval

  async function loadSpots() {
    try {
      const params = new URLSearchParams({ limit: 100 })
      if (filterBand)      params.set('band', filterBand)
      if (filterContinent) params.set('continent', filterContinent)
      if (filterMode)      params.set('mode', filterMode)
      const r = await fetch(`/api/dx/spots?${params}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      spots = d.spots || []
      error = null
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  async function tuneToSpot(spot) {
    tuning = spot.id
    try {
      const r = await fetch('/api/dx/tune', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ freq: spot.freq, mode: spot.mode || null }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
    } catch (e) {
      error = `Tune failed: ${e.message}`
    } finally {
      setTimeout(() => { tuning = null }, 1500)
    }
  }

  function fmtFreq(hz) {
    if (!hz) return '—'
    const mhz = hz / 1_000_000
    return mhz >= 1 ? mhz.toFixed(3) + ' MHz' : (hz / 1000).toFixed(1) + ' kHz'
  }

  function fmtAge(ts) {
    if (!ts) return ''
    const age = Math.round((Date.now() / 1000) - ts)
    if (age < 60) return `${age}s`
    if (age < 3600) return `${Math.round(age / 60)}m`
    return `${Math.round(age / 3600)}h`
  }

  onMount(() => {
    loadSpots()
    interval = setInterval(loadSpots, 60_000)
  })

  onDestroy(() => clearInterval(interval))
</script>

<div class="dx-panel">
  <div class="dx-filters">
    <select bind:value={filterBand} on:change={loadSpots} class="dx-sel">
      {#each BANDS as b}
        <option value={b}>{b || 'All Bands'}</option>
      {/each}
    </select>
    <select bind:value={filterContinent} on:change={loadSpots} class="dx-sel">
      {#each CONTINENTS as c}
        <option value={c}>{c || 'All Continents'}</option>
      {/each}
    </select>
    <select bind:value={filterMode} on:change={loadSpots} class="dx-sel">
      {#each MODES as m}
        <option value={m}>{m || 'All Modes'}</option>
      {/each}
    </select>
    <button class="dx-refresh" on:click={loadSpots} title="Refresh">↻</button>
  </div>

  {#if error}
    <div class="dx-error">{error}</div>
  {:else if loading}
    <div class="dx-empty">Loading spots…</div>
  {:else if spots.length === 0}
    <div class="dx-empty">No spots</div>
  {:else}
    <div class="dx-list">
      {#each spots as spot (spot.id)}
        <div class="dx-row">
          <span class="dx-call" title="{spot.dx_country || ''}">{spot.dx_call}</span>
          {#if spot.dx_flag}<span class="dx-flag">{spot.dx_flag}</span>{/if}
          <span class="dx-freq">{fmtFreq(spot.freq)}</span>
          <span class="dx-band badge">{spot.band || '?'}</span>
          {#if spot.mode}<span class="dx-mode badge">{spot.mode}</span>{/if}
          {#if spot.sig}<span class="dx-sig badge sig">{spot.sig}</span>{/if}
          <span class="dx-age">{fmtAge(spot.time)}</span>
          <button
            class="dx-tune"
            class:tuning={tuning === spot.id}
            on:click={() => tuneToSpot(spot)}
            title="Tune to {fmtFreq(spot.freq)}"
            disabled={tuning !== null}
          >QSY</button>
          {#if spot.comment}
            <span class="dx-comment" title={spot.comment}>{spot.comment}</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .dx-panel { display: flex; flex-direction: column; gap: 4px; height: 100%; }
  .dx-filters { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
  .dx-sel {
    background: var(--surface, #1a1a2e); color: var(--text, #e0e0e0);
    border: 1px solid var(--border, #333); border-radius: 4px;
    padding: 2px 6px; font-size: 0.78rem;
  }
  .dx-refresh {
    background: none; border: 1px solid var(--border, #333); border-radius: 4px;
    color: var(--text, #e0e0e0); cursor: pointer; padding: 2px 6px; font-size: 0.85rem;
  }
  .dx-refresh:hover { background: var(--surface2, #252540); }
  .dx-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .dx-row {
    display: flex; align-items: center; gap: 5px; padding: 3px 4px;
    border-radius: 3px; font-size: 0.8rem; flex-wrap: wrap;
  }
  .dx-row:hover { background: var(--surface2, #252540); }
  .dx-call { font-weight: 600; color: var(--accent, #4fc3f7); min-width: 70px; }
  .dx-flag { font-size: 1rem; }
  .dx-freq { color: var(--text, #e0e0e0); min-width: 80px; }
  .dx-age { color: var(--muted, #888); font-size: 0.72rem; margin-left: auto; }
  .dx-comment { color: var(--muted, #888); font-size: 0.72rem; flex-basis: 100%;
    padding-left: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .badge {
    border-radius: 3px; padding: 1px 4px; font-size: 0.7rem;
    background: var(--surface2, #252540); color: var(--muted, #aaa);
  }
  .badge.sig { color: #81c784; background: #1b3320; }
  .dx-tune {
    padding: 1px 6px; font-size: 0.72rem; border-radius: 3px; cursor: pointer;
    background: var(--accent, #4fc3f7); color: #000; border: none; font-weight: 600;
  }
  .dx-tune:hover:not(:disabled) { opacity: 0.85; }
  .dx-tune:disabled { opacity: 0.5; cursor: not-allowed; }
  .dx-tune.tuning { background: var(--green, #66bb6a); }
  .dx-error { color: var(--red, #ef5350); font-size: 0.8rem; padding: 6px; }
  .dx-empty { color: var(--muted, #888); font-size: 0.8rem; padding: 8px; text-align: center; }
</style>
