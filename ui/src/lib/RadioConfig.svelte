<script>
  import { onMount } from 'svelte'
  import { radios } from '../stores/ws.js'
  import SerialPortPicker from './SerialPortPicker.svelte'

  /** @type {{radios: any[]}|null} */
  let config      = null
  let loading     = true
  let saving      = false
  let banner      = null   // { ok: bool, text: str }
  let editIdx     = -1     // index into config.radios being edited; config.radios.length = new
  /** @type {any} */
  let editEntry   = null   // working copy

  /** @type {{port: string, description: string}[]} */
  let serialPorts = []

  const BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

  /** Extract the serial port string from a radio config entry, or '' if it uses TCP/network. */
  function radioSerialPort(r) {
    if (r.backend === 'managed_rigctld') return r.serial_port || ''
    if (r.backend === 'hamlib_direct')   return r.port || ''
    if (r.backend === 'elecraft_k4' && r.transport !== 'tcp') return r.port || ''
    return ''
  }

  /** Port strings used by radios other than the one currently being edited. */
  $: usedSerialPorts = (config?.radios ?? [])
    .filter((_, idx) => idx !== editIdx)
    .map(radioSerialPort)
    .filter(Boolean)

  onMount(async () => {
    await loadConfig()
    try {
      const r = await fetch('/api/radio/serial-ports')
      if (r.ok) {
        const d = await r.json()
        serialPorts = d.ports ?? []
      }
    } catch (_) {}
  })

  async function loadConfig() {
    loading = true
    banner  = null
    try {
      const r = await fetch('/api/radio/config')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      if (!data.radios || data.radios.length === 0) {
        data.radios = [defaultEntry()]
      }
      config = data
    } catch (e) {
      banner = { ok: false, text: `Failed to load config: ${e.message}` }
      config = { radios: [defaultEntry()] }
    }
    loading = false
  }

  function defaultEntry() {
    return {
      name: 'radio',
      backend: 'managed_rigctld',
      model_id: 351,
      serial_port: '',
      serial_baud: 9600,
      host: '127.0.0.1',
      port: 0,
      startup_timeout_s: 10.0,
      serial_timeout_ms: 500,
      timeout_s: 15.0,
      poll_interval_s: 1.0,
      reconnect_delay_s: 5.0,
    }
  }

  function startEdit(i) {
    editIdx   = i
    editEntry = i < (config?.radios.length ?? 0)
      ? { ...config.radios[i] }
      : defaultEntry()
  }

  function cancelEdit() {
    editIdx   = -1
    editEntry = null
  }

  function applyEdit() {
    if (!config || !editEntry) return
    if (editIdx < config.radios.length) {
      config.radios[editIdx] = { ...editEntry }
    } else {
      config.radios = [...config.radios, { ...editEntry }]
    }
    editIdx   = -1
    editEntry = null
    config = config
  }

  function removeRadio(i) {
    if (!config) return
    if (config.radios.length <= 1) {
      banner = { ok: false, text: 'Cannot remove the last radio.' }
      return
    }
    config.radios = config.radios.filter((_, idx) => idx !== i)
    if (editIdx === i) cancelEdit()
    else if (editIdx > i) editIdx--
    config = config
  }

  function switchBackend(backend) {
    if (!editEntry) return
    const shared = {
      name:              editEntry.name,
      backend,
      poll_interval_s:   editEntry.poll_interval_s   ?? 1.0,
      reconnect_delay_s: editEntry.reconnect_delay_s ?? 5.0,
    }
    if (backend === 'managed_rigctld') {
      editEntry = { ...shared,
        model_id:          editEntry.model_id ?? 351,
        serial_port:       editEntry.serial_port ?? editEntry.port ?? '',
        serial_baud:       editEntry.serial_baud ?? editEntry.baud_rate ?? 9600,
        host:              '127.0.0.1',
        port:              0,
        startup_timeout_s: editEntry.startup_timeout_s ?? 10.0,
        serial_timeout_ms: editEntry.serial_timeout_ms ?? 500,
        timeout_s:         editEntry.timeout_s ?? 15.0,
      }
    } else if (backend === 'rigctld') {
      editEntry = { ...shared,
        host:      editEntry.host ?? 'localhost',
        port:      editEntry.port || 4532,
        timeout_s: editEntry.timeout_s ?? 15.0,
      }
    } else if (backend === 'hamlib_direct') {
      editEntry = { ...shared,
        model_id:  editEntry.model_id ?? 1,
        port:      editEntry.serial_port ?? editEntry.port ?? '',
        baud_rate: editEntry.serial_baud ?? editEntry.baud_rate ?? 9600,
        data_bits: editEntry.data_bits ?? 8,
        stop_bits: editEntry.stop_bits ?? 1,
        parity:    editEntry.parity    ?? 'N',
      }
    } else if (backend === 'elecraft_k4') {
      editEntry = { ...shared,
        transport:   editEntry.transport   ?? 'serial',
        port:        editEntry.port ?? editEntry.serial_port ?? '',
        baud_rate:   editEntry.baud_rate   ?? 38400,
        host:        editEntry.host        ?? '',
        tcp_port:    editEntry.tcp_port    ?? 9204,
        password:    editEntry.password    ?? '',
        timeout_s:   editEntry.timeout_s   ?? 5.0,
        max_power_w: editEntry.max_power_w ?? 100,
        power_range: editEntry.power_range ?? 'H',
      }
    }
  }

  async function save() {
    saving = true; banner = null
    try {
      const r = await fetch('/api/radio/config', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(config),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail ?? `HTTP ${r.status}`)
      banner = {
        ok:   true,
        text: d.reconnected
          ? 'Saved and reconnected.'
          : 'Saved. Changing backend type or device port requires an app restart.',
      }
    } catch (e) {
      banner = { ok: false, text: e.message }
    }
    saving = false
  }

  /** @param {any} rs */
  function fmtStatus(rs) {
    if (!rs?.connected) return 'Disconnected'
    let s = 'Connected'
    if (rs.frequency_hz) s += ` · ${(rs.frequency_hz / 1e6).toFixed(3)} MHz`
    if (rs.mode) s += ` · ${rs.mode}`
    return s
  }
