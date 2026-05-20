<script>
  import { onMount } from 'svelte'

  /** @type {(() => void) | undefined} */
  export let ondone = undefined

  const STEPS = [
    { label: 'Welcome'   },
    { label: 'Radio'     },
    { label: 'Comms'     },
    { label: 'Telemetry' },
    { label: 'Auth'      },
    { label: 'Save'      },
  ]

  let step    = 0
  let loading = true
  let saving  = false
  let banner  = null   // { ok, text }

  // ── Radio ─────────────────────────────────────────────────────────────────
  let radioEnabled = true
  let radio = {
    name: 'radio', backend: 'managed_rigctld',
    model_id: 351, serial_port: '', serial_baud: 9600,
    host: '127.0.0.1', port: 0,
    timeout_s: 15.0, startup_timeout_s: 10.0,
    poll_interval_s: 1.0, reconnect_delay_s: 5.0,
  }

  function switchBackend(e) {
    const backend = e.target.value
    const shared  = { name: radio.name, backend,
                      poll_interval_s: radio.poll_interval_s,
                      reconnect_delay_s: radio.reconnect_delay_s,
                      timeout_s: radio.timeout_s ?? 15.0 }
    if (backend === 'managed_rigctld') {
      radio = { ...shared, model_id: radio.model_id ?? 351,
                serial_port: radio.serial_port ?? radio.port ?? '',
                serial_baud: radio.serial_baud ?? radio.baud_rate ?? 9600,
                host: '127.0.0.1', port: 0, startup_timeout_s: 10.0 }
    } else if (backend === 'rigctld') {
      radio = { ...shared, host: 'localhost', port: 4532 }
    } else {
      radio = { ...shared, model_id: radio.model_id ?? 1,
                port: radio.serial_port ?? radio.port ?? '',
                baud_rate: radio.serial_baud ?? radio.baud_rate ?? 9600,
                data_bits: 8, stop_bits: 1, parity: 'N' }
    }
  }

  // ── Communications ────────────────────────────────────────────────────────
  let buses   = []
  let devices = []

  let addingBus    = false
  let addingDevice = false
  let newBus       = mkBus()
  let newDevice    = mkDevice()

  function mkBus() {
    return {
      name: '',
      transport: {
        type: 'rs485',
        port: '', baud_rate: 9600,
        broker: 'localhost', port_mqtt: 1883, topic_rx: '', topic_tx: '',
        username: '', password: '',
        host: '0.0.0.0', port_tcp: 4880,
      },
    }
  }
  function mkDevice() {
    return { type: 'gpio', name: '', address: '01', bus: '', persona: 'cc_8a' }
  }

  function commitBus() {
    if (!newBus.name.trim()) return
    const t   = newBus.transport
    const bus = {
      name: newBus.name.trim(),
      transport: {
        ...t,
        topic_rx: t.topic_rx || `dcn/${newBus.name.trim()}/rx`,
        topic_tx: t.topic_tx || `dcn/${newBus.name.trim()}/tx`,
      },
    }
    buses     = [...buses, bus]
    newBus    = mkBus()
    addingBus = false
  }

  function removeBus(i) {
    const name = buses[i].name
    buses   = buses.filter((_, idx) => idx !== i)
    devices = devices.filter(d => d.bus !== name)
  }

  function commitDevice() {
    if (!newDevice.name.trim() || !newDevice.bus) return
    devices      = [...devices, { ...newDevice }]
    newDevice    = mkDevice()
    addingDevice = false
  }

  function removeDevice(i) { devices = devices.filter((_, idx) => idx !== i) }

  $: busNames = buses.map(b => b.name)

  // ── DCN Auto-discovery ────────────────────────────────────────────────────
  let scanBus      = ''         // bus name to scan (defaults to first live bus)
  let scanning     = false
  let scanResults  = null       // null = not run yet, [] = ran but nothing found
  let scanError    = null
  let liveBuses    = []         // bus names known to the running app

  // Keep scan-bus default in sync with available buses
  $: if (!scanBus && liveBuses.length) scanBus = liveBuses[0]
  $: if (!scanBus && busNames.length)  scanBus = busNames[0]

  async function loadLiveBuses() {
    try {
      const r = await fetch('/api/comms/buses')
      if (r.ok) liveBuses = (await r.json()).buses ?? []
    } catch (_) { liveBuses = [] }
  }

  async function scanForDevices() {
    if (scanning) return
    scanning    = true
    scanResults = null
    scanError   = null
    try {
      const bus = scanBus || liveBuses[0] || busNames[0] || 'control'
      const r   = await fetch(`/api/comms/discover?bus=${encodeURIComponent(bus)}&timeout=3`, { method: 'POST' })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        scanError = d.detail ?? `HTTP ${r.status}`
      } else {
        scanResults = (await r.json()).devices ?? []
      }
    } catch (e) { scanError = e.message }
    scanning = false
  }

  const DEVICE_TYPE_LABELS = {
    gpio:          'GPIO (#321)',
    antenna_relay: 'Antenna Relay (#361)',
    coax_switch:   'Coax Switch (#331)',
    vhf_coax_relay:'VHF Relay (#332)',
    watt_meter:    'Watt Meter (#351)',
  }

  function addDiscovered(d) {
    const bus = scanBus || busNames[0] || ''
    const defaultName = (d.device_type ?? d.raw_type ?? 'device') + '_' + d.address
    devices = [...devices, {
      type:    d.device_type ?? 'gpio',
      name:    defaultName,
      address: d.address,
      bus,
      persona: 'cc_8a',
    }]
  }

  // ── Telemetry ─────────────────────────────────────────────────────────────
  let telemetry = {
    enabled:               true,
    db_url:                'sqlite+aiosqlite:///data/station.db',
    min_interval_s:        1.0,
    dcn_logging:           false,
    retention_sensor_days: 90,
    retention_events_days: 365,
  }

  // ── Auth ──────────────────────────────────────────────────────────────────
  let auth = { enabled: false, secure_cookie: false, token_expiry_hours: 24 }
  let authUsers  = []
  let newUser    = { username: '', password: '' }
  let addingUser = false
  let userBanner = null

  async function loadUsers() {
    const r = await fetch('/api/auth/users')
    if (r.ok) authUsers = (await r.json()).users ?? []
  }

  async function addUser() {
    if (!newUser.username.trim() || !newUser.password) return
    addingUser = true; userBanner = null
    try {
      const r = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: newUser.username.trim(), password: newUser.password }),
      })
      if (!r.ok) throw new Error((await r.json()).detail ?? 'Failed')
      newUser = { username: '', password: '' }
      await loadUsers()
      userBanner = { ok: true, text: 'User saved.' }
    } catch (e) { userBanner = { ok: false, text: e.message } }
    addingUser = false
  }

  async function deleteUser(username) {
    const r = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' })
    if (r.ok) await loadUsers()
  }

  // ── Load on mount ─────────────────────────────────────────────────────────
  onMount(loadAll)

  async function loadAll() {
    loading = true
    try {
      // Radio
      const rr = await fetch('/api/radio/config')
      if (rr.ok) {
        const d  = await rr.json()
        const r0 = d.radios?.[0]
        if (r0) { radioEnabled = true; radio = { ...radio, ...r0 } }
        else     { radioEnabled = false }
      }

      // Comms
      const cr = await fetch('/api/config/comms/json')
      if (cr.ok) {
        const d = await cr.json()
        buses = (d.buses ?? []).map(b => {
          const t = b.transports?.[0] ?? {}
          return {
            name: b.name,
            transport: {
              type:      t.type     ?? 'rs485',
              port:      t.port     ?? '',
              baud_rate: t.baud_rate ?? 9600,
              broker:    t.broker   ?? 'localhost',
              port_mqtt: t.port     ?? 1883,
              topic_rx:  t.topic_rx ?? `dcn/${b.name}/rx`,
              topic_tx:  t.topic_tx ?? `dcn/${b.name}/tx`,
              username:  t.username ?? '',
              password:  t.password ?? '',
              host:      t.host     ?? '0.0.0.0',
              port_tcp:  t.port     ?? 4880,
            },
          }
        })
        devices = (d.devices ?? []).map(d => ({
          type:    d.type,
          name:    d.name,
          address: d.address,
          bus:     d.bus,
          persona: d.persona ?? 'cc_8a',
        }))
      }

      // Telemetry
      const tr = await fetch('/api/config/telemetry/json')
      if (tr.ok) {
        const d = await tr.json()
        const t = d.telemetry ?? {}
        telemetry = {
          enabled:               t.enabled !== false,
          db_url:                t.database?.url       ?? telemetry.db_url,
          min_interval_s:        t.sensor_recording?.min_interval_s ?? 1.0,
          dcn_logging:           t.dcn_logging?.enabled ?? false,
          retention_sensor_days: t.retention?.sensor_readings_days  ?? 90,
          retention_events_days: t.retention?.device_events_days    ?? 365,
        }
      }

      // Auth
      const ar = await fetch('/api/config/auth/json')
      if (ar.ok) {
        const d = await ar.json()
        const a = d.auth ?? {}
        auth = {
          enabled:            a.enabled            ?? false,
          secure_cookie:      a.secure_cookie       ?? false,
          token_expiry_hours: a.token_expiry_hours  ?? 24,
        }
      }

      await loadUsers()
      await loadLiveBuses()
    } catch (e) { console.error('Wizard load error:', e) }
    loading = false
  }

  // ── YAML builders ─────────────────────────────────────────────────────────
  function buildCommsYaml() {
    const L = ['buses:']
    for (const bus of buses) {
      const t = bus.transport
      L.push('', `  - name: ${bus.name}`, '    transports:',
             `      - name: ${bus.name}_${t.type}`, `        type: ${t.type}`)
      if (t.type === 'rs485') {
        L.push(`        port: ${t.port}`, `        baud_rate: ${t.baud_rate}`)
      } else if (t.type === 'nodered_mqtt') {
        L.push(`        broker: ${t.broker}`, `        port: ${t.port_mqtt}`,
               `        topic_rx: "${t.topic_rx}"`, `        topic_tx: "${t.topic_tx}"`)
        if (t.username) L.push(`        username: "${t.username}"`)
        if (t.password) L.push(`        password: "${t.password}"`)
      } else if (t.type === 'nodered_tcp') {
        L.push(`        host: ${t.host}`, `        port: ${t.port_tcp}`)
      }
    }
    if (!buses.length) L.push('')
    L.push('', 'devices:')
    for (const d of devices) {
      L.push('', `  - type: ${d.type}`, `    name: ${d.name}`,
             `    address: "${d.address}"`, `    bus: ${d.bus}`)
      if (d.type === 'antenna_relay' && d.persona)
        L.push(`    persona: ${d.persona}`)
    }
    if (!devices.length) L.push('')
    return L.join('\n') + '\n'
  }

  function buildTelemetryYaml() {
    return `telemetry:
  enabled: ${telemetry.enabled}

  database:
    url: "${telemetry.db_url}"

  sensor_recording:
    min_interval_s: ${telemetry.min_interval_s}
    min_change_threshold: 0.0
    exclude: []

  dcn_logging:
    enabled: ${telemetry.dcn_logging}

  retention:
    sensor_readings_days: ${telemetry.retention_sensor_days}
    device_events_days: ${telemetry.retention_events_days}
    automation_events_days: ${telemetry.retention_events_days}
    application_log_days: 30
`
  }

  async function buildAuthYaml() {
    // Re-fetch to pick up any live user changes made during this wizard session
    const r      = await fetch('/api/config/auth/json')
    const latest = r.ok ? await r.json() : {}
    const a      = latest.auth ?? {}
    const secret = a.secret || genHex(64)
    const users  = a.users  ?? {}

    let usersBlock = ' {}'
    if (Object.keys(users).length) {
      usersBlock = '\n'
      for (const [u, data] of Object.entries(users)) {
        const hash = typeof data === 'string' ? data : (data.password_hash ?? '')
        usersBlock += `    ${u}:\n      password_hash: "${hash.replace(/"/g, '\\"')}"\n`
      }
    }
    return `auth:
  enabled: ${auth.enabled}
  secret: ${secret}
  secure_cookie: ${auth.secure_cookie}
  token_expiry_hours: ${auth.token_expiry_hours}
  users:${usersBlock}`
  }

  function genHex(n) {
    const b = new Uint8Array(n / 2)
    crypto.getRandomValues(b)
    return [...b].map(x => x.toString(16).padStart(2, '0')).join('')
  }

  // ── Save everything ───────────────────────────────────────────────────────
  async function saveAll() {
    saving = true; banner = null
    const errors = []

    // Radio
    const radioPayload = radioEnabled ? { radios: [radio] } : { radios: [] }
    const rr = await fetch('/api/radio/config', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(radioPayload),
    })
    if (!rr.ok) errors.push('radio')

    // Comms
    const cr = await fetch('/api/config/comms', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: buildCommsYaml() }),
    })
    if (!cr.ok) errors.push('comms')

    // Telemetry
    const tr = await fetch('/api/config/telemetry', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: buildTelemetryYaml() }),
    })
    if (!tr.ok) errors.push('telemetry')

    // Auth
    const authYaml = await buildAuthYaml()
    const ar = await fetch('/api/config/auth', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: authYaml }),
    })
    if (!ar.ok) errors.push('auth')

    saving = false
    banner = errors.length
      ? { ok: false, text: `Save failed for: ${errors.join(', ')}. Check application logs.` }
      : { ok: true,  text: 'All configurations saved. Restart the app to apply changes.' }
  }

  $: isFirst = step === 0
  $: isLast  = step === STEPS.length - 1
