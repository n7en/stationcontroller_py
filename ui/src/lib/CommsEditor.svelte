<script>
  import { onMount } from 'svelte'
  import SerialPortPicker from './SerialPortPicker.svelte'

  let buses   = []
  let devices = []
  let loading = true
  let saving  = false
  let banner  = null

  /** @type {{port: string, description: string}[]} */
  let serialPorts = []

  /** RS-485 port strings in use by buses other than the one being edited. */
  $: usedBusPorts = buses
    .filter((_, idx) => idx !== editingBusIdx)
    .filter(b => b.transport.type === 'rs485')
    .map(b => b.transport.port)
    .filter(Boolean)

  let editingBusIdx    = null
  let editingDeviceIdx = null
  let addingBus        = false
  let addingDevice     = false

  let editBus    = null
  let editDevice = null
  let newBus     = mkBus()
  let newDevice  = mkDevice()

  function mkBus() {
    return {
      name: '',
      enabled: true,
      transport: {
        type: 'rs485',
        enabled: true,
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

  onMount(async () => {
    await loadAll()
    try {
      const r = await fetch('/api/radio/serial-ports')
      if (r.ok) {
        const d = await r.json()
        serialPorts = d.ports ?? []
      }
    } catch (_) {}
  })

  async function loadAll() {
    loading = true; banner = null
    try {
      const r = await fetch('/api/config/comms/json')
      if (r.ok) {
        const d = await r.json()
        buses = (d.buses ?? []).map(b => {
          const t = b.transports?.[0] ?? {}
          return {
            name:    b.name,
            enabled: b.enabled ?? true,
            transport: {
              type:      t.type      ?? 'rs485',
              enabled:   t.enabled   ?? true,
              port:      t.port      ?? '',
              baud_rate: t.baud_rate ?? 9600,
              broker:    t.broker    ?? 'localhost',
              port_mqtt: t.port      ?? 1883,
              topic_rx:  t.topic_rx  ?? `dcn/${b.name}/rx`,
              topic_tx:  t.topic_tx  ?? `dcn/${b.name}/tx`,
              username:  t.username  ?? '',
              password:  t.password  ?? '',
              host:      t.host      ?? '0.0.0.0',
              port_tcp:  t.port      ?? 4880,
            },
          }
        })
        devices = (d.devices ?? []).map(dev => ({
          type:    dev.type,
          name:    dev.name,
          address: dev.address,
          bus:     dev.bus,
          persona: dev.persona ?? 'cc_8a',
        }))
      }
    } catch (e) { console.error('CommsEditor load error:', e) }
    loading = false
  }

  // ── Bus CRUD ───────────────────────────────────────────────────────────────

  function startEditBus(i) {
    editingBusIdx    = i
    editingDeviceIdx = null
    addingBus        = false
    editBus          = JSON.parse(JSON.stringify(buses[i]))
  }

  function cancelEditBus() { editingBusIdx = null; editBus = null }

  function commitEditBus() {
    if (!editBus.name.trim()) return
    const cur = buses[editingBusIdx]
    const updated = {
      ...editBus,
      name:      editBus.name.trim(),
      enabled:   cur.enabled,
      transport: { ...editBus.transport, enabled: cur.transport.enabled },
    }
    const oldName = cur.name
    buses = buses.map((b, idx) => idx === editingBusIdx ? updated : b)
    if (oldName !== updated.name)
      devices = devices.map(d => d.bus === oldName ? { ...d, bus: updated.name } : d)
    editingBusIdx = null; editBus = null
  }

  function removeBus(i) {
    const name = buses[i].name
    buses   = buses.filter((_, idx) => idx !== i)
    devices = devices.filter(d => d.bus !== name)
    if (editingBusIdx === i) { editingBusIdx = null; editBus = null }
  }

  function commitBus() {
    if (!newBus.name.trim()) return
    const t = newBus.transport
    buses = [...buses, {
      name:    newBus.name.trim(),
      enabled: true,
      transport: {
        ...t,
        topic_rx: t.topic_rx || `dcn/${newBus.name.trim()}/rx`,
        topic_tx: t.topic_tx || `dcn/${newBus.name.trim()}/tx`,
      },
    }]
    newBus = mkBus(); addingBus = false
  }

  function toggleBus(i) {
    buses = buses.map((b, idx) => idx === i ? { ...b, enabled: !b.enabled } : b)
  }

  function toggleTransport(i) {
    buses = buses.map((b, idx) => idx === i
      ? { ...b, transport: { ...b.transport, enabled: !b.transport.enabled } }
      : b)
  }

  // ── Device CRUD ────────────────────────────────────────────────────────────

  function startEditDevice(i) {
    editingDeviceIdx = i
    editingBusIdx    = null
    addingDevice     = false
    editDevice       = { ...devices[i] }
  }

  function cancelEditDevice() { editingDeviceIdx = null; editDevice = null }

  function commitEditDevice() {
    if (!editDevice.name.trim() || !editDevice.bus) return
    devices = devices.map((d, idx) => idx === editingDeviceIdx ? { ...editDevice } : d)
    editingDeviceIdx = null; editDevice = null
  }

  function removeDevice(i) {
    devices = devices.filter((_, idx) => idx !== i)
    if (editingDeviceIdx === i) { editingDeviceIdx = null; editDevice = null }
  }

  function commitDevice() {
    if (!newDevice.name.trim() || !newDevice.bus) return
    devices = [...devices, { ...newDevice }]
    newDevice = mkDevice(); addingDevice = false
  }

  $: busNames = buses.map(b => b.name)

  // ── Save ───────────────────────────────────────────────────────────────────

  function buildCommsYaml() {
    const L = ['buses:']
    for (const bus of buses) {
      const t = bus.transport
      L.push('', `  - name: ${bus.name}`)
      if (!bus.enabled) L.push('    enabled: false')
      L.push('    transports:',
             `      - name: ${bus.name}_${t.type}`, `        type: ${t.type}`)
      if (!t.enabled) L.push('        enabled: false')
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

  async function save() {
    saving = true; banner = null
    const r = await fetch('/api/config/comms', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: buildCommsYaml() }),
    })
    saving = false
    banner = r.ok
      ? { ok: true,  text: 'Saved. Restart the app to apply changes.' }
      : { ok: false, text: 'Save failed — check application logs.' }
  }
</script>

<!-- ═══════════════════════════════════════════════════════════════════════ -->

<div class="comms-editor">

  <div class="editor-header">
    <div>
      <div class="editor-title">DCN Networks &amp; Devices</div>
      <div class="editor-sub">Buses define how the app connects to hardware. Devices are the modules on those buses.</div>
    </div>
    <button class="btn-save" on:click={save} disabled={saving || loading}>
      {saving ? 'Saving…' : 'Save'}
    </button>
  </div>

  {#if banner}
    <div class="banner" class:ok={banner.ok}>{banner.text}</div>
  {/if}

  {#if loading}
    <p class="loading">Loading configuration…</p>
  {:else}

    <!-- ── Buses ─────────────────────────────────────────────────────────── -->
    <div class="section">
      <div class="section-hdr">
        <span class="section-title">Buses</span>
        <button class="btn-add"
          on:click={() => { addingBus = !addingBus; editingBusIdx = null; editBus = null }}>
          {addingBus ? '− Cancel' : '+ Add Bus'}
        </button>
      </div>

      {#each buses as bus, i (bus.name + i)}

        {#if editingBusIdx === i && editBus}
          <div class="inline-form">
            <div class="field-row">
              <div class="field grow">
                <label>Bus name
                  <input bind:value={editBus.name} />
                </label>
              </div>
              <div class="field narrow">
                <label>Transport
                  <select bind:value={editBus.transport.type}>
                    <option value="rs485">RS-485</option>
                    <option value="nodered_mqtt">MQTT</option>
                    <option value="nodered_tcp">TCP</option>
                  </select>
                </label>
              </div>
            </div>

            {#if editBus.transport.type === 'rs485'}
              <div class="field-row">
                <div class="field grow">
                  <label>Serial port
                    <SerialPortPicker bind:value={editBus.transport.port} ports={serialPorts} usedPorts={usedBusPorts}
                                      placeholder="COM3 or /dev/ttyUSB0" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Baud rate
                    <select bind:value={editBus.transport.baud_rate}>
                      {#each [1200,2400,4800,9600,19200,38400,57600,115200] as b}
                        <option value={b}>{b}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              </div>
            {:else if editBus.transport.type === 'nodered_mqtt'}
              <div class="field-row">
                <div class="field grow">
                  <label>Broker
                    <input bind:value={editBus.transport.broker} />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port
                    <input type="number" bind:value={editBus.transport.port_mqtt} />
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field grow">
                  <label>RX topic
                    <input bind:value={editBus.transport.topic_rx} />
                  </label>
                </div>
                <div class="field grow">
                  <label>TX topic
                    <input bind:value={editBus.transport.topic_tx} />
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field grow">
                  <label>Username (optional)
                    <input bind:value={editBus.transport.username} />
                  </label>
                </div>
                <div class="field grow">
                  <label>Password (optional)
                    <input type="password" bind:value={editBus.transport.password} />
                  </label>
                </div>
              </div>
            {:else if editBus.transport.type === 'nodered_tcp'}
              <div class="field-row">
                <div class="field grow">
                  <label>Listen host
                    <input bind:value={editBus.transport.host} />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port
                    <input type="number" bind:value={editBus.transport.port_tcp} />
                  </label>
                </div>
              </div>
            {/if}

            <div class="form-btns">
              <button class="btn-secondary" on:click={cancelEditBus}>Cancel</button>
              <button class="btn-primary" on:click={commitEditBus}
                disabled={!editBus.name.trim()}>Save Bus</button>
            </div>
          </div>

        {:else}
          <div class="item-row" class:disabled={!bus.enabled}>
            <button class="toggle-switch" class:on={bus.enabled}
              title={bus.enabled ? 'Bus enabled — click to disable' : 'Bus disabled — click to enable'}
              on:click={() => toggleBus(i)}>
              <span class="toggle-knob"></span>
            </button>
            <span class="item-name">{bus.name}</span>
            <span class="badge">{bus.transport.type}</span>
            {#if bus.transport.type === 'rs485'}
              <span class="item-detail">{bus.transport.port || '—'} · {bus.transport.baud_rate} baud</span>
            {:else if bus.transport.type === 'nodered_mqtt'}
              <span class="item-detail">{bus.transport.broker}:{bus.transport.port_mqtt}</span>
            {:else}
              <span class="item-detail">{bus.transport.host}:{bus.transport.port_tcp}</span>
            {/if}
            <span class="transport-lbl">transport</span>
            <button class="toggle-switch toggle-sm" class:on={bus.transport.enabled}
              title={bus.transport.enabled ? 'Transport enabled — click to disable' : 'Transport disabled — click to enable'}
              on:click={() => toggleTransport(i)}>
              <span class="toggle-knob"></span>
            </button>
            <button class="btn-icon" title="Edit" on:click={() => startEditBus(i)}>✎</button>
            <button class="btn-remove" title="Remove" on:click={() => removeBus(i)}>×</button>
          </div>
        {/if}

      {/each}

      {#if !buses.length && !addingBus}
        <p class="empty">No buses configured. Add one to connect hardware to the app.</p>
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
                  <SerialPortPicker bind:value={newBus.transport.port} ports={serialPorts} usedPorts={usedBusPorts}
                                    placeholder="COM3 or /dev/ttyUSB0" />
                </label>
              </div>
              <div class="field narrow">
                <label>Baud rate
                  <select bind:value={newBus.transport.baud_rate}>
                    {#each [1200,2400,4800,9600,19200,38400,57600,115200] as b}
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
            <button class="btn-primary" on:click={commitBus}
              disabled={!newBus.name.trim()}>Add Bus</button>
          </div>
        </div>
      {/if}
    </div>

    <!-- ── Devices ───────────────────────────────────────────────────────── -->
    <div class="section">
      <div class="section-hdr">
        <span class="section-title">Devices</span>
        <button class="btn-add" disabled={!buses.length}
          on:click={() => {
            addingDevice = !addingDevice
            editingDeviceIdx = null; editDevice = null
            if (busNames[0] && !newDevice.bus) newDevice.bus = busNames[0]
          }}>
          {addingDevice ? '− Cancel' : '+ Add Device'}
        </button>
      </div>

      {#each devices as dev, i (i)}

        {#if editingDeviceIdx === i && editDevice}
          <div class="inline-form">
            <div class="field-row">
              <div class="field narrow">
                <label>Type
                  <select bind:value={editDevice.type}>
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
                  <input bind:value={editDevice.name} />
                </label>
              </div>
            </div>
            <div class="field-row">
              <div class="field narrow">
                <label>Address (hex)
                  <input bind:value={editDevice.address} maxlength="2" />
                </label>
              </div>
              <div class="field grow">
                <label>Bus
                  <select bind:value={editDevice.bus}>
                    {#each busNames as b}
                      <option value={b}>{b}</option>
                    {/each}
                  </select>
                </label>
              </div>
            </div>
            {#if editDevice.type === 'antenna_relay'}
              <div class="field">
                <label>Persona
                  <select bind:value={editDevice.persona}>
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
              <button class="btn-secondary" on:click={cancelEditDevice}>Cancel</button>
              <button class="btn-primary" on:click={commitEditDevice}
                disabled={!editDevice.name.trim() || !editDevice.bus}>Save Device</button>
            </div>
          </div>

        {:else}
          <div class="item-row">
            <span class="item-name">{dev.name}</span>
            <span class="badge">{dev.type}</span>
            <span class="item-detail">addr {dev.address} · {dev.bus}</span>
            {#if dev.type === 'antenna_relay'}
              <span class="item-detail-sm">{dev.persona}</span>
            {/if}
            <button class="btn-icon" title="Edit" on:click={() => startEditDevice(i)}>✎</button>
            <button class="btn-remove" title="Remove" on:click={() => removeDevice(i)}>×</button>
          </div>
        {/if}

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
            <button class="btn-secondary"
              on:click={() => { addingDevice = false; newDevice = mkDevice() }}>Cancel</button>
            <button class="btn-primary" on:click={commitDevice}
              disabled={!newDevice.name.trim() || !newDevice.bus}>Add Device</button>
          </div>
        </div>
      {/if}
    </div>

  {/if}
</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<style>
  .comms-editor {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    max-width: 760px;
  }

  /* ── Header ── */
  .editor-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  .editor-title { font-size: 1rem; font-weight: 600; margin-bottom: 0.2rem; }
  .editor-sub   { font-size: 0.78rem; color: var(--text-muted); }

  /* ── Section ── */
  .section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
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
    font-weight: 600;
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
  .item-name    { font-weight: 600; min-width: 80px; }
  .item-detail  { color: var(--text-muted); font-size: 0.78rem; flex: 1; }
  .item-detail-sm { color: var(--text-muted); font-size: 0.72rem; font-style: italic; }
  .badge {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    background: var(--accent-dim);
    color: var(--accent);
    flex-shrink: 0;
  }

  /* ── Inline form ── */
  .inline-form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 0.75rem;
    background: var(--bg);
    border: 1px solid var(--accent);
    border-radius: 6px;
  }
  .form-btns { display: flex; gap: 0.5rem; justify-content: flex-end; }

  /* ── Fields ── */
  .field-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .field     { display: flex; flex-direction: column; gap: 0.25rem; }
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

  /* ── Misc ── */
  .loading, .empty {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin: 0.25rem 0;
    padding: 0.4rem 0.6rem;
  }

  .banner {
    padding: 0.45rem 0.7rem;
    border-radius: 5px;
    font-size: 0.82rem;
    background: rgba(233,98,98,0.1);
    color: var(--red);
    border: 1px solid rgba(233,98,98,0.25);
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

  .btn-save {
    flex-shrink: 0;
    padding: 0.4rem 1.25rem;
    border-color: var(--accent);
    color: var(--accent);
  }
  .btn-save:not(:disabled):hover { background: var(--accent-dim); }

  .btn-primary { border-color: var(--accent); color: var(--accent); }
  .btn-primary:not(:disabled):hover { background: var(--accent-dim); }

  .btn-secondary:not(:disabled):hover { background: var(--border); }

  .btn-add {
    font-size: 0.75rem;
    padding: 0.2rem 0.6rem;
    color: var(--accent);
    border-color: var(--accent);
    background: transparent;
  }
  .btn-add:not(:disabled):hover { background: var(--accent-dim); }
  .btn-add:disabled { opacity: 0.35; cursor: not-allowed; }

  .btn-icon {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0 0.25rem;
    line-height: 1;
    flex-shrink: 0;
  }
  .btn-icon:hover { color: var(--accent); }

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

  .item-row.disabled { opacity: 0.45; }

  /* ── Pill toggle (matches RadioConfig style) ── */
  .toggle-switch {
    position: relative;
    width: 36px; height: 20px;
    padding: 0; border: none;
    border-radius: 10px;
    background: var(--border);
    cursor: pointer;
    transition: background 0.2s;
    flex-shrink: 0;
  }
  .toggle-switch.on { background: var(--green); }
  .toggle-switch.toggle-sm { width: 28px; height: 16px; border-radius: 8px; }
  .toggle-knob {
    position: absolute;
    top: 3px; left: 3px;
    width: 14px; height: 14px;
    border-radius: 50%;
    background: #fff;
    transition: left 0.2s;
    pointer-events: none;
  }
  .toggle-switch.on .toggle-knob { left: 19px; }
  .toggle-switch.toggle-sm .toggle-knob { width: 10px; height: 10px; }
  .toggle-switch.toggle-sm.on .toggle-knob { left: 15px; }

  .transport-lbl {
    font-size: 0.68rem;
    color: var(--text-muted);
    flex-shrink: 0;
    margin-left: auto;
  }
</style>
