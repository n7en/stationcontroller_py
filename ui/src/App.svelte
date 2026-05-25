<script>
  import { onMount } from 'svelte'
  import { connected, sensors, labels, radio, updateAvailable } from './stores/ws.js'
  import { theme } from './stores/theme.js'
  import CoaxPortSelector from './lib/CoaxPortSelector.svelte'
  import RelayButton      from './lib/RelayButton.svelte'
  import LabelEditor      from './lib/LabelEditor.svelte'
  import DashboardView    from './lib/DashboardView.svelte'
  import RadioConfig      from './lib/RadioConfig.svelte'
  import SystemControls   from './lib/SystemControls.svelte'
  import UpdateChecker    from './lib/UpdateChecker.svelte'
  import ConfigEditor     from './lib/ConfigEditor.svelte'
  import HistoryView      from './lib/HistoryView.svelte'
  import SensorMonitor    from './lib/SensorMonitor.svelte'
  import LogView          from './lib/LogView.svelte'
  import LoginPage        from './lib/LoginPage.svelte'
  import ConfigWizard    from './lib/ConfigWizard.svelte'
  import CommsEditor     from './lib/CommsEditor.svelte'
  import BandPlanEditor  from './lib/BandPlanEditor.svelte'

  let page        = 'dashboard'
  let configTab   = 'comms'
  let sidebarOpen = !window.matchMedia('(max-width: 640px)').matches

  // null = checking auth; {auth_enabled, username} once resolved
  let authState = null

  $: authRequired = authState?.auth_enabled === true && !authState?.username

  onMount(() => {
    const mq = window.matchMedia('(max-width: 640px)')
    const onMQChange = (e) => { if (e.matches) sidebarOpen = false }
    mq.addEventListener('change', onMQChange)
    return () => mq.removeEventListener('change', onMQChange)
  })

  onMount(async () => {
    // Resolve auth state before loading anything else
    try {
      const r = await fetch('/api/auth/me')
      authState = r.ok ? await r.json() : { auth_enabled: false, username: 'anonymous' }
    } catch {
      authState = { auth_enabled: false, username: 'anonymous' }
    }
  })

  async function handleLogin({ detail }) {
    authState = { ...authState, username: detail.username }
  }

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' })
    authState = { ...authState, username: null }
  }

  const NAV = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'relays',    label: 'Relays',    icon: 'relays'    },
    { id: 'labels',    label: 'Labels',    icon: 'labels'    },
    { id: 'history',   label: 'History',   icon: 'history'   },
    { id: 'logs',      label: 'Logs',      icon: 'logs'      },
    { id: 'config',    label: 'Config',    icon: 'config'    },
    { id: 'settings',  label: 'Settings',  icon: 'settings'  },
    { id: 'bandplan',  label: 'Band Plan',  icon: 'bandplan'  },
    { id: 'wizard',    label: 'Setup',     icon: 'wizard'    },
  ]

  const ICONS = {
    menu:       'M3 12h18M3 6h18M3 18h18',
    sun:        'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 7a5 5 0 100 10 5 5 0 000-10z',
    moon:       'M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z',
    auto:       'M12 3v1m0 16v1m9-9h-1M4 12H3M12 7a5 5 0 100 10 5 5 0 000-10z',
    wizard:     'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 12l2 2 4-4',
    history:    'M3 3v18h18M9 17V9M13 17V5M17 17v-3',
    dashboard:  'M10 3H3v7h7V3zm11 0h-7v7h7V3zm0 11h-7v7h7v-7zm-11 0H3v7h7v-7z',
    relays:     'M18 7a5 5 0 010 10M6 7a5 5 0 000 10M6 12h12',
    dashboards: 'M18 20V10M12 20V4M6 20v-6',
    labels:     'M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82zM7 7h.01',
    logs:       'M4 6h16M4 10h16M4 14h10',
    bandplan:   'M3 6h18M3 10h18M3 14h10M3 18h6M15 16l2 2 4-4',
    config:     'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
    settings:   'M12 15a3 3 0 100-6 3 3 0 000 6zm6.36-1.5a1.5 1.5 0 00.3 1.66l.05.05a2 2 0 010 2.83 2 2 0 01-2.83 0l-.05-.05a1.5 1.5 0 00-1.66-.3 1.5 1.5 0 00-.91 1.37V19a2 2 0 01-4 0v-.09a1.5 1.5 0 00-.98-1.38 1.5 1.5 0 00-1.66.3l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.5 1.5 0 00.3-1.66 1.5 1.5 0 00-1.37-.91H3a2 2 0 010-4h.09a1.5 1.5 0 001.38-.98 1.5 1.5 0 00-.3-1.66l-.06-.06a2 2 0 012.83-2.83l.06.06a1.5 1.5 0 001.66.3H9a1.5 1.5 0 00.91-1.37V3a2 2 0 014 0v.09a1.5 1.5 0 00.91 1.37 1.5 1.5 0 001.66-.3l.06-.06a2 2 0 012.83 2.83l-.06.06a1.5 1.5 0 00-.3 1.66V9a1.5 1.5 0 001.37.91H21a2 2 0 010 4h-.09a1.5 1.5 0 00-1.37.91z',
  }

  function cycleTheme() {
    const order = ['system', 'dark', 'light']
    theme.set(order[(order.indexOf($theme) + 1) % order.length])
  }

  function navigate(id) {
    page = id
    if (window.matchMedia('(max-width: 640px)').matches) sidebarOpen = false
  }

  let devices = []

  onMount(async () => {
    try {
      const r = await fetch('/api/devices')
      if (r.ok) devices = (await r.json()).devices ?? []
    } catch {}
  })

  $: relayDevices = devices.filter(dev =>
    dev.type === 'coax_switch' ||
    (dev.sensors ?? []).some(s => s.role === 'relay')
  )

  const DEVICE_TYPE_LABEL = {
    gpio:          'GPIO Module',
    antenna_relay: 'Antenna Relay Module',
    vhf_relay:     'VHF/UHF Coax Relay',
    coax_switch:   'HF Coax Switch',
  }

