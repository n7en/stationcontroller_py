<script>
  import { onMount } from 'svelte'
  import { sensors, labels, radio } from '../stores/ws.js'
  import DashboardCard from './DashboardCard.svelte'

  export let dashboardId = 'main'

  let config  = { cards: [] }
  let error   = null
  let loading = true
  let editMode  = false
  let saving    = false
  let saveBanner = ''

  // Drag-and-drop state
  let dragIdx = null
  let dropIdx = null

  // Card picker state
  let showPicker  = false
  let editingIdx  = null   // null = new card, number = editing existing
  let pickerType  = 'radio_status'
  let pickerConfig = {}

  const CARD_TYPES = [
    { id: 'radio_status', label: 'Radio Status' },
    { id: 'sensor',       label: 'Sensor Value' },
    { id: 'relay',        label: 'Relay Button' },
    { id: 'power_meter',  label: 'Power Meter'  },
    { id: 'swr_bar',      label: 'SWR Bar'      },
    { id: 'blank',        label: 'Blank Space'  },
  ]

  onMount(async () => {
    loading = true
    try {
      const r = await fetch(`/api/dashboards/${dashboardId}`)
      if (r.ok) {
        const d = await r.json()
        config = { cards: [], ...d }
      } else if (r.status === 404) {
        config = { cards: [] }
      } else {
        throw new Error(`HTTP ${r.status}`)
      }
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })

  async function save() {
    saving = true
    try {
      const r = await fetch(`/api/dashboards/${dashboardId}`, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(config),
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

  function toggleEdit() {
    if (editMode) save()
    editMode   = !editMode
    showPicker = false
  }

  // ── Drag-and-drop ─────────────────────────────────────────────────────────
  function onDragStart(e, i) {
    dragIdx = i
    e.dataTransfer.effectAllowed = 'move'
  }
  function onDragOver(e, i) {
    if (dragIdx === null) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    dropIdx = i
  }
  function onDrop(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) { dragIdx = dropIdx = null; return }
    const cards = [...config.cards]
    const [moved] = cards.splice(dragIdx, 1)
    // After removing dragIdx, indices above it shift down by 1.
    // Compensate so the card lands before the originally-targeted position.
    const insertAt = i > dragIdx ? i - 1 : i
    cards.splice(insertAt, 0, moved)
    config  = { ...config, cards }
    dragIdx = null
    dropIdx = null
  }
  function onDragEnd() { dragIdx = null; dropIdx = null }

  // ── Card operations ───────────────────────────────────────────────────────
  function removeCard(i) {
    config = { ...config, cards: config.cards.filter((_, idx) => idx !== i) }
  }

  function setSpan(i, span) {
    const cards = [...config.cards]
    if (span === 1) {
      const { span: _s, ...rest } = cards[i]
      cards[i] = rest
    } else {
      cards[i] = { ...cards[i], span }
    }
    config = { ...config, cards }
  }

  function setRowSpan(i, rows) {
    const cards = [...config.cards]
    if (rows === 1) {
      const { row_span: _r, ...rest } = cards[i]
      cards[i] = rest
    } else {
      cards[i] = { ...cards[i], row_span: rows }
    }
    config = { ...config, cards }
  }

  function parseBoard(card) {
    if (card.type === 'radio_status') return 'Radio'
    const key = card.sensor || card.relay_key || ''
    if (key.startsWith('watt_meter')) return 'Watt Meter'
    if (key.startsWith('gpio_'))      return 'GPIO'
    const seg = key.split('_')[0]
    return seg ? seg.charAt(0).toUpperCase() + seg.slice(1) : '—'
  }

  // ── Card picker ───────────────────────────────────────────────────────────
  function openPicker(idx = null) {
    editingIdx = idx
    if (idx !== null) {
      const c = config.cards[idx]
      pickerType   = c.type
      pickerConfig = JSON.parse(JSON.stringify(c))
    } else {
      pickerType   = 'radio_status'
      pickerConfig = mkDefault('radio_status')
    }
    showPicker = true
  }

  function mkDefault(type) {
    switch (type) {
      case 'radio_status': return { type, span: 2, row_span: 3 }
      case 'sensor':       return { type, title: '', sensor: '', unit: '' }
      case 'relay':        return { type, title: '', relay_key: '', device_addr: '01', relay_num: 1 }
      case 'power_meter':  return { type, title: 'Power', sensor: '', max_w: 1500, row_span: 2 }
      case 'swr_bar':      return { type, title: 'SWR', sensor: '', span: 2,
                                    thresholds: { good: 1.5, warning: 2.0, critical: 3.0 } }
      case 'blank':        return { type }
      default: return { type }
    }
  }

  function onPickerTypeChange(type) {
    const oldTitle = pickerConfig.title
    pickerConfig = { ...mkDefault(type), title: oldTitle ?? '' }
    pickerType   = type
  }

  function commitPicker() {
    const card  = { ...pickerConfig, type: pickerType }
    const cards = [...config.cards]
    if (editingIdx !== null) {
      cards[editingIdx] = card
    } else {
      cards.push(card)
    }
    config     = { ...config, cards }
    showPicker = false
  }

  $: sensorKeys = Object.keys($sensors).sort()
</script>

{#if loading}
  <div class="msg">Loading dashboard…</div>
{:else if error}
  <div class="msg err">Could not load dashboard: {error}</div>
{:else}

  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <div class="dash-header">
    {#if config.title}
      <span class="dash-title">{config.title}</span>
    {:else}
      <span></span>
    {/if}
    <div class="dash-actions">
      {#if saveBanner}
        <span class="save-banner">{saveBanner}</span>
      {/if}
      {#if editMode}
        <button class="btn-add" on:click={() => openPicker()}>+ Add Card</button>
      {/if}
      <button class="btn-edit" class:active={editMode} on:click={toggleEdit}>
        {#if editMode}{saving ? 'Saving…' : 'Done'}{:else}Edit{/if}
      </button>
    </div>
  </div>

  <!-- ── Empty state ─────────────────────────────────────────────────────── -->
  {#if config.cards.length === 0}
    <div class="empty-state">
      {#if editMode}
        No cards yet — click <strong>+ Add Card</strong> to build your dashboard.
      {:else}
        This dashboard is empty. Click <strong>Edit</strong> to add cards.
      {/if}
    </div>
  {/if}

  <!-- ── Card grid ───────────────────────────────────────────────────────── -->
  <div class="card-grid" class:edit-mode={editMode} role="list">
    {#each config.cards as card, i (i)}
      <div
        role="listitem"
        class="card-wrap"
        class:is-dragging={dragIdx === i}
        class:drop-target={dropIdx === i && dragIdx !== i}
        class:card-filled={card.type !== 'blank'}
        style="grid-column: span {card.span ?? 1}; grid-row: span {card.row_span ?? 1}"
        draggable={editMode}
        on:dragstart={e => onDragStart(e, i)}
        on:dragover={e  => onDragOver(e, i)}
        on:dragleave={() => { if (dropIdx === i) dropIdx = null }}
        on:drop={e      => onDrop(e, i)}
        on:dragend={onDragEnd}
      >
        {#if card.type !== 'blank'}
          <div class="card-header">
            <span class="ch-board">{parseBoard(card)}</span>
            {#if card.title && card.type !== 'radio_status'}
              <span class="ch-sep">·</span>
              <span class="ch-entity">{card.title}</span>
            {/if}
          </div>
        {/if}
        <div class="card-body">
          <DashboardCard {card} sensors={$sensors} labels={$labels} radio={$radio} />
        </div>

        {#if editMode}
          <div class="edit-overlay">
            <div class="drag-handle" title="Drag to reorder">⠿</div>
            <div class="overlay-actions">
              <span class="span-label">W</span>
              {#each [1, 2, 3] as s}
                <button
                  class="span-btn"
                  class:active={(card.span ?? 1) === s}
                  title="Width {s}"
                  on:click={() => setSpan(i, s)}
                >{s}</button>
              {/each}
              <span class="span-label span-label-h">H</span>
              {#each [1, 2, 3] as s}
                <button
                  class="span-btn"
                  class:active={(card.row_span ?? 1) === s}
                  title="Height {s}"
                  on:click={() => setRowSpan(i, s)}
                >{s}</button>
              {/each}
              <button class="ov-btn" title="Edit card"   on:click={() => openPicker(i)}>✏</button>
              <button class="ov-btn del" title="Remove"  on:click={() => removeCard(i)}>✕</button>
            </div>
          </div>
        {/if}
      </div>
    {/each}

    <!-- Drop zone at the end so cards can be moved after the last item -->
    {#if editMode}
      <div
        class="end-drop-zone"
        class:active={dropIdx === config.cards.length && dragIdx !== null}
        role="listitem"
        on:dragover={e => { if (dragIdx === null) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; dropIdx = config.cards.length }}
        on:dragleave={() => { if (dropIdx === config.cards.length) dropIdx = null }}
        on:drop={e => onDrop(e, config.cards.length)}
      >
        {dragIdx !== null ? 'Drop here to move to end' : '+ drag cards here'}
      </div>
    {/if}
  </div>

{/if}

<!-- ── Card picker modal ──────────────────────────────────────────────────── -->
{#if showPicker}
  <div
    class="picker-backdrop"
    role="presentation"
    on:click|self={() => showPicker = false}
    on:keydown={(e) => { if (e.key === 'Escape') showPicker = false }}
  >
    <div class="picker-modal">

      <div class="picker-header">
        <span>{editingIdx !== null ? 'Edit Card' : 'Add Card'}</span>
        <button class="close-btn" on:click={() => showPicker = false}>✕</button>
      </div>

      <div class="picker-body">

        <div class="type-list">
          {#each CARD_TYPES as t}
            <button
              class="type-btn"
              class:active={pickerType === t.id}
              on:click={() => onPickerTypeChange(t.id)}
            >{t.label}</button>
          {/each}
        </div>

        <div class="picker-form">
          {#if pickerType === 'radio_status'}
            <p class="form-hint">Shows the radio's frequency, mode, signal level and PTT state in real time. No configuration needed.</p>

          {:else if pickerType === 'sensor'}
            <label>Title
              <input bind:value={pickerConfig.title} placeholder="e.g. Temperature" />
            </label>
            <label>Sensor key
              <input bind:value={pickerConfig.sensor} list="dv-sensor-keys" placeholder="hardware_key" />
            </label>
            <label>Unit
              <input bind:value={pickerConfig.unit} placeholder="e.g. °F, V, A" />
            </label>
            <div class="form-subhead">Thresholds (optional)</div>
            <div class="form-row">
              <label>Warn above  <input type="number" bind:value={pickerConfig.warn_above}     /></label>
              <label>Warn below  <input type="number" bind:value={pickerConfig.warn_below}     /></label>
            </div>
            <div class="form-row">
              <label>Crit above  <input type="number" bind:value={pickerConfig.critical_above} /></label>
              <label>Crit below  <input type="number" bind:value={pickerConfig.critical_below} /></label>
            </div>

          {:else if pickerType === 'relay'}
            <label>Title
              <input bind:value={pickerConfig.title} placeholder="e.g. Antenna A" />
            </label>
            <label>Relay key
              <input bind:value={pickerConfig.relay_key} list="dv-sensor-keys" placeholder="hardware_key" />
            </label>
            <div class="form-row">
              <label>Device addr
                <input bind:value={pickerConfig.device_addr} placeholder="01" />
              </label>
              <label>Relay #
                <input type="number" bind:value={pickerConfig.relay_num} min="1" />
              </label>
            </div>

          {:else if pickerType === 'power_meter'}
            <label>Title
              <input bind:value={pickerConfig.title} placeholder="e.g. Forward Power" />
            </label>
            <label>Sensor key
              <input bind:value={pickerConfig.sensor} list="dv-sensor-keys" placeholder="hardware_key" />
            </label>
            <label>Max watts
              <input type="number" bind:value={pickerConfig.max_w} min="1" />
            </label>

          {:else if pickerType === 'swr_bar'}
            <label>Title
              <input bind:value={pickerConfig.title} placeholder="e.g. SWR" />
            </label>
            <label>Sensor key
              <input bind:value={pickerConfig.sensor} list="dv-sensor-keys" placeholder="hardware_key" />
            </label>
            <div class="form-subhead">Thresholds</div>
            <div class="form-row">
              <label>Good &lt;    <input type="number" step="0.1" bind:value={pickerConfig.thresholds.good}     /></label>
              <label>Warning &lt; <input type="number" step="0.1" bind:value={pickerConfig.thresholds.warning}  /></label>
              <label>Critical &lt;<input type="number" step="0.1" bind:value={pickerConfig.thresholds.critical} /></label>
            </div>

          {:else if pickerType === 'blank'}
            <p class="form-hint">Holds an empty grid cell. Use the width buttons (W 1 2 3) to size it, then drag it into position. Edit it later to replace it with a real card.</p>
          {/if}
        </div>

      </div>

      <datalist id="dv-sensor-keys">
        {#each sensorKeys as k}
          <option value={k}>{$labels[k] ? $labels[k] + ' (' + k + ')' : k}</option>
        {/each}
      </datalist>

      <div class="picker-footer">
        <button class="btn-cancel" on:click={() => showPicker = false}>Cancel</button>
        <button class="btn-commit" on:click={commitPicker}>
          {editingIdx !== null ? 'Update' : 'Add'}
        </button>
      </div>

    </div>
  </div>
{/if}

<style>
  .msg       { padding: 1rem; color: var(--text-muted); font-size: 0.85rem; }
  .err       { color: var(--red); }

  /* ── Header ───────────────────────────────────────────────────────────── */
  .dash-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 0.5rem; margin-bottom: 0.75rem;
  }
  .dash-title { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
  .dash-actions { display: flex; align-items: center; gap: 0.4rem; }
  .save-banner { font-size: 0.75rem; color: var(--green); }

  .btn-edit {
    padding: 0.3rem 0.8rem;
    background: var(--accent-dim); color: var(--accent);
    border: 1px solid var(--accent); border-radius: 4px;
    font-size: 0.78rem; cursor: pointer;
  }
  .btn-edit.active, .btn-edit:hover { background: var(--accent); color: #fff; }
  .btn-add {
    padding: 0.3rem 0.8rem;
    background: var(--accent); color: #fff;
    border: none; border-radius: 4px;
    font-size: 0.78rem; cursor: pointer; font-weight: 600;
  }
  .btn-add:hover { opacity: 0.88; }

  /* ── Empty state ──────────────────────────────────────────────────────── */
  .empty-state {
    text-align: center; padding: 3rem 1rem;
    color: var(--text-muted); font-size: 0.85rem;
    border: 1px dashed var(--border); border-radius: 8px;
    margin-top: 0.5rem;
  }

  /* ── Card grid ────────────────────────────────────────────────────────── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-auto-rows: 80px;
    grid-auto-flow: row dense;
    gap: 0.5rem;
  }
  .card-grid.edit-mode { gap: 0.75rem; }

  /* Responsive: 2 cols on medium, 1 col on small */
  @media (max-width: 700px) {
    .card-grid { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 440px) {
    .card-grid { grid-template-columns: 1fr; }
  }

  /* ── Card wrap ────────────────────────────────────────────────────────── */
  .card-wrap {
    position: relative;
    display: flex;
    flex-direction: column;
    border-radius: 8px;
    overflow: hidden;
    transition: opacity 0.15s;
  }
  .card-filled { background: var(--surface); }

  .card-header {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.18rem 0.6rem;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
    flex-shrink: 0;
  }
  .ch-board {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
  }
  .ch-sep    { font-size: 0.58rem; color: var(--border); }
  .ch-entity {
    font-size: 0.58rem;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .card-body { flex: 1; min-height: 0; overflow: hidden; }

  .card-wrap.is-dragging { opacity: 0.35; cursor: grabbing; }
  /* Left-edge insertion line — shows WHERE the card will land */
  .card-wrap.drop-target::before {
    content: '';
    position: absolute;
    left: -5px; top: 8%; height: 84%; width: 3px;
    background: var(--accent);
    border-radius: 3px;
    pointer-events: none; z-index: 20;
  }
  .card-wrap.drop-target::after { display: none; }
  .edit-mode .card-wrap {
    outline: 1px dashed color-mix(in srgb, var(--border) 80%, transparent);
    cursor: grab;
  }

  /* ── Edit overlay ─────────────────────────────────────────────────────── */
  .edit-overlay {
    position: absolute; inset: 0;
    display: flex; align-items: flex-start; justify-content: space-between;
    padding: 0.3rem 0.35rem;
    background: rgba(8, 10, 18, 0.6);
    border-radius: 8px;
    opacity: 0; pointer-events: none;
    transition: opacity 0.12s;
  }
  .card-wrap:hover .edit-overlay { opacity: 1; pointer-events: all; }

  .drag-handle {
    color: var(--text-muted); font-size: 1rem; line-height: 1;
    cursor: grab; padding: 0.15rem 0.1rem; user-select: none;
  }
  .drag-handle:active { cursor: grabbing; }

  .overlay-actions { display: flex; align-items: center; gap: 0.2rem; }
  .span-label { font-size: 0.6rem; color: var(--text-muted); margin-right: 0.05rem; }
  .span-label-h { margin-left: 0.2rem; }

  .span-btn {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 3px; color: var(--text-muted);
    font-size: 0.63rem; width: 1.2rem; height: 1.2rem;
    cursor: pointer; padding: 0; line-height: 1;
  }
  .span-btn.active  { background: var(--accent); border-color: var(--accent); color: #fff; }
  .span-btn:hover:not(.active) { border-color: var(--accent); color: var(--text); }

  .ov-btn {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 3px; color: var(--text);
    font-size: 0.7rem; padding: 0.15rem 0.35rem;
    cursor: pointer; line-height: 1;
  }
  .ov-btn:hover     { border-color: var(--accent); color: var(--accent); }
  .ov-btn.del:hover { border-color: var(--red);    color: var(--red); }

  /* ── End drop zone ────────────────────────────────────────────────────── */
  .end-drop-zone {
    grid-column: 1 / -1;     /* always spans all columns */
    min-height: 36px;
    display: flex; align-items: center; justify-content: center;
    border: 1px dashed var(--border);
    border-radius: 6px;
    font-size: 0.72rem; color: var(--text-muted);
    transition: border-color 0.15s, background 0.15s, color 0.15s;
    pointer-events: all;
  }
  .end-drop-zone.active {
    border-color: var(--accent);
    background: var(--accent-dim);
    color: var(--accent);
  }

  /* ── Picker modal ─────────────────────────────────────────────────────── */
  .picker-backdrop {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.65);
    display: flex; align-items: center; justify-content: center;
    z-index: 200;
  }
  .picker-modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px;
    width: min(540px, 95vw);
    display: flex; flex-direction: column;
    max-height: 85vh; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .picker-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.7rem 1rem; border-bottom: 1px solid var(--border);
    font-size: 0.85rem; font-weight: 600;
  }
  .close-btn {
    background: none; border: none; color: var(--text-muted);
    cursor: pointer; font-size: 0.9rem; padding: 0.1rem 0.3rem;
  }
  .close-btn:hover { color: var(--text); }

  .picker-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }

  .type-list {
    display: flex; flex-direction: column; gap: 0.1rem;
    padding: 0.6rem 0.4rem;
    border-right: 1px solid var(--border);
    min-width: 130px;
  }
  .type-btn {
    background: none; border: none; border-radius: 5px;
    padding: 0.45rem 0.6rem; text-align: left;
    font-size: 0.78rem; color: var(--text-muted); cursor: pointer;
  }
  .type-btn:hover        { background: var(--accent-dim); color: var(--text); }
  .type-btn.active       { background: var(--accent-dim); color: var(--accent); }

  .picker-form {
    flex: 1; padding: 0.75rem 1rem;
    overflow-y: auto; display: flex; flex-direction: column; gap: 0.55rem;
  }
  .picker-form label {
    display: flex; flex-direction: column; gap: 0.2rem;
    font-size: 0.74rem; color: var(--text-muted);
  }
  .picker-form input {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 4px; color: var(--text);
    padding: 0.35rem 0.5rem; font-size: 0.82rem;
  }
  .picker-form input:focus { outline: none; border-color: var(--accent); }
  .form-hint { font-size: 0.78rem; color: var(--text-muted); margin: 0; }
  .form-subhead {
    font-size: 0.68rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-muted); margin-top: 0.2rem;
  }
  .form-row { display: flex; gap: 0.5rem; }
  .form-row label { flex: 1; }

  .picker-footer {
    display: flex; justify-content: flex-end; gap: 0.5rem;
    padding: 0.7rem 1rem; border-top: 1px solid var(--border);
  }
  .btn-cancel {
    background: none; border: 1px solid var(--border); border-radius: 4px;
    color: var(--text-muted); font-size: 0.78rem;
    padding: 0.35rem 0.8rem; cursor: pointer;
  }
  .btn-cancel:hover { border-color: var(--text-muted); color: var(--text); }
  .btn-commit {
    background: var(--accent); border: none; border-radius: 4px;
    color: #fff; font-size: 0.78rem;
    padding: 0.35rem 0.9rem; cursor: pointer; font-weight: 600;
  }
  .btn-commit:hover { opacity: 0.88; }
</style>