</script>

<div class="radio-cfg">
  <div class="header-row">
    <h2>Radio Configuration</h2>
    {#if config && editIdx === -1}
      <button class="btn-add" on:click={() => startEdit(config.radios.length)}>+ Add Radio</button>
    {/if}
  </div>

  {#if loading}
    <div class="msg">Loading…</div>

  {:else if config}
    <div class="radio-list">

      {#each config.radios as radio, i (i)}
        {@const liveState = $radios[radio.name]}
        <div class="radio-row" class:editing={editIdx === i}>
          <span class="dot" class:online={liveState?.connected}></span>
          <span class="radio-name">{radio.name}</span>
          <span class="radio-backend">{radio.backend}</span>
          <span class="radio-status" class:online={liveState?.connected}>
            {fmtStatus(liveState)}
          </span>
          <div class="row-btns">
            <button on:click={() => editIdx === i ? cancelEdit() : startEdit(i)}>
              {editIdx === i ? 'Cancel' : 'Edit'}
            </button>
            <button class="btn-danger"
                    on:click={() => removeRadio(i)}
                    disabled={config.radios.length <= 1}>
              Remove
            </button>
          </div>
        </div>

        {#if editIdx === i}
          <div class="edit-form">

            <div class="field">
              <label>Name<input bind:value={editEntry.name} placeholder="ic7300" /></label>
            </div>

            <div class="field">
              <label>Backend
                <select value={editEntry.backend}
                        on:change={e => switchBackend(e.currentTarget.value)}>
                  <option value="managed_rigctld">managed rigctld (auto-start, recommended)</option>
                  <option value="rigctld">rigctld (connect to running daemon)</option>
                  <option value="hamlib_direct">hamlib direct (Python bindings)</option>
                  <option value="elecraft_k4">Elecraft K4 (native CAT)</option>
                </select>
              </label>
            </div>

            {#if editEntry.backend === 'managed_rigctld'}
              <div class="field-row">
                <div class="field narrow">
                  <label>Model ID
                    <input type="number" bind:value={editEntry.model_id} min="1" placeholder="351" />
                  </label>
                </div>
                <div class="field grow">
                  <label>Serial port
                    <SerialPortPicker bind:value={editEntry.serial_port} ports={serialPorts} usedPorts={usedSerialPorts} />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Baud rate
                    <select bind:value={editEntry.serial_baud}>
                      {#each BAUD_RATES as b}
                        <option value={b}>{b}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field grow">
                  <label>rigctld host
                    <input bind:value={editEntry.host} placeholder="127.0.0.1" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port (0 = auto)
                    <input type="number" bind:value={editEntry.port} min="0" max="65535" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Startup timeout (s)
                    <input type="number" bind:value={editEntry.startup_timeout_s} min="1" max="60" step="1" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Serial read timeout (ms)
                    <input type="number" bind:value={editEntry.serial_timeout_ms} min="1" max="5000" step="50" />
                  </label>
                </div>
              </div>
              <p class="hint">
                Model IDs: 351 = IC-7300 · 135 = FT-991A · 122 = IC-7610 ·
                <a href="https://hamlib.sourceforge.net/manuals/4.5/supported_radios.html"
                   target="_blank" rel="noopener">full list ↗</a>
              </p>
            {/if}

            {#if editEntry.backend === 'rigctld'}
              <div class="field-row">
                <div class="field grow">
                  <label>Host
                    <input bind:value={editEntry.host} placeholder="localhost" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Port
                    <input type="number" bind:value={editEntry.port} min="1" max="65535" />
                  </label>
                </div>
              </div>
              <p class="hint">
                Start the daemon first:
                <code>rigctld -m &lt;model&gt; -r &lt;device&gt; -s &lt;baud&gt;</code>
              </p>
            {/if}

            {#if editEntry.backend === 'hamlib_direct'}
              <div class="field-row">
                <div class="field narrow">
                  <label>Model ID
                    <input type="number" bind:value={editEntry.model_id} min="1" placeholder="351" />
                  </label>
                </div>
                <div class="field grow">
                  <label>Device port
                    <SerialPortPicker bind:value={editEntry.port} ports={serialPorts} usedPorts={usedSerialPorts} />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Baud rate
                    <select bind:value={editEntry.baud_rate}>
                      {#each BAUD_RATES as b}
                        <option value={b}>{b}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              </div>
              <div class="field-row">
                <div class="field narrow">
                  <label>Data bits
                    <input type="number" bind:value={editEntry.data_bits} min="7" max="8" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Stop bits
                    <input type="number" bind:value={editEntry.stop_bits} min="1" max="2" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Parity
                    <select bind:value={editEntry.parity}>
                      <option value="N">None</option>
                      <option value="E">Even</option>
                      <option value="O">Odd</option>
                    </select>
                  </label>
                </div>
              </div>
              <p class="hint">
                Model IDs: 1 = Dummy · 351 = IC-7300 · 135 = FT-991A ·
                <a href="https://hamlib.sourceforge.net/manuals/4.5/supported_radios.html"
                   target="_blank" rel="noopener">full list ↗</a>
              </p>
            {/if}

            {#if editEntry.backend === 'elecraft_k4'}
              <div class="field">
                <label>Transport
                  <select bind:value={editEntry.transport}>
                    <option value="serial">Serial (USB / RS-232)</option>
                    <option value="tcp">Ethernet (TCP)</option>
                  </select>
                </label>
              </div>
              {#if editEntry.transport === 'tcp'}
                <div class="field-row">
                  <div class="field grow">
                    <label>K4 IP address
                      <input bind:value={editEntry.host} placeholder="192.168.1.100" />
                    </label>
                  </div>
                  <div class="field narrow">
                    <label>TCP port
                      <input type="number" bind:value={editEntry.tcp_port} min="1" max="65535" />
                    </label>
                  </div>
                </div>
                <div class="field">
                  <label>Password (optional)
                    <input bind:value={editEntry.password} placeholder="leave blank if RRP not set" />
                  </label>
                </div>
              {:else}
                <div class="field-row">
                  <div class="field grow">
                    <label>Serial port
                      <SerialPortPicker bind:value={editEntry.port} ports={serialPorts} usedPorts={usedSerialPorts}
                                        placeholder="COM3  or  /dev/ttyACM0" />
                    </label>
                  </div>
                  <div class="field narrow">
                    <label>Baud rate
                      <select bind:value={editEntry.baud_rate}>
                        {#each BAUD_RATES as b}
                          <option value={b}>{b}</option>
                        {/each}
                      </select>
                    </label>
                  </div>
                </div>
              {/if}
              <div class="field-row">
                <div class="field narrow">
                  <label>Max power (W)
                    <input type="number" bind:value={editEntry.max_power_w} min="1" max="200" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Power range
                    <select bind:value={editEntry.power_range}>
                      <option value="H">H — High (100 W)</option>
                      <option value="L">L — QRP (10 W)</option>
                    </select>
                  </label>
                </div>
              </div>
              <p class="hint">
                Set TCP port on the K4: Front Panel → Config → Network.
                Baud rate must match Front Panel → XCVR → KIO3 CAT.
              </p>
            {/if}

            <!-- Shared timing fields -->
            <div class="field-row">
              <div class="field narrow">
                <label>Poll interval (s)
                  <input type="number" bind:value={editEntry.poll_interval_s}
                         min="0.1" max="10" step="0.1" />
                </label>
              </div>
              <div class="field narrow">
                <label>Reconnect delay (s)
                  <input type="number" bind:value={editEntry.reconnect_delay_s}
                         min="1" max="120" step="1" />
                </label>
              </div>
              {#if editEntry.backend !== 'hamlib_direct'}
                <div class="field narrow">
                  <label>Timeout (s)
                    <input type="number" bind:value={editEntry.timeout_s}
                           min="1" max="60" step="1" />
                  </label>
                </div>
              {/if}
            </div>

            <div class="form-actions">
              <button class="btn-primary" on:click={applyEdit}>
                {editIdx < config.radios.length ? 'Apply' : 'Add'}
              </button>
              <button on:click={cancelEdit}>Cancel</button>
            </div>
          </div>
        {/if}
      {/each}

      <!-- New radio form (editIdx === config.radios.length) -->
      {#if editIdx === config.radios.length}
        <div class="edit-form new-radio">
          <div class="new-radio-title">New Radio</div>

          <div class="field">
            <label>Name<input bind:value={editEntry.name} placeholder="ic7300" /></label>
          </div>

          <div class="field">
            <label>Backend
              <select value={editEntry.backend}
                      on:change={e => switchBackend(e.currentTarget.value)}>
                <option value="managed_rigctld">managed rigctld (auto-start, recommended)</option>
                <option value="rigctld">rigctld (connect to running daemon)</option>
                <option value="hamlib_direct">hamlib direct (Python bindings)</option>
                <option value="elecraft_k4">Elecraft K4 (native CAT)</option>
              </select>
            </label>
          </div>

          {#if editEntry.backend === 'managed_rigctld'}
            <div class="field-row">
              <div class="field narrow">
                <label>Model ID
                  <input type="number" bind:value={editEntry.model_id} min="1" placeholder="351" />
                </label>
              </div>
              <div class="field grow">
                <label>Serial port
                  <SerialPortPicker bind:value={editEntry.serial_port} ports={serialPorts} usedPorts={usedSerialPorts} />
                </label>
              </div>
              <div class="field narrow">
                <label>Baud rate
                  <select bind:value={editEntry.serial_baud}>
                    {#each BAUD_RATES as b}
                      <option value={b}>{b}</option>
                    {/each}
                  </select>
                </label>
              </div>
            </div>
            <div class="field-row">
              <div class="field grow">
                <label>rigctld host
                  <input bind:value={editEntry.host} placeholder="127.0.0.1" />
                </label>
              </div>
              <div class="field narrow">
                <label>Port (0 = auto)
                  <input type="number" bind:value={editEntry.port} min="0" max="65535" />
                </label>
              </div>
              <div class="field narrow">
                <label>Startup timeout (s)
                  <input type="number" bind:value={editEntry.startup_timeout_s} min="1" max="60" step="1" />
                </label>
              </div>
              <div class="field narrow">
                <label>Serial read timeout (ms)
                  <input type="number" bind:value={editEntry.serial_timeout_ms} min="1" max="5000" step="50" />
                </label>
              </div>
            </div>
            <p class="hint">
              Model IDs: 351 = IC-7300 · 135 = FT-991A · 122 = IC-7610 ·
              <a href="https://hamlib.sourceforge.net/manuals/4.5/supported_radios.html"
                 target="_blank" rel="noopener">full list ↗</a>
            </p>
          {/if}

          {#if editEntry.backend === 'rigctld'}
            <div class="field-row">
              <div class="field grow">
                <label>Host
                  <input bind:value={editEntry.host} placeholder="localhost" />
                </label>
              </div>
              <div class="field narrow">
                <label>Port
                  <input type="number" bind:value={editEntry.port} min="1" max="65535" />
                </label>
              </div>
            </div>
            <p class="hint">
              Start the daemon first:
              <code>rigctld -m &lt;model&gt; -r &lt;device&gt; -s &lt;baud&gt;</code>
            </p>
          {/if}

          {#if editEntry.backend === 'hamlib_direct'}
            <div class="field-row">
              <div class="field narrow">
                <label>Model ID
                  <input type="number" bind:value={editEntry.model_id} min="1" placeholder="351" />
                </label>
              </div>
              <div class="field grow">
                <label>Device port
                  <SerialPortPicker bind:value={editEntry.port} ports={serialPorts} usedPorts={usedSerialPorts} />
                </label>
              </div>
              <div class="field narrow">
                <label>Baud rate
                  <select bind:value={editEntry.baud_rate}>
                    {#each BAUD_RATES as b}
                      <option value={b}>{b}</option>
                    {/each}
                  </select>
                </label>
              </div>
            </div>
            <div class="field-row">
              <div class="field narrow">
                <label>Data bits
                  <input type="number" bind:value={editEntry.data_bits} min="7" max="8" />
                </label>
              </div>
              <div class="field narrow">
                <label>Stop bits
                  <input type="number" bind:value={editEntry.stop_bits} min="1" max="2" />
                </label>
              </div>
              <div class="field narrow">
                <label>Parity
                  <select bind:value={editEntry.parity}>
                    <option value="N">None</option>
                    <option value="E">Even</option>
                    <option value="O">Odd</option>
                  </select>
                </label>
              </div>
            </div>
            <p class="hint">
              Model IDs: 1 = Dummy · 351 = IC-7300 · 135 = FT-991A ·
              <a href="https://hamlib.sourceforge.net/manuals/4.5/supported_radios.html"
                 target="_blank" rel="noopener">full list ↗</a>
            </p>
          {/if}

          {#if editEntry.backend === 'elecraft_k4'}
            <div class="field">
              <label>Transport
                <select bind:value={editEntry.transport}>
                  <option value="serial">Serial (USB / RS-232)</option>
                  <option value="tcp">Ethernet (TCP)</option>
                </select>
              </label>
            </div>
            {#if editEntry.transport === 'tcp'}
              <div class="field-row">
                <div class="field grow">
                  <label>K4 IP address
                    <input bind:value={editEntry.host} placeholder="192.168.1.100" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>TCP port
                    <input type="number" bind:value={editEntry.tcp_port} min="1" max="65535" />
                  </label>
                </div>
              </div>
              <div class="field">
                <label>Password (optional)
                  <input bind:value={editEntry.password} placeholder="leave blank if RRP not set" />
                </label>
              </div>
            {:else}
              <div class="field-row">
                <div class="field grow">
                  <label>Serial port
                    <SerialPortPicker bind:value={editEntry.port} ports={serialPorts} usedPorts={usedSerialPorts}
                                      placeholder="COM3  or  /dev/ttyACM0" />
                  </label>
                </div>
                <div class="field narrow">
                  <label>Baud rate
                    <select bind:value={editEntry.baud_rate}>
                      {#each BAUD_RATES as b}
                        <option value={b}>{b}</option>
                      {/each}
                    </select>
                  </label>
                </div>
              </div>
            {/if}
            <div class="field-row">
              <div class="field narrow">
                <label>Max power (W)
                  <input type="number" bind:value={editEntry.max_power_w} min="1" max="200" />
                </label>
              </div>
              <div class="field narrow">
                <label>Power range
                  <select bind:value={editEntry.power_range}>
                    <option value="H">H — High (100 W)</option>
                    <option value="L">L — QRP (10 W)</option>
                  </select>
                </label>
              </div>
            </div>
            <p class="hint">
              Set TCP port on the K4: Front Panel → Config → Network.
              Baud rate must match Front Panel → XCVR → KIO3 CAT.
            </p>
          {/if}

          <div class="field-row">
            <div class="field narrow">
              <label>Poll interval (s)
                <input type="number" bind:value={editEntry.poll_interval_s}
                       min="0.1" max="10" step="0.1" />
              </label>
            </div>
            <div class="field narrow">
              <label>Reconnect delay (s)
                <input type="number" bind:value={editEntry.reconnect_delay_s}
                       min="1" max="120" step="1" />
              </label>
            </div>
            {#if editEntry.backend !== 'hamlib_direct'}
              <div class="field narrow">
                <label>Timeout (s)
                  <input type="number" bind:value={editEntry.timeout_s}
                         min="1" max="60" step="1" />
                </label>
              </div>
            {/if}
          </div>

          <div class="form-actions">
            <button class="btn-primary" on:click={applyEdit}>Add</button>
            <button on:click={cancelEdit}>Cancel</button>
          </div>
        </div>
      {/if}
    </div>

    {#if banner}
      <div class="banner" class:ok={banner.ok}>{banner.text}</div>
    {/if}

    <div class="save-row">
      <button class="btn-primary" on:click={save}
              disabled={saving || editIdx !== -1}>
        {saving ? 'Saving…' : 'Save & Apply'}
      </button>
      <span class="save-hint">
        {editIdx !== -1 ? 'Apply or cancel the open edit first.' : 'Saves all radios and reconnects.'}
      </span>
    </div>
  {/if}
</div>

<style>
  .radio-cfg { max-width: 700px; display: flex; flex-direction: column; gap: 1rem; }
  h2 { margin: 0; font-size: 1.1rem; }

  .header-row { display: flex; align-items: center; justify-content: space-between; }

  /* ── Radio list ── */
  .radio-list { display: flex; flex-direction: column; gap: 0.5rem; }

  .radio-row {
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
    padding: 0.5rem 0.7rem;
    border-radius: 6px;
    background: var(--surface);
    border: 1px solid var(--border);
  }
  .radio-row.editing { border-color: var(--accent); }

  .dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    background: var(--text-muted);
    transition: background 0.3s;
  }
  .dot.online { background: var(--green); box-shadow: 0 0 5px var(--green); }

  .radio-name  { font-weight: 600; font-size: 0.9rem; min-width: 80px; }
  .radio-backend { font-size: 0.75rem; color: var(--text-muted); flex: 1; }

  .radio-status { font-size: 0.78rem; color: var(--text-muted); }
  .radio-status.online { color: var(--green); }

  .row-btns { display: flex; gap: 0.4rem; margin-left: auto; }

  /* ── Edit form ── */
  .edit-form {
    padding: 0.9rem 1rem;
    background: var(--bg);
    border: 1px solid var(--accent);
    border-radius: 6px;
    display: flex; flex-direction: column; gap: 0.65rem;
  }
  .new-radio { border-color: var(--border); }
  .new-radio-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 0.1rem; }

  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .field.grow   { flex: 1; min-width: 160px; }
  .field.narrow { width: 130px; flex-shrink: 0; }

  label {
    font-size: 0.75rem; color: var(--text-muted);
    display: flex; flex-direction: column; gap: 0.2rem;
  }

  input, select {
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    font-size: 0.85rem;
    width: 100%;
    box-sizing: border-box;
  }
  input:focus, select:focus { outline: none; border-color: var(--accent); }

  .hint {
    font-size: 0.75rem; color: var(--text-muted); margin: -0.2rem 0 0; line-height: 1.5;
  }
  .hint a { color: var(--accent); }
  .hint code {
    font-family: monospace; font-size: 0.8em;
    background: var(--surface); padding: 0.1em 0.3em; border-radius: 3px;
  }

  .form-actions { display: flex; gap: 0.5rem; padding-top: 0.1rem; }

  /* ── Save row ── */
  .save-row { display: flex; align-items: center; gap: 0.75rem; }
  .save-hint { font-size: 0.75rem; color: var(--text-muted); }

  /* ── Banner ── */
  .banner {
    padding: 0.4rem 0.6rem; border-radius: 4px; font-size: 0.82rem;
    background: rgba(233, 98, 98, 0.12); color: var(--red);
    border: 1px solid rgba(233, 98, 98, 0.3);
  }
  .banner.ok {
    background: rgba(62, 207, 142, 0.1); color: var(--green);
    border-color: rgba(62, 207, 142, 0.25);
  }

  /* ── Buttons ── */
  button {
    padding: 0.3rem 0.75rem; border-radius: 5px; cursor: pointer;
    font-size: 0.82rem; border: 1px solid var(--border);
    background: var(--surface); color: var(--text);
    transition: background 0.15s, border-color 0.15s;
    white-space: nowrap;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { border-color: var(--accent); color: var(--accent); }
  .btn-primary:not(:disabled):hover { background: var(--accent-dim); }
  .btn-add { border-color: var(--accent); color: var(--accent); }
  .btn-add:not(:disabled):hover { background: var(--accent-dim); }
  .btn-danger { color: var(--red); border-color: rgba(233,98,98,0.4); }
  .btn-danger:not(:disabled):hover { background: rgba(233,98,98,0.1); }
  button:not(.btn-primary):not(.btn-add):not(.btn-danger):not(:disabled):hover { background: var(--border); }

  .msg { color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0; }
</style>
