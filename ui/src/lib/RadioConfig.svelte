<script>
  import { onMount } from 'svelte'
  import { radio } from '../stores/ws.js'

  let config      = null   // { radios: [...] }
  let loading     = true
  let saving      = false
  let reconnecting= false
  let banner      = null   // { ok: bool, text: str }

  onMount(loadConfig)

  async function loadConfig() {
    loading = true
    banner  = null
    try {
      const r = await fetch('/api/radio/config')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      // Ensure there is at least one radio entry with defaults
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
      backend: 'rigctld',
      host: 'localhost',
      port: 4532,
      poll_interval_s: 0.5,
      reconnect_delay_s: 5.0,
    }
  }

  // Switch backend — clear backend-specific keys and set new defaults
  function switchBackend(evt) {
    const backend = evt.target.value
    const current = config.radios[0]
    const shared  = {
      name:               current.name,
      backend,
      poll_interval_s:    current.poll_interval_s ?? 0.5,
      reconnect_delay_s:  current.reconnect_delay_s ?? 5.0,
    }
    config.radios[0] = backend === 'rigctld'
      ? { ...shared, host: 'localhost', port: 4532 }
      : { ...shared, model_id: 1, port: '', baud_rate: 9600,
          data_bits: 8, stop_bits: 1, parity: 'N' }
    config = config   // trigger reactivity
  }

  $: r0 = config?.radios?.[0]

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

  async function reconnect() {
    reconnecting = true; banner = null
    try {
      const r = await fetch('/api/radio/reconnect', { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail ?? `HTTP ${r.status}`)
      banner = {
        ok:   true,
        text: d.connected ? 'Reconnected.' : 'Reconnect attempted — radio may be offline.',
      }
    } catch (e) {
      banner = { ok: false, text: e.message }
    }
    reconnecting = false
  }
</script>

<div class="radio-cfg">
  <h2>Radio Configuration</h2>

  <!-- Live status bar -->
  <div class="status-bar" class:online={$radio?.connected}>
    <span class="status-dot"></span>
    <span class="status-text">
      {#if $radio?.connected}
        Connected
        {#if $radio.frequency_hz}
          · {($radio.frequency_hz / 1e6).toFixed(3)} MHz
        {/if}
        {#if $radio.mode}· {$radio.mode}{/if}
      {:else}
        Disconnected
      {/if}
    </span>
  </div>

  {#if loading}
    <div class="msg">Loading…</div>

  {:else if r0}
    <form on:submit|preventDefault={save}>

      <!-- Name -->
      <div class="field">
        <label for="r-name">Name</label>
        <input id="r-name" bind:value={config.radios[0].name} />
      </div>

      <!-- Backend selector -->
      <div class="field">
        <label for="r-backend">Backend</label>
        <select id="r-backend" value={r0.backend} on:change={switchBackend}>
          <option value="rigctld">rigctld  (recommended — connects to a running rigctld daemon)</option>
          <option value="hamlib_direct">hamlib direct  (Python bindings, local serial port)</option>
        </select>
      </div>

      {#if r0.backend === 'rigctld'}
        <div class="field-row">
          <div class="field grow">
            <label for="r-host">Host</label>
            <input id="r-host" bind:value={config.radios[0].host} placeholder="localhost" />
          </div>
          <div class="field narrow">
            <label for="r-port">Port</label>
            <input id="r-port" type="number" bind:value={config.radios[0].port}
                   min="1" max="65535" />
          </div>
        </div>
        <p class="hint">
          Start the daemon first:
          <code>rigctld -m &lt;model&gt; -r &lt;device&gt; -s &lt;baud&gt;</code>
        </p>
      {/if}

      {#if r0.backend === 'hamlib_direct'}
        <div class="field-row">
          <div class="field narrow">
            <label for="r-model">Model ID</label>
            <input id="r-model" type="number" bind:value={config.radios[0].model_id}
                   min="1" placeholder="351" />
          </div>
          <div class="field grow">
            <label for="r-dev">Device port</label>
            <input id="r-dev" bind:value={config.radios[0].port}
                   placeholder="COM3  or  /dev/ttyUSB0" />
          </div>
        </div>
        <div class="field-row">
          <div class="field narrow">
            <label for="r-baud">Baud rate</label>
            <input id="r-baud" type="number" bind:value={config.radios[0].baud_rate} />
          </div>
          <div class="field narrow">
            <label for="r-data">Data bits</label>
            <input id="r-data" type="number" bind:value={config.radios[0].data_bits}
                   min="7" max="8" />
          </div>
          <div class="field narrow">
            <label for="r-stop">Stop bits</label>
            <input id="r-stop" type="number" bind:value={config.radios[0].stop_bits}
                   min="1" max="2" />
          </div>
          <div class="field narrow">
            <label for="r-par">Parity</label>
            <select id="r-par" bind:value={config.radios[0].parity}>
              <option value="N">None</option>
              <option value="E">Even</option>
              <option value="O">Odd</option>
            </select>
          </div>
        </div>
        <p class="hint">
          Model IDs: 1 = Dummy · 351 = IC-7300 · 135 = FT-991A ·
          <a href="https://hamlib.sourceforge.net/manuals/4.5/supported_radios.html"
             target="_blank" rel="noopener">full list ↗</a>
        </p>
      {/if}

      <!-- Shared timing -->
      <div class="field-row">
        <div class="field narrow">
          <label for="r-poll">Poll interval (s)</label>
          <input id="r-poll" type="number" bind:value={config.radios[0].poll_interval_s}
                 min="0.1" max="10" step="0.1" />
        </div>
        <div class="field narrow">
          <label for="r-recon">Reconnect delay (s)</label>
          <input id="r-recon" type="number" bind:value={config.radios[0].reconnect_delay_s}
                 min="1" max="120" step="1" />
        </div>
      </div>

      {#if banner}
        <div class="banner" class:ok={banner.ok}>{banner.text}</div>
      {/if}

      <div class="actions">
        <button type="submit" class="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save & Reconnect'}
        </button>
        <button type="button" class="btn-secondary" on:click={reconnect}
                disabled={reconnecting}>
          {reconnecting ? 'Reconnecting…' : 'Reconnect only'}
        </button>
      </div>
    </form>
  {/if}
</div>

<style>
  .radio-cfg { max-width: 600px; }
  h2 { margin: 0 0 1rem; font-size: 1.1rem; }

  .status-bar {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.4rem 0.7rem;
    border-radius: 5px;
    background: var(--surface);
    margin-bottom: 1.25rem;
    font-size: 0.82rem;
    color: var(--text-muted);
  }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--text-muted); flex-shrink: 0;
    transition: background 0.3s;
  }
  .status-bar.online .status-dot  { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .status-bar.online .status-text { color: var(--green); }

  form { display: flex; flex-direction: column; gap: 0.75rem; }

  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .field.grow   { flex: 1; min-width: 160px; }
  .field.narrow { width: 120px; flex-shrink: 0; }

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
  input:focus, select:focus {
    outline: none;
    border-color: var(--accent);
  }

  .hint {
    font-size: 0.75rem; color: var(--text-muted);
    margin: -0.25rem 0 0;
    line-height: 1.5;
  }
  .hint a { color: var(--accent); }
  .hint code {
    font-family: monospace; font-size: 0.8em;
    background: var(--bg); padding: 0.1em 0.3em; border-radius: 3px;
  }

  .banner {
    padding: 0.4rem 0.6rem;
    border-radius: 4px;
    font-size: 0.82rem;
    background: rgba(233, 98, 98, 0.12);
    color: var(--red);
    border: 1px solid rgba(233, 98, 98, 0.3);
  }
  .banner.ok {
    background: rgba(62, 207, 142, 0.1);
    color: var(--green);
    border-color: rgba(62, 207, 142, 0.25);
  }

  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }

  button {
    padding: 0.35rem 0.85rem;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.85rem;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    transition: background 0.15s, border-color 0.15s;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { border-color: var(--accent); color: var(--accent); }
  .btn-primary:not(:disabled):hover { background: var(--accent-dim); }
  .btn-secondary:not(:disabled):hover { background: var(--border); }

  .msg { color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0; }
</style>
