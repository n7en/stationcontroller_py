<script>
  import { onMount, onDestroy } from 'svelte'

  export let card = {}   // card config from dashboard YAML

  let contacts = []
  let status   = null    // {enabled, backends: [{backend, connected, detail}], total_contacts}
  let error    = null
  let loading  = true

  const limit = card.limit || 50

  let interval

  async function load() {
    try {
      const [rs, rc] = await Promise.all([
        fetch('/api/logbook/status'),
        fetch(`/api/logbook/contacts?limit=${limit}`),
      ])
      if (!rs.ok || !rc.ok) throw new Error(`HTTP ${rs.status}/${rc.status}`)
      status   = await rs.json()
      contacts = (await rc.json()).contacts || []
      error    = null
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  function fmtFreq(hz) {
    if (!hz) return ''
    return (hz / 1_000_000).toFixed(3) + ' MHz'
  }

  function fmtAge(ts) {
    if (!ts) return ''
    const age = Math.round((Date.now() / 1000) - ts)
    if (age < 60) return `${age}s`
    if (age < 3600) return `${Math.round(age / 60)}m`
    if (age < 86400) return `${Math.round(age / 3600)}h`
    return `${Math.round(age / 86400)}d`
  }

  onMount(() => {
    load()
    interval = setInterval(load, 30_000)
  })

  onDestroy(() => clearInterval(interval))
</script>

<div class="lb-panel">
  {#if status}
    <div class="lb-status">
      {#if !status.enabled}
        <span class="lb-off">Logbook integration disabled — enable n1mm or n3fjp in config/logbook_config.yaml</span>
      {:else}
        {#each status.backends as b}
          <span class="lb-backend" class:online={b.connected} title={b.detail}>
            <span class="lb-dot"></span>{b.backend.toUpperCase()}
          </span>
        {/each}
        <span class="lb-total">{status.total_contacts} QSOs</span>
      {/if}
    </div>
  {/if}

  {#if error}
    <div class="lb-error">{error}</div>
  {:else if loading}
    <div class="lb-empty">Loading…</div>
  {:else if contacts.length === 0}
    <div class="lb-empty">No contacts logged yet</div>
  {:else}
    <div class="lb-list">
      {#each contacts as c}
        <div class="lb-row" class:dupe={c.dupe}>
          <span class="lb-call" title={c.country || ''}>{c.callsign}</span>
          {#if c.band}<span class="badge">{c.band}</span>{/if}
          {#if c.mode}<span class="badge">{c.mode}</span>{/if}
          <span class="lb-freq">{fmtFreq(c.frequency_hz)}</span>
          <span class="badge src">{c.source}</span>
          <span class="lb-age">{fmtAge(c.timestamp)}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .lb-panel { display: flex; flex-direction: column; gap: 4px; height: 100%; }

  .lb-status {
    display: flex; align-items: center; gap: 10px; flex-shrink: 0;
    font-size: 0.72rem; padding: 2px 2px 4px;
    border-bottom: 1px solid var(--border, #333);
  }
  .lb-backend {
    display: inline-flex; align-items: center; gap: 4px;
    color: var(--muted, #888); font-weight: 600;
  }
  .lb-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--muted, #666);
  }
  .lb-backend.online { color: var(--green, #66bb6a); }
  .lb-backend.online .lb-dot { background: var(--green, #66bb6a); box-shadow: 0 0 4px var(--green, #66bb6a); }
  .lb-total { margin-left: auto; color: var(--muted, #888); }
  .lb-off { color: var(--muted, #888); }

  .lb-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .lb-row {
    display: flex; align-items: center; gap: 6px; padding: 3px 4px;
    border-radius: 3px; font-size: 0.8rem;
  }
  .lb-row:hover { background: var(--surface2, #252540); }
  .lb-row.dupe { opacity: 0.55; }
  .lb-call { font-weight: 600; color: var(--accent, #4fc3f7); min-width: 78px; }
  .lb-freq { color: var(--text, #e0e0e0); font-size: 0.75rem; }
  .lb-age  { color: var(--muted, #888); font-size: 0.72rem; margin-left: auto; }

  .badge {
    border-radius: 3px; padding: 1px 4px; font-size: 0.7rem;
    background: var(--surface2, #252540); color: var(--muted, #aaa);
  }
  .badge.src { text-transform: uppercase; font-size: 0.62rem; }

  .lb-error { color: var(--red, #ef5350); font-size: 0.8rem; padding: 6px; }
  .lb-empty { color: var(--muted, #888); font-size: 0.8rem; padding: 8px; text-align: center; }
</style>
