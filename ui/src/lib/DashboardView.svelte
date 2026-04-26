<script>
  import { onMount } from 'svelte'
  import { sensors, labels, radio } from '../stores/ws.js'
  import DashboardCard from './DashboardCard.svelte'

  export let dashboardId = 'main'

  let config  = null
  let error   = null
  let loading = true

  onMount(async () => {
    try {
      const r = await fetch(`/api/dashboards/${dashboardId}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      config = await r.json()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })
</script>

{#if loading}
  <div class="msg">Loading dashboard…</div>
{:else if error}
  <div class="msg err">Could not load dashboard: {error}</div>
{:else if config}
  {#if config.title}
    <div class="dash-title">{config.title}</div>
  {/if}
  <div class="card-grid">
    {#each config.cards ?? [] as card (JSON.stringify(card))}
      <div class="card-wrap card-{card.type}">
        <DashboardCard {card} sensors={$sensors} labels={$labels} radio={$radio} />
      </div>
    {/each}
  </div>
{/if}

<style>
  .msg { padding: 1rem; color: var(--text-muted); font-size: 0.85rem; }
  .err { color: var(--red); }

  .dash-title {
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.07em; color: var(--text-muted);
    margin-bottom: 0.5rem;
  }
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.5rem;
  }
  /* Wider cards for widgets that need horizontal space */
  .card-wrap.card-radio_status { grid-column: span 2; }
  .card-wrap.card-swr_bar      { grid-column: span 2; }
</style>
