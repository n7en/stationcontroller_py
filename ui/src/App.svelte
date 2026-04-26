<script>
  import { connected, sensors, labels, radio, updateAvailable } from './stores/ws.js'
  import RadioStatus      from './lib/RadioStatus.svelte'
  import CoaxPortSelector from './lib/CoaxPortSelector.svelte'
  import RelayButton      from './lib/RelayButton.svelte'
  import LabelEditor      from './lib/LabelEditor.svelte'
  import PowerMeterGauge  from './lib/PowerMeterGauge.svelte'
  import SwrBar           from './lib/SwrBar.svelte'
  import DashboardView    from './lib/DashboardView.svelte'
  import RadioConfig      from './lib/RadioConfig.svelte'
  import UpdateChecker   from './lib/UpdateChecker.svelte'

  let page = 'dashboard'

  $: antennaRelays = Array.from({length: 8}, (_, i) => {
    const key = `ant_relay_${i + 1}`
    return { key, value: $sensors[key]?.value ?? 0, label: $labels[key] ?? '', relayNum: i + 1 }
  })

  $: vhfRelays = [
    { key: 'vhf_relay', relayNum: 1 },
  ].map(r => ({ ...r, value: $sensors[r.key]?.value ?? 0, label: $labels[r.key] ?? '' }))

  $: wm = {
    fwd: $sensors['watt_meter_forward_power_w']?.value   ?? 0,
    ref: $sensors['watt_meter_reflected_power_w']?.value ?? 0,
    swr: $sensors['watt_meter_swr']?.value               ?? 0,
  }
</script>

<div class="app">
  <header>
    <div class="brand">StationController</div>
    <nav>
      <button class:active={page==='dashboard'}  on:click={() => page='dashboard'}>Dashboard</button>
      <button class:active={page==='relays'}     on:click={() => page='relays'}>Relays</button>
      <button class:active={page==='dashboards'} on:click={() => page='dashboards'}>Dashboards</button>
      <button class:active={page==='labels'}     on:click={() => page='labels'}>Labels</button>
      <button class:active={page==='settings'}   on:click={() => page='settings'}>
        Settings{#if $updateAvailable}<span class="update-dot" title="Update available"></span>{/if}
      </button>
    </nav>
    <div class="ws-status" class:ok={$connected}>
      <span class="ws-dot"></span>
      {$connected ? 'Live' : 'Connecting…'}
    </div>
  </header>

  <main>
    {#if page === 'dashboard'}

      <section>
        <RadioStatus radioState={$radio} />
      </section>

      <section>
        <div class="section-title">HF Antenna</div>
        <CoaxPortSelector
          deviceName="coax"
          deviceAddr="02"
          labelsMap={$labels}
          sensorsMap={$sensors}
        />
      </section>

      <section>
        <div class="section-title">RF Power</div>
        <div class="power-grid">
          <PowerMeterGauge
            value={wm.fwd} max={1500} color="var(--accent)"
            title={$labels['watt_meter_forward_power_w'] || 'Forward Power'}
          />
          <PowerMeterGauge
            value={wm.ref} max={1500} color="var(--red)"
            title={$labels['watt_meter_reflected_power_w'] || 'Reflected Power'}
          />
          <SwrBar
            value={wm.swr}
            title={$labels['watt_meter_swr'] || 'SWR'}
            thresholds={{ good: 1.5, warning: 2.0, critical: 3.0 }}
          />
        </div>
      </section>

      <section>
        <div class="section-title">Antenna Relays</div>
        <div class="relay-grid">
          {#each antennaRelays as r (r.key)}
            <RelayButton hardwareKey={r.key} label={r.label} value={r.value} deviceAddr="06" relayNum={r.relayNum} />
          {/each}
        </div>
      </section>

    {:else if page === 'relays'}

      <section>
        <div class="section-title">VHF / UHF Coax Relay (#332)</div>
        <div class="relay-grid">
          {#each vhfRelays as r (r.key)}
            <RelayButton hardwareKey={r.key} label={r.label} value={r.value} deviceAddr="05" relayNum={r.relayNum} />
          {/each}
        </div>
      </section>

      <section>
        <div class="section-title">Antenna Relay Module (#361)</div>
        <div class="relay-grid">
          {#each antennaRelays as r (r.key)}
            <RelayButton hardwareKey={r.key} label={r.label} value={r.value} deviceAddr="06" relayNum={r.relayNum} />
          {/each}
        </div>
      </section>

      <section>
        <div class="section-title">HF Coax Switch (#331)</div>
        <CoaxPortSelector
          deviceName="coax"
          deviceAddr="02"
          labelsMap={$labels}
          sensorsMap={$sensors}
        />
      </section>

    {:else if page === 'dashboards'}

      <section>
        <DashboardView dashboardId="main" />
      </section>

    {:else if page === 'labels'}

      <section>
        <LabelEditor />
      </section>

    {:else if page === 'settings'}

      <section>
        <RadioConfig />
      </section>

      <section>
        <UpdateChecker />
      </section>

    {/if}
  </main>
</div>

<style>
  :global(:root) {
    --bg:         #0f1117;
    --surface:    #1a1e29;
    --border:     #2a2f3e;
    --text:       #e0e4f0;
    --text-muted: #7a82a0;
    --accent:     #4e9af1;
    --accent-dim: rgba(78,154,241,0.12);
    --green:      #3ecf8e;
    --red:        #e96262;
  }
  :global(*, *::before, *::after) { box-sizing: border-box; }
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
  }

  .app { display: flex; flex-direction: column; min-height: 100vh; }

  header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 0 1.25rem;
    height: 48px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky; top: 0; z-index: 10;
  }
  .brand { font-weight: 700; font-size: 1rem; flex-shrink: 0; }
  nav { display: flex; gap: 0.25rem; }
  nav button {
    padding: 0.3rem 0.75rem;
    border: none; background: transparent;
    color: var(--text-muted); cursor: pointer;
    border-radius: 5px; font-size: 0.85rem;
    transition: color 0.15s, background 0.15s;
  }
  nav button:hover  { background: var(--border); color: var(--text); }
  nav button.active { background: var(--accent-dim); color: var(--accent); }
  .update-dot {
    display: inline-block;
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
    margin-left: 5px;
    vertical-align: middle;
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.35; }
  }

  .ws-status {
    margin-left: auto;
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.75rem; color: var(--text-muted);
  }
  .ws-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--text-muted); transition: background 0.3s;
  }
  .ws-status.ok .ws-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .ws-status.ok { color: var(--green); }

  main {
    padding: 1.25rem;
    max-width: 900px; width: 100%;
    margin: 0 auto;
    display: flex; flex-direction: column; gap: 1.25rem;
  }
  section { display: flex; flex-direction: column; gap: 0.6rem; }
  .section-title {
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.07em; color: var(--text-muted);
  }
  .power-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.5rem;
  }
  .relay-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 0.4rem;
  }
</style>
