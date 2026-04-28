<script>
  import { onMount } from 'svelte'
  import { connected, sensors, labels, radio, updateAvailable } from './stores/ws.js'
  import RadioStatus      from './lib/RadioStatus.svelte'
  import CoaxPortSelector from './lib/CoaxPortSelector.svelte'
  import RelayButton      from './lib/RelayButton.svelte'
  import LabelEditor      from './lib/LabelEditor.svelte'
  import DashboardView    from './lib/DashboardView.svelte'
  import RadioConfig      from './lib/RadioConfig.svelte'
  import UpdateChecker    from './lib/UpdateChecker.svelte'
  import ConfigEditor     from './lib/ConfigEditor.svelte'
  import DeviceCard       from './lib/DeviceCard.svelte'

  let page        = 'dashboard'
  let sidebarOpen = true
  let devices     = []

  onMount(async () => {
    const res = await fetch('/api/devices')
    if (res.ok) {
      const data = await res.json()
      devices = data.devices ?? []
    }
  })

  const NAV = [
    { id: 'dashboard',  label: 'Dashboard',  icon: 'dashboard'  },
    { id: 'relays',     label: 'Relays',      icon: 'relays'     },
    { id: 'dashboards', label: 'Dashboards',  icon: 'dashboards' },
    { id: 'labels',     label: 'Labels',      icon: 'labels'     },
    { id: 'config',     label: 'Config',      icon: 'config'     },
    { id: 'settings',   label: 'Settings',    icon: 'settings'   },
  ]

  const ICONS = {
    menu:       'M3 12h18M3 6h18M3 18h18',
    dashboard:  'M10 3H3v7h7V3zm11 0h-7v7h7V3zm0 11h-7v7h7v-7zm-11 0H3v7h7v-7z',
    relays:     'M18 7a5 5 0 010 10M6 7a5 5 0 000 10M6 12h12',
    dashboards: 'M18 20V10M12 20V4M6 20v-6',
    labels:     'M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82zM7 7h.01',
    config:     'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
    settings:   'M12 15a3 3 0 100-6 3 3 0 000 6zm6.36-1.5a1.5 1.5 0 00.3 1.66l.05.05a2 2 0 010 2.83 2 2 0 01-2.83 0l-.05-.05a1.5 1.5 0 00-1.66-.3 1.5 1.5 0 00-.91 1.37V19a2 2 0 01-4 0v-.09a1.5 1.5 0 00-.98-1.38 1.5 1.5 0 00-1.66.3l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.5 1.5 0 00.3-1.66 1.5 1.5 0 00-1.37-.91H3a2 2 0 010-4h.09a1.5 1.5 0 001.38-.98 1.5 1.5 0 00-.3-1.66l-.06-.06a2 2 0 012.83-2.83l.06.06a1.5 1.5 0 001.66.3H9a1.5 1.5 0 00.91-1.37V3a2 2 0 014 0v.09a1.5 1.5 0 00.91 1.37 1.5 1.5 0 001.66-.3l.06-.06a2 2 0 012.83 2.83l-.06.06a1.5 1.5 0 00-.3 1.66V9a1.5 1.5 0 001.37.91H21a2 2 0 010 4h-.09a1.5 1.5 0 00-1.37.91z',
  }

  $: antennaRelays = Array.from({length: 8}, (_, i) => {
    const key = `ant_relay_${i + 1}`
    return { key, value: $sensors[key]?.value ?? 0, label: $labels[key] ?? '', relayNum: i + 1 }
  })

  $: vhfRelays = [{ key: 'vhf_relay', relayNum: 1 }].map(r => ({
    ...r, value: $sensors[r.key]?.value ?? 0, label: $labels[r.key] ?? '',
  }))

</script>

