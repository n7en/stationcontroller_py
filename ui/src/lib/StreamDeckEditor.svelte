<script>
  import { onMount } from 'svelte'
  import { sensors, labels } from '../stores/ws.js'

  // ── State ─────────────────────────────────────────────────────────────────
  let cfg        = { streamdeck: { enabled: true, brightness: 70, buttons: [] } }
  let status     = { connected: false, available: false }
  let devices    = []
  let saving     = false
  let saveBanner = ''
  let loading    = true

  // Grid layout
  let rows = 3, cols = 5    // default Standard; updated from status
  $: keyCount = rows * cols
  $: buttons  = cfg.streamdeck?.buttons ?? []

  // Modal
  let editIdx    = null   // button index being edited, null = closed
  let editForm   = {}

  const TYPES = [
    { id: 'relay_toggle', label: 'Relay Toggle' },
    { id: 'coax_select',  label: 'Coax Port'    },
    { id: 'radio_tune',   label: 'Radio Tune'   },
  ]

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  onMount(async () => {
    await Promise.all([loadStatus(), loadConfig(), loadDevices()])
    loading = false
  })

  async function loadStatus() {
    try {
      const r = await fetch('/api/streamdeck/status')
      if (r.ok) {
        status = await r.json()
        if (status.rows) rows = status.rows
        if (status.cols) cols = status.cols
      }
    } catch {}
  }

  async function loadConfig() {
    try {
      const r = await fetch('/api/streamdeck/config')
      if (r.ok) cfg = await r.json()
    } catch {}
  }

  async function loadDevices() {
    try {
      const r = await fetch('/api/devices')
      if (r.ok) devices = (await r.json()).devices ?? []
    } catch {}
  }

  // ── Save ─────────────────────────────────────────────────────────────────
  async function save() {
    saving = true
    try {
      const r = await fetch('/api/streamdeck/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      saveBanner = 'Saved'
      setTimeout(() => saveBanner = '', 2000)
    } catch (e) {
      saveBanner = 'Save failed: ' + e.message
    } finally {
      saving = false
    }
  }

  // ── Grid helpers ──────────────────────────────────────────────────────────
  function btnAt(idx) {
    return buttons.find(b => b.index === idx) ?? null
  }

  function btnColor(btn) {
    if (!btn) return 'var(--surface)'
    if (btn.type === 'relay_toggle') return '#1e3a1e'
    if (btn.type === 'coax_select')  return '#1a2a4a'
    if (btn.type === 'radio_tune')   return '#2a1a4a'
    return 'var(--surface)'
  }

  function btnAccent(btn) {
    if (!btn) return 'var(--border)'
    if (btn.type === 'relay_toggle') return 'var(--green)'
    if (btn.type === 'coax_select')  return 'var(--accent)'
    if (btn.type === 'radio_tune')   return '#c792ea'
    return 'var(--border)'
  }

  function btnLine1(btn) {
    if (!btn) return ''
    return btn.label || btn.type
  }

  function btnLine2(btn) {
    if (!btn) return ''
    if (btn.type === 'relay_toggle') return `Relay ${(btn.relay_num ?? 0) + 1}`
    if (btn.type === 'coax_select')  return `Port ${(btn.port ?? 0) + 1}`
    if (btn.type === 'radio_tune') {
      const hz = btn.frequency_hz ?? 0
      const mhz = (hz / 1e6).toFixed(3).replace(/\.?0+$/, '')
      return `${mhz} ${btn.mode ?? ''}`
    }
    return ''
  }

  // ── Modal ────────────────────────────────────────────────────────────────
  function openEdit(idx) {
    editIdx  = idx
    const existing = btnAt(idx)
    editForm = existing
      ? JSON.parse(JSON.stringify(existing))
      : { index: idx, type: 'relay_toggle', label: '', device_addr: '01', bus: 'control', relay_num: 0, sensor_key: '', port: 0, frequency_hz: 14225000, mode: 'USB', radio_name: '' }
  }

  function closeModal() { editIdx = null }

  function clearButton() {
    cfg = {
      ...cfg,
      streamdeck: {
        ...cfg.streamdeck,
        buttons: (cfg.streamdeck?.buttons ?? []).filter(b => b.index !== editIdx),
      },
    }
    closeModal()
  }

  function applyEdit() {
    const b = { ...editForm, index: editIdx }
    const rest = (cfg.streamdeck?.buttons ?? []).filter(x => x.index !== editIdx)
    cfg = {
      ...cfg,
      streamdeck: { ...cfg.streamdeck, buttons: [...rest, b] },
    }
    closeModal()
  }

  // ── Sensor / device helpers ───────────────────────────────────────────────
  $: sensorKeys = Object.keys($sensors).sort()
  $: relaySensors = sensorKeys.filter(k => k.toLowerCase().includes('relay'))
  $: coaxSensors  = sensorKeys.filter(k => k.toLowerCase().includes('port') || k.toLowerCase().includes('coax'))

  $: relayDevices = devices.filter(d =>
    (d.sensors ?? []).some(s => s.role === 'relay') || d.type === 'antenna_relay' || d.type === 'vhf_relay'
  )
  $: coaxDevices  = devices.filter(d => d.type === 'coax_switch')

  $: busNames = [...new Set(devices.map(d => d.bus).filter(Boolean))].sort()
</script>

<div class="sd-editor">

  <!-- ── Header ─────────────────────────────────────────────────────────── -->
  <div class="header">
    <div class="header-left">
      <div class="status-dot" class:ok={status.connected} title={status.connected ? 'Device connected' : 'No device detected'}></div>
      <span class="status-lbl">
        {#if status.connected}
          {status.model} · {status.key_count} keys
        {:else}
          No Stream Deck detected
        {/if}
      </span>
    </div>
    <div class="header-right">
      {#if saveBanner}
        <span class="banner">{saveBanner}</span>
      {/if}
      <label class="brightness-row">
        <span>Brightness</span>
        <input type="range" min="0" max="100"
          bind:value={cfg.streamdeck.brightness}
          class="brightness-slider"
        />
        <span class="brightness-val">{cfg.streamdeck.brightness}%</span>
      </label>
      <button class="btn-save" on:click={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  </div>

  {#if loading}
    <div class="loading">Loading…</div>
  {:else}

    <!-- ── Layout selector ──────────────────────────────────────────────── -->
    <div class="layout-bar">
      <span class="layout-lbl">Layout:</span>
      {#each [{label:'Mini (3×2)', r:2, c:3},{label:'Standard (5×3)', r:3, c:5},{label:'XL (8×4)', r:4, c:8}] as lay}
        <button
          class="layout-btn"
          class:active={rows === lay.r && cols === lay.c}
          on:click={() => { rows = lay.r; cols = lay.c }}
        >{lay.label}</button>
      {/each}
    </div>

    <!-- ── Key grid ──────────────────────────────────────────────────────── -->
    <div class="key-grid" style="--cols:{cols}">
      {#each Array(keyCount) as _, idx}
        {@const btn = btnAt(idx)}
        <button
          class="key-cell"
          class:assigned={!!btn}
          style="background:{btnColor(btn)}; --accent:{btnAccent(btn)}"
          on:click={() => openEdit(idx)}
          title="Button {idx}{btn ? ' — ' + btn.type : ' (empty)'}"
        >
          {#if btn}
            <span class="key-l1">{btnLine1(btn)}</span>
            <span class="key-l2">{btnLine2(btn)}</span>
          {:else}
            <span class="key-empty">{idx}</span>
          {/if}
        </button>
      {/each}
    </div>

    <!-- ── Legend ────────────────────────────────────────────────────────── -->
    <div class="legend">
      <span class="leg-item relay">Relay Toggle</span>
      <span class="leg-item coax">Coax Port</span>
      <span class="leg-item radio">Radio Tune</span>
    </div>

  {/if}
</div>

<!-- ── Edit modal ─────────────────────────────────────────────────────────── -->
{#if editIdx !== null}
  <div class="modal-backdrop" role="presentation"
    on:click|self={closeModal}
    on:keydown={e => e.key === 'Escape' && closeModal()}
  >
    <div class="modal">
      <div class="modal-header">
        <span>Button {editIdx}</span>
        <button class="close-btn" on:click={closeModal}>✕</button>
      </div>

      <div class="modal-body">
        <!-- Type selector -->
        <div class="type-row">
          {#each TYPES as t}
            <button
              class="type-btn"
              class:active={editForm.type === t.id}
              on:click={() => editForm = { ...editForm, type: t.id }}
            >{t.label}</button>
          {/each}
        </div>

        <!-- Label (all types) -->
        <label class="field">
          <span>Label</span>
          <input bind:value={editForm.label} placeholder="Button label" />
        </label>

        <!-- ── Relay Toggle ── -->
        {#if editForm.type === 'relay_toggle'}
          <label class="field">
            <span>Sensor key</span>
            <select bind:value={editForm.sensor_key}>
              <option value="">— pick a relay sensor —</option>
              {#each relaySensors as k}
                <option value={k}>{$labels[k] ?? k}</option>
              {/each}
              {#each sensorKeys.filter(k => !relaySensors.includes(k)) as k}
                <option value={k}>{$labels[k] ?? k}</option>
              {/each}
            </select>
          </label>
          <div class="field-row">
            <label class="field">
              <span>Device addr</span>
              <input bind:value={editForm.device_addr} placeholder="01" />
            </label>
            <label class="field">
              <span>Bus</span>
              <select bind:value={editForm.bus}>
                {#each busNames as b}<option value={b}>{b}</option>{/each}
                <option value="">control</option>
              </select>
            </label>
            <label class="field">
              <span>Relay # (0-based)</span>
              <input type="number" min="0" bind:value={editForm.relay_num} />
            </label>
          </div>

        <!-- ── Coax Select ── -->
        {:else if editForm.type === 'coax_select'}
          <label class="field">
            <span>Active port sensor key</span>
            <select bind:value={editForm.sensor_key}>
              <option value="">— pick a coax sensor —</option>
              {#each coaxSensors as k}
                <option value={k}>{$labels[k] ?? k}</option>
              {/each}
              {#each sensorKeys.filter(k => !coaxSensors.includes(k)) as k}
                <option value={k}>{$labels[k] ?? k}</option>
              {/each}
            </select>
          </label>
          <div class="field-row">
            <label class="field">
              <span>Device addr</span>
              <input bind:value={editForm.device_addr} placeholder="02" />
            </label>
            <label class="field">
              <span>Bus</span>
              <select bind:value={editForm.bus}>
                {#each busNames as b}<option value={b}>{b}</option>{/each}
                <option value="">control</option>
              </select>
            </label>
            <label class="field">
              <span>Port # (0-based)</span>
              <input type="number" min="0" bind:value={editForm.port} />
            </label>
          </div>

        <!-- ── Radio Tune ── -->
        {:else if editForm.type === 'radio_tune'}
          <div class="field-row">
            <label class="field">
              <span>Frequency (Hz)</span>
              <input type="number" bind:value={editForm.frequency_hz} step="1000" />
            </label>
            <label class="field">
              <span>Mode</span>
              <select bind:value={editForm.mode}>
                {#each ['USB','LSB','AM','FM','CW','CWR','RTTY','RTTYR','PKTUSB','PKTLSB','PKTFM'] as m}
                  <option value={m}>{m}</option>
                {/each}
              </select>
            </label>
          </div>
          <label class="field">
            <span>Radio name (blank = primary)</span>
            <input bind:value={editForm.radio_name} placeholder="" />
          </label>
        {/if}
      </div>

      <div class="modal-footer">
        <button class="btn-clear" on:click={clearButton}>Clear</button>
        <div style="flex:1"></div>
        <button class="btn-cancel" on:click={closeModal}>Cancel</button>
        <button class="btn-apply" on:click={applyEdit}>Apply</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .sd-editor { display: flex; flex-direction: column; gap: 0.75rem; }

  /* ── Header ── */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 0.5rem;
  }
  .header-left { display: flex; align-items: center; gap: 0.5rem; }
  .header-right { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }

  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--border); flex-shrink: 0;
    transition: background 0.3s;
  }
  .status-dot.ok { background: var(--green); }
  .status-lbl { font-size: 0.78rem; color: var(--text-muted); }

  .banner { font-size: 0.75rem; color: var(--green); }

  .brightness-row { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--text-muted); }
  .brightness-slider { width: 80px; accent-color: var(--accent); }
  .brightness-val { min-width: 3ch; }

  .btn-save {
    padding: 0.3rem 0.9rem;
    background: var(--accent); color: #fff;
    border: none; border-radius: 4px;
    font-size: 0.78rem; font-weight: 600; cursor: pointer;
  }
  .btn-save:disabled { opacity: 0.5; }
  .btn-save:hover:not(:disabled) { opacity: 0.88; }

  /* ── Layout bar ── */
  .loading { color: var(--text-muted); font-size: 0.82rem; padding: 2rem; text-align: center; }
  .layout-bar { display: flex; align-items: center; gap: 0.3rem; }
  .layout-lbl { font-size: 0.72rem; color: var(--text-muted); margin-right: 0.2rem; }
  .layout-btn {
    padding: 0.22rem 0.6rem;
    border: 1px solid var(--border); border-radius: 4px;
    background: transparent; color: var(--text-muted);
    font-size: 0.72rem; cursor: pointer;
  }
  .layout-btn:hover  { background: var(--border); color: var(--text); }
  .layout-btn.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

  /* ── Key grid ── */
  .key-grid {
    display: grid;
    grid-template-columns: repeat(var(--cols, 5), 1fr);
    gap: 6px;
    max-width: 600px;
  }

  .key-cell {
    aspect-ratio: 1;
    border-radius: 6px;
    border: 1px solid var(--border);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 0.15rem;
    cursor: pointer;
    transition: border-color 0.12s, filter 0.12s;
    padding: 4px;
  }
  .key-cell:hover { filter: brightness(1.2); }
  .key-cell.assigned { border-color: var(--accent); }

  .key-empty { font-size: 0.65rem; color: var(--border); }
  .key-l1 {
    font-size: 0.62rem; font-weight: 600;
    color: var(--text); text-align: center;
    overflow: hidden; width: 100%;
    text-overflow: ellipsis; white-space: nowrap;
  }
  .key-l2 {
    font-size: 0.6rem; color: var(--text-muted);
    text-align: center; overflow: hidden;
    width: 100%; text-overflow: ellipsis; white-space: nowrap;
  }

  /* ── Legend ── */
  .legend { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .leg-item {
    font-size: 0.68rem;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    border-left: 3px solid;
  }
  .leg-item.relay  { background: #1e3a1e; border-color: var(--green);  color: var(--green); }
  .leg-item.coax   { background: #1a2a4a; border-color: var(--accent); color: var(--accent); }
  .leg-item.radio  { background: #2a1a4a; border-color: #c792ea;       color: #c792ea; }

  /* ── Modal ── */
  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.65);
    display: flex; align-items: center; justify-content: center;
    z-index: 200;
  }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; width: min(480px, 95vw);
    display: flex; flex-direction: column;
    max-height: 85vh; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .modal-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.65rem 1rem; border-bottom: 1px solid var(--border);
    font-size: 0.85rem; font-weight: 600;
  }
  .close-btn {
    background: none; border: none; color: var(--text-muted);
    cursor: pointer; font-size: 0.9rem; padding: 0.1rem 0.3rem;
  }
  .close-btn:hover { color: var(--text); }

  .modal-body {
    flex: 1; overflow-y: auto;
    padding: 0.75rem 1rem;
    display: flex; flex-direction: column; gap: 0.6rem;
  }

  /* Type buttons */
  .type-row { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .type-btn {
    padding: 0.28rem 0.7rem;
    border: 1px solid var(--border); border-radius: 5px;
    background: transparent; color: var(--text-muted);
    font-size: 0.78rem; cursor: pointer;
  }
  .type-btn:hover        { background: var(--border); color: var(--text); }
  .type-btn.active       { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

  /* Fields */
  .field {
    display: flex; flex-direction: column; gap: 0.2rem;
    font-size: 0.74rem; color: var(--text-muted);
  }
  .field input, .field select {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 4px; color: var(--text);
    padding: 0.32rem 0.5rem; font-size: 0.82rem;
  }
  .field input:focus, .field select:focus { outline: none; border-color: var(--accent); }
  .field-row { display: flex; gap: 0.5rem; }
  .field-row .field { flex: 1; }

  .modal-footer {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.65rem 1rem; border-top: 1px solid var(--border);
  }
  .btn-clear {
    background: none; border: 1px solid var(--border); border-radius: 4px;
    color: var(--red); font-size: 0.78rem; padding: 0.32rem 0.7rem; cursor: pointer;
  }
  .btn-clear:hover { border-color: var(--red); }
  .btn-cancel {
    background: none; border: 1px solid var(--border); border-radius: 4px;
    color: var(--text-muted); font-size: 0.78rem; padding: 0.32rem 0.7rem; cursor: pointer;
  }
  .btn-cancel:hover { color: var(--text); }
  .btn-apply {
    background: var(--accent); border: none; border-radius: 4px;
    color: #fff; font-size: 0.78rem; font-weight: 600;
    padding: 0.32rem 0.9rem; cursor: pointer;
  }
  .btn-apply:hover { opacity: 0.88; }
</style>