</script>

{#if authState === null}
  <!-- Auth state loading — render nothing to avoid flash -->
{:else if authRequired}
  <LoginPage on:login={handleLogin} />
{:else}

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
          on:click={() => navigate(item.id)}
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
      <button class="nav-btn theme-cycle" title="Theme: {$theme}" on:click={cycleTheme}>
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
             width="18" height="18" aria-hidden="true">
          <path d={$theme === 'light' ? ICONS.sun : $theme === 'dark' ? ICONS.moon : ICONS.auto}/>
        </svg>
        <span class="nav-label">{$theme === 'system' ? 'Auto' : $theme === 'light' ? 'Light' : 'Dark'}</span>
      </button>
      <div class="ws-status" class:ok={$connected} title={$connected ? 'Live' : 'Connecting…'}>
        <span class="ws-dot"></span>
        <span class="nav-label">{$connected ? 'Live' : 'Connecting…'}</span>
      </div>
      {#if authState?.auth_enabled}
        <button class="logout-btn" on:click={handleLogout} title="Sign out">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>
          </svg>
          <span class="nav-label">{authState.username}</span>
        </button>
      {/if}
    </div>

  </aside>

  <!-- Mobile sidebar backdrop -->
  <div
    class="mobile-backdrop"
    class:visible={sidebarOpen}
    role="presentation"
    on:click={() => sidebarOpen = false}
    on:keydown={() => {}}
  ></div>

  <!-- ── Main content ── -->
  <main class="content">

    {#if page === 'dashboard'}

      <DashboardView dashboardId="main" />

    {:else if page === 'relays'}

      {#if relayDevices.length === 0}
        <p style="color:var(--text-muted);font-size:0.85rem;">
          No relay devices configured. Add devices in Config &rarr; Comms &amp; Devices.
        </p>
      {/if}

      {#each relayDevices as dev (dev.name)}
        <section>
          <div class="section-title">
            {dev.name} &mdash; {DEVICE_TYPE_LABEL[dev.type] ?? dev.type}
            <span style="font-size:0.65rem;opacity:0.6;margin-left:0.4rem">addr {dev.address}</span>
          </div>

          {#if dev.type === 'coax_switch'}
            <CoaxPortSelector
              deviceName={dev.name}
              deviceAddr={dev.address}
              bus={dev.bus ?? ''}
              labelsMap={$labels}
              sensorsMap={$sensors}
            />
          {:else}
            {@const relays = (dev.sensors ?? []).filter(s => s.role === 'relay')}
            <div class="relay-grid">
              {#each relays as s (s.key)}
                <RelayButton
                  hardwareKey={s.key}
                  label={$labels[s.key] ?? ''}
                  value={$sensors[s.key]?.value ?? 0}
                  deviceAddr={dev.address}
                  bus={dev.bus ?? ''}
                  relayNum={s.relay_num}
                />
              {/each}
            </div>
          {/if}
        </section>
      {/each}

    {:else if page === 'labels'}

      <section>
        <LabelEditor />
      </section>

    {:else if page === 'history'}

      <section>
        <SensorMonitor
          title="Temperature"
          detect={(name, info) => {
            const u = (info.unit ?? '').trim()
            return /°|celsius|fahrenheit/i.test(u) || u === 'C' || u === 'F' || u === 'K'
              || name.toLowerCase().includes('temp')
          }}
        />
      </section>

      <section>
        <SensorMonitor
          title="Voltage"
          detect={(name, info) => {
            const u = (info.unit ?? '').trim()
            return /volt|^v$|^mv$|^kv$/i.test(u)
              || /volt|^vcc|^vbat|^vsup/i.test(name)
          }}
        />
      </section>

      <section>
        <div class="section-title">Sensor History</div>
        <HistoryView />
      </section>

    {:else if page === 'logs'}

      <section style="flex:1;min-height:0;height:100%;">
        <div class="section-title">Live Logs</div>
        <LogView />
      </section>

    {:else if page === 'config'}

      <section>
        <div class="config-tabs">
          <button class="tab-btn" class:active={configTab === 'comms'}
            on:click={() => configTab = 'comms'}>Comms &amp; Devices</button>
          <button class="tab-btn" class:active={configTab === 'yaml'}
            on:click={() => configTab = 'yaml'}>YAML Editor</button>
        </div>
        {#if configTab === 'comms'}
          <CommsEditor />
        {:else}
          <div class="section-title">Configuration Editor</div>
          <ConfigEditor />
        {/if}
      </section>

    {:else if page === 'settings'}

      <section>
        <div class="section-title">Appearance</div>
        <div class="theme-picker">
          {#each [
            { id: 'system', label: 'System', desc: 'Follows your browser / OS preference' },
            { id: 'dark',   label: 'Dark',   desc: 'Dark background, light text'          },
            { id: 'light',  label: 'Light',  desc: 'Light background, dark text'          },
          ] as opt}
            <button class="theme-opt" class:active={$theme === opt.id} on:click={() => theme.set(opt.id)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                   width="16" height="16" aria-hidden="true">
                <path d={opt.id === 'light' ? ICONS.sun : opt.id === 'dark' ? ICONS.moon : ICONS.auto}/>
              </svg>
              <span class="theme-opt-label">{opt.label}</span>
              <span class="theme-opt-desc">{opt.desc}</span>
            </button>
          {/each}
        </div>
      </section>

      <section>
        <RadioConfig />
      </section>

      <section>
        <UpdateChecker />
      </section>

      <section>
        <SystemControls />
      </section>

    {:else if page === 'bandplan'}

      <section>
        <BandPlanEditor />
      </section>

    {:else if page === 'wizard'}

      <section>
        <ConfigWizard ondone={() => page = 'dashboard'} />
      </section>

    {/if}

  </main>
</div>

{/if}

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
  :global([data-theme="light"]) {
    --bg:         #f2f4f8;
    --surface:    #ffffff;
    --border:     #d8dce8;
    --text:       #1a1e2e;
    --text-muted: #5c6480;
    --accent:     #2472d4;
    --accent-dim: rgba(36,114,212,0.10);
    --green:      #1a9e6a;
    --red:        #cc3333;
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

  .logout-btn {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    padding: 0.35rem 0.5rem;
    margin-top: 0.25rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 5px;
    font-size: 0.75rem;
    text-align: left;
    transition: color 0.15s, background 0.15s;
    white-space: nowrap;
    overflow: hidden;
  }
  .logout-btn:hover { background: var(--border); color: var(--red); }

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
  .relay-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 0.4rem;
  }

  /* ── Config tabs ── */
  .config-tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0.75rem;
  }
  .tab-btn {
    padding: 0.4rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
    font-size: 0.85rem;
    cursor: pointer;
    margin-bottom: -1px;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* ── Theme cycle button (sidebar footer) ─────────────────────────────── */
  .theme-cycle { font-size: 0.8rem; color: var(--text-muted); }
  .theme-cycle:hover { color: var(--accent); background: var(--border); }

  /* ── Theme picker (settings page) ────────────────────────────────────── */
  .theme-picker {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .theme-opt {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.2rem;
    padding: 0.6rem 0.85rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    min-width: 120px;
    flex: 1;
    transition: border-color 0.15s, background 0.15s;
  }
  .theme-opt svg { color: var(--text-muted); margin-bottom: 0.15rem; }
  .theme-opt:hover { border-color: var(--accent); }
  .theme-opt.active {
    border-color: var(--accent);
    background: var(--accent-dim);
  }
  .theme-opt.active svg { color: var(--accent); }
  .theme-opt-label { font-size: 0.82rem; font-weight: 600; color: var(--text); }
  .theme-opt-desc  { font-size: 0.7rem; color: var(--text-muted); }

  /* ── Mobile ───────────────────────────────────────────────────────────── */
  .mobile-backdrop { display: none; }

  @media (max-width: 640px) {
    /* Sidebar becomes a fixed overlay that slides in from the left */
    .sidebar {
      position: fixed;
      left: 0; top: 0; bottom: 0;
      z-index: 100;
      width: 220px;
      transform: translateX(-100%);
      transition: transform 0.25s ease;
    }
    /* "not collapsed" = sidebarOpen=true = slide in */
    .sidebar:not(.collapsed) {
      transform: translateX(0);
      box-shadow: 6px 0 24px rgba(0, 0, 0, 0.6);
    }
    /* Override the 52px collapsed width so we slide off-screen at full width */
    .sidebar.collapsed { width: 220px; }
    /* Labels always visible when sidebar slides in (not collapsed) */
    .sidebar:not(.collapsed) .nav-label { opacity: 1; width: auto; pointer-events: auto; }
    .sidebar:not(.collapsed) .brand    { opacity: 1; pointer-events: auto; }

    /* Backdrop darkens content when sidebar is open */
    .mobile-backdrop.visible {
      display: block;
      position: fixed; inset: 0;
      background: rgba(0, 0, 0, 0.55);
      z-index: 99;
    }

    /* Content takes full viewport width */
    .content { padding: 0.75rem; }

    /* Larger touch targets for nav */
    .nav-btn { min-height: 44px; }
    .toggle-btn { min-width: 44px; min-height: 44px; }
  }
</style>