</script>

<!-- ═══════════════════════════════════════════════════════════════════════ -->

<div class="wizard">

  <!-- ── Stepper ─────────────────────────────────────────────────────────── -->
  <div class="stepper">
    {#each STEPS as s, i}
      <button
        class="step-node"
        class:done={i < step}
        class:active={i === step}
        on:click={() => { if (i < step) step = i }}
        disabled={i > step}
      >
        <div class="node-circle">
          {#if i < step}✓{:else}{i + 1}{/if}
        </div>
        <div class="node-label">{s.label}</div>
      </button>
      {#if i < STEPS.length - 1}
        <div class="step-line" class:done={i < step}></div>
      {/if}
    {/each}
  </div>

  <!-- ── Body ───────────────────────────────────────────────────────────── -->
  <div class="body">

    {#if loading}

      <p class="loading">Loading configuration…</p>

    <!-- ── Step 0: Welcome ────────────────────────────────────────────── -->
    {:else if step === 0}

      <div class="welcome">
        <div class="welcome-icon">⚙</div>
        <h1>Setup Wizard</h1>
        <p class="welcome-sub">
          Configure the core modules of your Station Controller.
          Each step is optional — skip anything you don't need right now.
        </p>
        <div class="module-cards">
          <div class="mcard"><span class="mcard-icon">📻</span><div><strong>Radio</strong><span>Connect via managed rigctld, rigctld, or hamlib</span></div></div>
          <div class="mcard"><span class="mcard-icon">🔌</span><div><strong>Communications</strong><span>DCN buses and hardware devices</span></div></div>
          <div class="mcard"><span class="mcard-icon">📊</span><div><strong>Telemetry</strong><span>SQLite sensor data recording</span></div></div>
          <div class="mcard"><span class="mcard-icon">🔒</span><div><strong>Authentication</strong><span>Secure the web interface</span></div></div>
        </div>
        <div class="welcome-actions">
          <button class="btn-primary large" on:click={() => step = 1}>Start Setup →</button>
          {#if ondone}
            <button class="btn-ghost" on:click={ondone}>Exit wizard</button>
          {/if}
        </div>
      </div>

    <!-- ── Step 1: Radio ──────────────────────────────────────────────── -->
    {:else if step === 1}

      <h2>Radio Control</h2>

      <div class="toggle-row">
        <label class="toggle">
          <input type="checkbox" bind:checked={radioEnabled} />
          <span class="slider"></span>
        </label>
        <span>Enable radio control</span>
      </div>

      {#if radioEnabled}
        <div class="fields">
          <div class="field">
            <label for="r-name">Name</label>
            <input id="r-name" bind:value={radio.name} />
          </div>

          <div class="field">
            <label for="r-backend">Backend</label>
            <select id="r-backend" value={radio.backend} on:change={switchBackend}>
              <option value="managed_rigctld">managed rigctld — auto-start rigctld (recommended, local radio)</option>
              <option value="rigctld">rigctld — TCP connection to a running rigctld daemon</option>
              <option value="hamlib_direct">hamlib direct — Python bindings, local serial port</option>
            </select>
          </div>

          {#if radio.backend === 'managed_rigctld'}
            <div class="field-row">
              <div class="field narrow">
                <label for="r-model">Model ID</label>
                <input id="r-model" type="number" bind:value={radio.model_id} min="1" placeholder="351" />
              </div>
              <div class="field grow">
                <label for="r-serial">Serial port</label>
                <input id="r-serial" bind:value={radio.serial_port} placeholder="COM3 or /dev/ttyUSB0" />
              </div>
              <div class="field narrow">
                <label for="r-sbaud">Baud rate</label>
                <input id="r-sbaud" type="number" bind:value={radio.serial_baud} />
              </div>
            </div>
            <div class="field-row">
              <div class="field narrow">
                <label for="r-timeout">Timeout (s)</label>
                <input id="r-timeout" type="number" bind:value={radio.timeout_s} min="5" max="60" step="1" />
              </div>
              <div class="field narrow">
                <label for="r-startup">Startup timeout (s)</label>
                <input id="r-startup" type="number" bind:value={radio.startup_timeout_s} min="5" max="60" step="1" />
              </div>
              <div class="field narrow">
                <label for="r-port">TCP port (0 = auto)</label>
                <input id="r-port" type="number" bind:value={radio.port} min="0" max="65535" />
              </div>
            </div>
            <p class="hint">Model IDs: 1 = Dummy · 351 = IC-7300 · 3073 = IC-7610 · 135 = FT-991A · 2014 = TS-2000 · 122 = FT-817</p>
          {/if}

          {#if radio.backend === 'rigctld'}
            <div class="field-row">
              <div class="field grow">
                <label for="r-host">Host</label>
                <input id="r-host" bind:value={radio.host} placeholder="localhost" />
              </div>
              <div class="field narrow">
                <label for="r-port">Port</label>
                <input id="r-port" type="number" bind:value={radio.port} min="1" max="65535" />
              </div>
              <div class="field narrow">
                <label for="r-timeout">Timeout (s)</label>
                <input id="r-timeout" type="number" bind:value={radio.timeout_s} min="5" max="60" step="1" />
              </div>
            </div>
            <p class="hint">Start rigctld first: <code>rigctld -m &lt;model&gt; -r &lt;port&gt; -s &lt;baud&gt;</code></p>
          {/if}

          {#if radio.backend === 'hamlib_direct'}
            <div class="field-row">
              <div class="field narrow">
                <label for="r-model">Model ID</label>
                <input id="r-model" type="number" bind:value={radio.model_id} min="1" placeholder="351" />
              </div>
              <div class="field grow">
                <label for="r-dev">Serial port</label>
                <input id="r-dev" bind:value={radio.port} placeholder="COM3 or /dev/ttyUSB0" />
              </div>
            </div>
            <div class="field-row">
              <div class="field narrow">
                <label for="r-baud">Baud rate</label>
                <input id="r-baud" type="number" bind:value={radio.baud_rate} />
              </div>
              <div class="field narrow">
                <label for="r-data">Data bits</label>
                <input id="r-data" type="number" bind:value={radio.data_bits} min="7" max="8" />
              </div>
              <div class="field narrow">
                <label for="r-stop">Stop bits</label>
                <input id="r-stop" type="number" bind:value={radio.stop_bits} min="1" max="2" />
              </div>
              <div class="field narrow">
                <label for="r-par">Parity</label>
                <select id="r-par" bind:value={radio.parity}>
                  <option value="N">None</option>
                  <option value="E">Even</option>
                  <option value="O">Odd</option>
                </select>
              </div>
            </div>
            <p class="hint">Model IDs: 1 = Dummy · 351 = IC-7300 · 135 = FT-991A · 2014 = TS-2000</p>
          {/if}

          <div class="field-row">
            <div class="field narrow">
              <label for="r-poll">Poll interval (s)</label>
              <input id="r-poll" type="number" bind:value={radio.poll_interval_s} min="0.1" max="10" step="0.1" />
            </div>
            <div class="field narrow">
              <label for="r-recon">Reconnect delay (s)</label>
              <input id="r-recon" type="number" bind:value={radio.reconnect_delay_s} min="1" max="120" step="1" />
            </div>
          </div>
        </div>
      {:else}
        <p class="hint">Radio control will be disabled. You can enable it later in Settings.</p>
      {/if}

    <!-- ── Step 2: Comms ──────────────────────────────────────────────── -->
    {:else if step === 2}

      <h2>Communications (DCN Buses)</h2>

      <!-- Buses -->
      <div class="section">
        <div class="section-hdr">
          <span class="section-title">Buses</span>
          <button class="btn-add" on:click={() => { addingBus = true; addingDevice = false }}>+ Add Bus</button>
        </div>

        {#each buses as bus, i (bus.name)}
          <div class="item-row">
            <span class="item-name">{bus.name}</span>
            <span class="badge">{bus.transport.type}</span>
            {#if bus.transport.type === 'rs485'}
              <span class="item-detail">{bus.transport.port} · {bus.transport.baud_rate}</span>
            {:else if bus.transport.type === 'nodered_mqtt'}
              <span class="item-detail">{bus.transport.broker}:{bus.transport.port_mqtt}</span>
            {:else}
              <span class="item-detail">{bus.transport.host}:{bus.transport.port_tcp}</span>
            {/if}
            <button class="btn-remove" on:click={() => removeBus(i)}>×</button>
          </div>
        {/each}

        {#if !buses.length && !addingBus}
          <p class="empty">No buses configured. Add one to connect hardware.</p>
        {/if}

        {#if addingBus}
          <div class="inline-form">
            <div class="field-row">
              <div class="field grow">
                <label>Bus name
                  <input bind:value={newBus.name} placeholder="control" />
                </label>
              </div>
              <div class="field narrow">
                <label>Transport
                  <select bind:value={newBus.transport.type}>
                    <option value="rs485">RS-485</option>
                    <option value="nodered_mqtt">MQTT</option>
                    <option value="nodered_tcp">TCP</option>
                  </select>
                </label>
              </div>
            </div>

            {#if newBus.transport.type === 'rs485'}
              <div class="field-row">
                <div class="field grow">
                  <label>Serial port
                    <input bind:value={newBus.transport.port} placeholder="COM3 or /dev/ttyUSB0" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Baud rate
                    <select bind:value={newBus.transport.baud_rate}>
                      {#each [4800,9600,19200,38400,57600,115200] as b}
                        <option value={b}>{b}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              </div>
            {:else if newBus.transport.type === 'nodered_mqtt'}
              <div class="field-row">
                <div class="field grow">
                  <label>Broker
                    <input bind:value={newBus.transport.broker} placeholder="localhost" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port
                    <input type="number" bind:value={newBus.transport.port_mqtt} />
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field grow">
                  <label>RX topic
                    <input bind:value={newBus.transport.topic_rx} placeholder="dcn/{name}/rx" />
                  </label>
                </div>
                <div class="field grow">
                  <label>TX topic
                    <input bind:value={newBus.transport.topic_tx} placeholder="dcn/{name}/tx" />
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field grow">
                  <label>Username (optional)
                    <input bind:value={newBus.transport.username} />
                  </label>
                </div>
                <div class="field grow">
                  <label>Password (optional)
                    <input type="password" bind:value={newBus.transport.password} />
                  </label>
                </div>
              </div>
            {:else if newBus.transport.type === 'nodered_tcp'}
              <div class="field-row">
                <div class="field grow">
                  <label>Listen host
                    <input bind:value={newBus.transport.host} placeholder="0.0.0.0" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port
                    <input type="number" bind:value={newBus.transport.port_tcp} />
                  </label>
                </div>
              </div>
            {/if}

            <div class="form-btns">
              <button class="btn-secondary" on:click={() => { addingBus = false; newBus = mkBus() }}>Cancel</button>
              <button class="btn-primary" on:click={commitBus} disabled={!newBus.name.trim()}>Add Bus</button>
            </div>
          </div>
        {/if}
      </div>

      <!-- Devices -->
      <div class="section">
        <div class="section-hdr">
          <span class="section-title">Devices</span>
          <div class="hdr-actions">
            <div class="scan-row">
              <select class="scan-bus-sel" bind:value={scanBus}
                disabled={scanning || (!liveBuses.length && !busNames.length)}>
                {#each liveBuses as b}
                  <option value={b}>{b}</option>
                {/each}
                {#each busNames.filter(b => !liveBuses.includes(b)) as b}
                  <option value={b}>{b} (not live)</option>
                {/each}
                {#if !liveBuses.length && !busNames.length}
                  <option value="">— no buses —</option>
                {/if}
              </select>
              <button class="btn-scan"
                disabled={scanning || (!liveBuses.length && !busNames.length)}
                on:click={scanForDevices}>
                {scanning ? 'Scanning…' : 'Scan Bus'}
              </button>
            </div>
            <button class="btn-add" disabled={!buses.length}
              on:click={() => { addingDevice = true; addingBus = false; if (busNames[0]) newDevice.bus = busNames[0] }}>
              + Add Device
            </button>
          </div>
        </div>

        {#if scanError}
          <div class="banner">{scanError}</div>
        {/if}

        {#if scanResults !== null}
          {#if scanResults.length === 0}
            <p class="empty">No devices responded to PING on bus <strong>{scanBus}</strong>.</p>
          {:else}
            <div class="scan-results">
              <p class="scan-header">Found {scanResults.length} device{scanResults.length !== 1 ? 's' : ''} — click to add:</p>
              {#each scanResults as d}
                {@const alreadyAdded = devices.some(x => x.address === d.address)}
                <div class="scan-result-row" class:added={alreadyAdded}>
                  <span class="scan-addr">#{d.address}</span>
                  <span class="scan-type">{DEVICE_TYPE_LABELS[d.device_type] ?? d.raw_type ?? 'Unknown'}</span>
                  {#if alreadyAdded}
                    <span class="scan-tag">added</span>
                  {:else}
                    <button class="btn-add" on:click={() => addDiscovered(d)}>+ Add</button>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        {/if}

        {#each devices as dev, i (i)}
          <div class="item-row">
            <span class="item-name">{dev.name}</span>
            <span class="badge">{dev.type}</span>
            <span class="item-detail">#{dev.address} · {dev.bus}</span>
            <button class="btn-remove" on:click={() => removeDevice(i)}>×</button>
          </div>
        {/each}

        {#if !devices.length && !addingDevice}
          <p class="empty">{buses.length ? 'No devices configured.' : 'Add a bus first, then add devices.'}</p>
        {/if}

        {#if addingDevice}
          <div class="inline-form">
            <div class="field-row">
              <div class="field narrow">
                <label>Type
                  <select bind:value={newDevice.type}>
                    <option value="gpio">GPIO (#321)</option>
                    <option value="coax_switch">Coax Switch (#331)</option>
                    <option value="watt_meter">Watt Meter (#351)</option>
                    <option value="vhf_relay">VHF Relay (#332)</option>
                    <option value="antenna_relay">Antenna Relay (#361)</option>
                  </select>
                </label>
              </div>
              <div class="field grow">
                <label>Name
                  <input bind:value={newDevice.name} placeholder="gpio" />
                </label>
              </div>
            </div>
            <div class="field-row">
              <div class="field narrow">
                <label>Address (hex)
                  <input bind:value={newDevice.address} placeholder="01" maxlength="2" />
                </label>
              </div>
              <div class="field grow">
                <label>Bus
                  <select bind:value={newDevice.bus}>
                    <option value="">— select bus —</option>
                    {#each busNames as b}
                      <option value={b}>{b}</option>
                    {/each}
                  </select>
                </label>
              </div>
            </div>
            {#if newDevice.type === 'antenna_relay'}
              <div class="field">
                <label>Persona
                  <select bind:value={newDevice.persona}>
                    <option value="cc_8a">CC-8A (8-antenna)</option>
                    <option value="1_of_8">1-of-8 select</option>
                    <option value="dual_vertical">Dual vertical</option>
                    <option value="bcd">BCD</option>
                    <option value="three_ant_phasing">3-element phasing</option>
                    <option value="two_ant_phasing">2-element phasing</option>
                    <option value="hi_z_3el">Hi-Z 3-element</option>
                    <option value="hi_z_4el">Hi-Z 4-element</option>
                    <option value="hi_z_4_8_pro">Hi-Z 4/8 Pro</option>
                    <option value="hi_z_8el">Hi-Z 8-element</option>
                  </select>
                </label>
              </div>
            {/if}
            <div class="form-btns">
              <button class="btn-secondary" on:click={() => { addingDevice = false; newDevice = mkDevice() }}>Cancel</button>
              <button class="btn-primary" on:click={commitDevice}
                disabled={!newDevice.name.trim() || !newDevice.bus}>Add Device</button>
            </div>
          </div>
        {/if}
      </div>

    <!-- ── Step 3: Telemetry ──────────────────────────────────────────── -->
    {:else if step === 3}

      <h2>Telemetry</h2>

      <div class="fields">
        <div class="toggle-row">
          <label class="toggle">
            <input type="checkbox" bind:checked={telemetry.enabled} />
            <span class="slider"></span>
          </label>
          <span>Enable sensor recording</span>
        </div>

        {#if telemetry.enabled}
          <div class="field">
            <label for="t-url">Database URL</label>
            <input id="t-url" bind:value={telemetry.db_url} />
            <span class="hint-inline">SQLite: <code>sqlite+aiosqlite:///data/station.db</code></span>
          </div>

          <div class="field-row">
            <div class="field narrow">
              <label for="t-int">Min interval (s)</label>
              <input id="t-int" type="number" bind:value={telemetry.min_interval_s} min="0.1" step="0.1" />
            </div>
            <div class="field narrow">
              <label for="t-sensor">Sensor retention (days)</label>
              <input id="t-sensor" type="number" bind:value={telemetry.retention_sensor_days} min="1" />
            </div>
            <div class="field narrow">
              <label for="t-events">Event retention (days)</label>
              <input id="t-events" type="number" bind:value={telemetry.retention_events_days} min="1" />
            </div>
          </div>

          <div class="toggle-row">
            <label class="toggle">
              <input type="checkbox" bind:checked={telemetry.dcn_logging} />
              <span class="slider"></span>
            </label>
            <span>Log raw DCN packets <span class="warn-label">(high I/O — debug only)</span></span>
          </div>
        {:else}
          <p class="hint">Telemetry disabled. Sensor history and the History page will be unavailable.</p>
        {/if}
      </div>

    <!-- ── Step 4: Auth ───────────────────────────────────────────────── -->
    {:else if step === 4}

      <h2>Authentication</h2>

      <div class="fields">
        <div class="toggle-row">
          <label class="toggle">
            <input type="checkbox" bind:checked={auth.enabled} />
            <span class="slider"></span>
          </label>
          <span>Require login to access the UI</span>
        </div>

        {#if auth.enabled}
          <div class="field-row">
            <div class="field narrow">
              <label for="a-exp">Token expiry (hours)</label>
              <input id="a-exp" type="number" bind:value={auth.token_expiry_hours} min="1" max="720" />
            </div>
          </div>

          <div class="toggle-row">
            <label class="toggle">
              <input type="checkbox" bind:checked={auth.secure_cookie} />
              <span class="slider"></span>
            </label>
            <span>Secure cookie <span class="hint-inline">(requires HTTPS — leave on when using the built-in TLS)</span></span>
          </div>

          <div class="section">
            <div class="section-hdr">
              <span class="section-title">Users</span>
            </div>

            {#each authUsers as u}
              <div class="item-row">
                <span class="item-name">{u}</span>
                <button class="btn-remove" on:click={() => deleteUser(u)}>×</button>
              </div>
            {/each}

            {#if !authUsers.length}
              <p class="empty warn-label">No users yet — add at least one before enabling auth.</p>
            {/if}

            <div class="inline-form">
              <div class="field-row">
                <div class="field grow">
                  <label>Username
                    <input bind:value={newUser.username} placeholder="admin" />
                  </label>
                </div>
                <div class="field grow">
                  <label>Password
                    <input type="password" bind:value={newUser.password} placeholder="••••••••" />
                  </label>
                </div>
                <div class="field" style="justify-content:flex-end;padding-top:1.1rem">
                  <button class="btn-primary" on:click={addUser}
                    disabled={addingUser || !newUser.username.trim() || !newUser.password}>
                    {addingUser ? '…' : 'Add User'}
                  </button>
                </div>
              </div>
              {#if userBanner}
                <div class="banner" class:ok={userBanner.ok}>{userBanner.text}</div>
              {/if}
            </div>
          </div>
        {:else}
          <p class="hint">Authentication disabled. Anyone on the network can access the UI.</p>
        {/if}
      </div>

    <!-- ── Step 5: Review & Save ──────────────────────────────────────── -->
    {:else if step === 5}

      <h2>Review &amp; Save</h2>
      <p class="hint">Check your settings below, then click <strong>Save All</strong>. Most changes require an app restart.</p>

      <div class="review-grid">
        <div class="review-card">
          <div class="rc-title">📻 Radio</div>
          {#if radioEnabled}
            <div class="rc-row"><span>Backend</span><strong>{radio.backend}</strong></div>
            {#if radio.backend === 'managed_rigctld'}
              <div class="rc-row"><span>Model ID</span><strong>{radio.model_id}</strong></div>
              <div class="rc-row"><span>Serial port</span><strong>{radio.serial_port}</strong></div>
              <div class="rc-row"><span>Baud</span><strong>{radio.serial_baud}</strong></div>
              <div class="rc-row"><span>TCP port</span><strong>{radio.port === 0 ? 'auto' : radio.port}</strong></div>
            {:else if radio.backend === 'rigctld'}
              <div class="rc-row"><span>Host</span><strong>{radio.host}:{radio.port}</strong></div>
              <div class="rc-row"><span>Timeout</span><strong>{radio.timeout_s}s</strong></div>
            {:else}
              <div class="rc-row"><span>Serial port</span><strong>{radio.port}</strong></div>
              <div class="rc-row"><span>Baud</span><strong>{radio.baud_rate}</strong></div>
            {/if}
            <div class="rc-row"><span>Poll</span><strong>{radio.poll_interval_s}s</strong></div>
          {:else}
            <div class="rc-disabled">Disabled</div>
          {/if}
        </div>

        <div class="review-card">
          <div class="rc-title">🔌 Communications</div>
          {#if buses.length}
            {#each buses as b}
              <div class="rc-row"><span>{b.name}</span><strong>{b.transport.type}</strong></div>
            {/each}
            <div class="rc-row"><span>Devices</span><strong>{devices.length}</strong></div>
          {:else}
            <div class="rc-disabled">No buses configured</div>
          {/if}
        </div>

        <div class="review-card">
          <div class="rc-title">📊 Telemetry</div>
          {#if telemetry.enabled}
            <div class="rc-row"><span>Database</span><strong style="font-size:0.78rem;word-break:break-all">{telemetry.db_url}</strong></div>
            <div class="rc-row"><span>Sensor retention</span><strong>{telemetry.retention_sensor_days} days</strong></div>
            <div class="rc-row"><span>Event retention</span><strong>{telemetry.retention_events_days} days</strong></div>
            <div class="rc-row"><span>DCN logging</span><strong>{telemetry.dcn_logging ? 'On' : 'Off'}</strong></div>
          {:else}
            <div class="rc-disabled">Disabled</div>
          {/if}
        </div>

        <div class="review-card">
          <div class="rc-title">🔒 Authentication</div>
          {#if auth.enabled}
            <div class="rc-row"><span>Users</span><strong>{authUsers.length}</strong></div>
            <div class="rc-row"><span>Token expiry</span><strong>{auth.token_expiry_hours}h</strong></div>
            <div class="rc-row"><span>Secure cookie</span><strong>{auth.secure_cookie ? 'Yes' : 'No'}</strong></div>
            {#if !authUsers.length}
              <div class="rc-warn">⚠ Enable auth requires at least one user</div>
            {/if}
          {:else}
            <div class="rc-disabled">Disabled</div>
          {/if}
        </div>
      </div>

      {#if banner}
        <div class="banner" class:ok={banner.ok}>{banner.text}</div>
      {/if}

    {/if}
  </div>

  <!-- ── Footer nav ─────────────────────────────────────────────────────── -->
  {#if !loading}
    <div class="footer">
      {#if isFirst}
        <!-- Welcome: no footer buttons — handled inside step content -->
      {:else if isLast}
        <button class="btn-secondary" on:click={() => step--}>← Back</button>
        <div class="spacer"></div>
        {#if banner?.ok && ondone}
          <button class="btn-secondary" on:click={ondone}>Exit wizard</button>
        {/if}
        <button class="btn-primary" on:click={saveAll} disabled={saving}>
          {saving ? 'Saving…' : 'Save All Configuration'}
        </button>
      {:else}
        {#if step > 1}
          <button class="btn-secondary" on:click={() => step--}>← Back</button>
        {/if}
        <div class="spacer"></div>
        <button class="btn-primary" on:click={() => step++}>Next →</button>
      {/if}
    </div>
  {/if}

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<style>
  .wizard {
    max-width: 760px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  /* ── Stepper ── */
  .stepper {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 0.5rem 0;
  }
  .step-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    background: none;
    border: none;
    cursor: default;
    padding: 0;
    flex-shrink: 0;
  }
  .step-node:not(:disabled) { cursor: pointer; }
  .node-circle {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    background: var(--surface);
    border: 2px solid var(--border);
    color: var(--text-muted);
    transition: background 0.2s, border-color 0.2s, color 0.2s;
  }
  .step-node.active .node-circle {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-dim);
  }
  .step-node.done .node-circle {
    border-color: var(--green);
    background: rgba(62,207,142,0.12);
    color: var(--green);
  }
  .node-label {
    font-size: 0.68rem;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .step-node.active .node-label { color: var(--accent); }
  .step-node.done  .node-label  { color: var(--green); }
  .step-line {
    flex: 1;
    height: 2px;
    background: var(--border);
    margin: 0 0.25rem;
    margin-bottom: 1.1rem;
    transition: background 0.2s;
  }
  .step-line.done { background: var(--green); }

  /* ── Body ── */
  .body {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.75rem;
    min-height: 340px;
  }
  .loading { color: var(--text-muted); font-size: 0.85rem; }

  h2 {
    margin: 0 0 1.25rem;
    font-size: 1.05rem;
    font-weight: 600;
  }

  /* ── Welcome ── */
  .welcome {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 1rem;
    padding: 0.5rem 0;
  }
  .welcome-icon { font-size: 2.5rem; line-height: 1; }
  .welcome h1 { margin: 0; font-size: 1.5rem; font-weight: 700; }
  .welcome-sub { color: var(--text-muted); font-size: 0.88rem; max-width: 480px; line-height: 1.6; margin: 0; }
  .module-cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
    width: 100%;
    max-width: 480px;
  }
  .mcard {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.6rem 0.8rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    text-align: left;
  }
  .mcard-icon { font-size: 1.3rem; flex-shrink: 0; }
  .mcard div { display: flex; flex-direction: column; gap: 0.15rem; }
  .mcard strong { font-size: 0.82rem; }
  .mcard span   { font-size: 0.72rem; color: var(--text-muted); }
  .welcome-actions { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; margin-top: 0.5rem; }

  /* ── Sections (comms) ── */
  .section { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 1.25rem; }
  .section:first-of-type { margin-top: 0; }
  .section-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.25rem;
  }
  .section-title {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  /* ── Item rows ── */
  .item-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.6rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 5px;
    font-size: 0.83rem;
  }
  .item-name   { font-weight: 600; min-width: 80px; }
  .item-detail { color: var(--text-muted); font-size: 0.78rem; flex: 1; }
  .badge {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    background: var(--accent-dim);
    color: var(--accent);
    flex-shrink: 0;
  }
  .btn-remove {
    margin-left: auto;
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 1rem;
    padding: 0 0.2rem;
    line-height: 1;
    flex-shrink: 0;
  }
  .btn-remove:hover { color: var(--red); }

  /* ── Inline forms ── */
  .inline-form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 0.75rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-top: 0.25rem;
  }
  .form-btns { display: flex; gap: 0.5rem; justify-content: flex-end; }

  /* ── Fields ── */
  .fields { display: flex; flex-direction: column; gap: 0.75rem; }
  .field  { display: flex; flex-direction: column; gap: 0.25rem; }
  .field-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .field.grow   { flex: 1; min-width: 140px; }
  .field.narrow { width: 130px; flex-shrink: 0; }

  label { font-size: 0.75rem; color: var(--text-muted); }

  input, select {
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    font-size: 0.85rem;
    width: 100%;
  }
  input:focus, select:focus { outline: none; border-color: var(--accent); }

  /* ── Toggle switch ── */
  .toggle-row { display: flex; align-items: center; gap: 0.65rem; font-size: 0.85rem; }
  .toggle { position: relative; display: inline-block; width: 36px; height: 20px; flex-shrink: 0; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; inset: 0;
    background: var(--border);
    border-radius: 20px;
    cursor: pointer;
    transition: background 0.2s;
  }
  .slider::before {
    content: '';
    position: absolute;
    width: 14px; height: 14px;
    left: 3px; top: 3px;
    background: var(--text-muted);
    border-radius: 50%;
    transition: transform 0.2s, background 0.2s;
  }
  .toggle input:checked + .slider { background: rgba(78,154,241,0.25); }
  .toggle input:checked + .slider::before { transform: translateX(16px); background: var(--accent); }

  /* ── Hint / empty ── */
  .hint, p.hint { font-size: 0.75rem; color: var(--text-muted); margin: 0; line-height: 1.5; }
  .hint code { font-family: monospace; font-size: 0.8em; background: var(--bg); padding: 0.1em 0.3em; border-radius: 3px; }
  .hint-inline { font-size: 0.72rem; color: var(--text-muted); }
  .hint-inline code { font-family: monospace; font-size: 0.85em; }
  .empty { font-size: 0.8rem; color: var(--text-muted); margin: 0.25rem 0; padding: 0.4rem 0.6rem; }
  .warn-label { color: #c8a04a; }

  /* ── Review grid ── */
  .review-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-top: 0.25rem;
  }
  .review-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.85rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .rc-title { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.25rem; }
  .rc-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 0.8rem;
    gap: 0.5rem;
  }
  .rc-row span  { color: var(--text-muted); flex-shrink: 0; }
  .rc-disabled  { font-size: 0.8rem; color: var(--text-muted); font-style: italic; }
  .rc-warn      { font-size: 0.75rem; color: #c8a04a; margin-top: 0.25rem; }

  /* ── Banners ── */
  .banner {
    padding: 0.45rem 0.7rem;
    border-radius: 5px;
    font-size: 0.82rem;
    background: rgba(233,98,98,0.1);
    color: var(--red);
    border: 1px solid rgba(233,98,98,0.25);
    margin-top: 0.5rem;
  }
  .banner.ok {
    background: rgba(62,207,142,0.1);
    color: var(--green);
    border-color: rgba(62,207,142,0.25);
  }

  /* ── Buttons ── */
  button {
    padding: 0.35rem 0.85rem;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.85rem;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }

  .btn-primary { border-color: var(--accent); color: var(--accent); }
  .btn-primary:not(:disabled):hover { background: var(--accent-dim); }
  .btn-secondary:not(:disabled):hover { background: var(--border); }
  .btn-ghost { background: none; border-color: transparent; color: var(--text-muted); font-size: 0.8rem; }
  .btn-ghost:hover { color: var(--text); }
  .btn-add {
    font-size: 0.75rem;
    padding: 0.2rem 0.6rem;
    color: var(--accent);
    border-color: var(--accent);
    background: transparent;
  }
  .btn-add:not(:disabled):hover { background: var(--accent-dim); }
  .btn-add:disabled { opacity: 0.35; cursor: not-allowed; }

  .large { padding: 0.5rem 1.5rem; font-size: 0.95rem; }

  /* ── Footer ── */
  .footer {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }
  .spacer { flex: 1; }

  /* ── Discovery / scan ── */
  .hdr-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .scan-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .scan-bus-sel {
    width: auto;
    min-width: 90px;
    font-size: 0.75rem;
    padding: 0.18rem 0.4rem;
    height: auto;
  }
  .btn-scan {
    font-size: 0.75rem;
    padding: 0.2rem 0.6rem;
    color: var(--text-muted);
    border-color: var(--border);
    white-space: nowrap;
  }
  .btn-scan:not(:disabled):hover { background: var(--border); color: var(--text); }
  .scan-results {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-top: 0.25rem;
  }
  .scan-header {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin: 0 0 0.1rem;
  }
  .scan-result-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0;
    border-top: 1px solid var(--border);
    font-size: 0.83rem;
  }
  .scan-result-row:first-of-type { border-top: none; }
  .scan-result-row.added { opacity: 0.6; }
  .scan-addr {
    font-family: monospace;
    font-weight: 700;
    min-width: 36px;
    color: var(--accent);
  }
  .scan-type { flex: 1; }
  .scan-tag {
    font-size: 0.7rem;
    color: var(--green);
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    background: rgba(62,207,142,0.12);
  }
</style>