<div class="app">
  <!-- ── Sidebar ── -->
  <aside class="sidebar" class:collapsed={!sidebarOpen}>

    <div class="sidebar-top">
      <button class="toggle-btn" on:click={() => sidebarOpen = !sidebarOpen} title="Toggle sidebar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" width="18" height="18">
          <path d={ICONS.menu}/>
        </svg>
      </button>
      <span class="brand">StationController</span>
    </div>

    <nav>
      {#each NAV as item (item.id)}
        <button
          class="nav-btn"
          class:active={page === item.id}
          on:click={() => page = item.id}
          title={!sidebarOpen ? item.label : undefined}
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               width="18" height="18" aria-hidden="true">
            <path d={ICONS[item.icon]}/>
          </svg>
          <span class="nav-label">{item.label}</span>
          {#if item.id === 'settings' && $updateAvailable}
            <span class="update-dot" title="Update available"></span>
          {/if}
        </button>
      {/each}
    </nav>

    <div class="sidebar-footer">
      <div class="ws-status" class:ok={$connected} title={$connected ? 'Live' : 'Connecting…'}>
        <span class="ws-dot"></span>
        <span class="nav-label">{$connected ? 'Live' : 'Connecting…'}</span>
      </div>
    </div>

  </aside>

  <!-- ── Main content ── -->
  <main class="content">

    {#if page === 'dashboard'}

      <section>
        <RadioStatus radioState={$radio} />
      </section>

      <div class="device-grid">
        {#each devices as dev (dev.name)}
          <DeviceCard device={dev} />
        {/each}
      </div>

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

    {:else if page === 'config'}

      <section>
        <div class="section-title">Configuration Editor</div>
        <ConfigEditor />
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
    --sidebar-w:  200px;
  }
  :global(*, *::before, *::after) { box-sizing: border-box; }
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
  }

  /* ── Layout ── */
  .app { display: flex; height: 100vh; overflow: hidden; }

  /* ── Sidebar ── */
  .sidebar {
    width: var(--sidebar-w);
    flex-shrink: 0;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    transition: width 0.2s ease;
    overflow: hidden;
  }
  .sidebar.collapsed { width: 52px; }

  .sidebar-top {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    height: 48px;
    padding: 0 0.75rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .toggle-btn {
    flex-shrink: 0;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s, background 0.15s;
  }
  .toggle-btn:hover { color: var(--text); background: var(--border); }

  .brand {
    font-weight: 700;
    font-size: 0.9rem;
    white-space: nowrap;
    overflow: hidden;
    opacity: 1;
    transition: opacity 0.15s ease;
  }
  .collapsed .brand { opacity: 0; pointer-events: none; }

  nav {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    padding: 0.5rem;
    flex: 1;
    overflow-y: auto;
  }

  .nav-btn {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    padding: 0.5rem 0.5rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 5px;
    font-size: 0.85rem;
    text-align: left;
    white-space: nowrap;
    transition: color 0.15s, background 0.15s;
  }
  .nav-btn:hover  { background: var(--border); color: var(--text); }
  .nav-btn.active { background: var(--accent-dim); color: var(--accent); }

  .nav-icon { flex-shrink: 0; }

  .nav-label {
    flex: 1;
    opacity: 1;
    transition: opacity 0.1s ease;
    overflow: hidden;
  }
  .collapsed .nav-label { opacity: 0; width: 0; pointer-events: none; }

  .update-dot {
    flex-shrink: 0;
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
  }

  .sidebar-footer {
    border-top: 1px solid var(--border);
    padding: 0.6rem 0.5rem;
    flex-shrink: 0;
  }

  .ws-status {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    padding: 0.25rem 0.5rem;
  }
  .ws-dot {
    flex-shrink: 0;
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--text-muted);
    transition: background 0.3s;
  }
  .ws-status.ok .ws-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .ws-status.ok { color: var(--green); }

  /* ── Content ── */
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  section { display: flex; flex-direction: column; gap: 0.6rem; }

  .section-title {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-muted);
  }
  .device-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .relay-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 0.4rem;
  }
</style>
