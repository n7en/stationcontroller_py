<script>
  import { onMount } from 'svelte'

  /** @type {{ key: string, label: string }[]} */
  let builtIns = []

  /** @type {{ name: string, country: string, region: string, bands: any[] }|null} */
  let plan = null

  let loading   = true
  let saving    = false
  let banner    = null  // { ok: bool, text: string }

  let selectedBuiltIn = 'us_extra'

  // Accordion / edit state
  let expandedBand  = -1
  let editBandIdx   = -1
  /** @type {{ name: string, start_mhz: number, end_mhz: number }|null} */
  let editBand      = null

  // Add-row state (one at a time per section)
  let addingSegment  = -1   // band index
  let addingActivity = -1   // band index

  /** @type {{ name: string, start_mhz: string, end_mhz: string, modes: string, description: string }} */
  let newSeg = emptySegment()
  /** @type {{ name: string, freq_mhz: string, mode: string, bandwidth_hz: string, description: string }} */
  let newAct = emptyActivity()

  // Edit existing segment/activity inline
  /** @type {{ bandIdx: number, segIdx: number, name: string, start_mhz: string, end_mhz: string, modes: string, description: string }|null} */
  let editSeg  = null
  /** @type {{ bandIdx: number, actIdx: number, name: string, freq_mhz: string, mode: string, bandwidth_hz: string, description: string }|null} */
  let editAct  = null

  // ── helpers ──────────────────────────────────────────────────────────────

  function emptySegment() {
    return { name: '', start_mhz: '', end_mhz: '', modes: '', description: '' }
  }
  function emptyActivity() {
    return { name: '', freq_mhz: '', mode: '', bandwidth_hz: '3000', description: '' }
  }

  function fmtMHz(hz) {
    return (hz / 1e6).toFixed(3)
  }
  function parseMHz(s) {
    return parseFloat(String(s).replace(/,/g, '')) * 1e6
  }

  const SEG_COLOR = {
    cw:      'var(--green)',
    digital: 'var(--accent)',
    phone:   '#e09850',
    beacon:  '#a0c8ff',
    mixed:   'var(--text-muted)',
  }
  function segColor(name) {
    return SEG_COLOR[String(name).toLowerCase()] ?? 'var(--text-muted)'
  }

  function modesToStr(modes) {
    return Array.isArray(modes) ? modes.join(', ') : (modes || '')
  }
  function strToModes(s) {
    return String(s).split(',').map(m => m.trim()).filter(Boolean)
  }

  // ── lifecycle ─────────────────────────────────────────────────────────────

  onMount(async () => {
    const [bRes, pRes] = await Promise.all([
      fetch('/api/band_plan/built_ins'),
      fetch('/api/band_plan'),
    ])
    builtIns = await bRes.json()
    const data = await pRes.json()
    plan = data.plan
    if (data.config?.built_in) selectedBuiltIn = data.config.built_in
    loading = false
  })

  // ── built-in loader ───────────────────────────────────────────────────────

  async function loadBuiltIn() {
    const r = await fetch(`/api/band_plan/built_in/${selectedBuiltIn}`)
    if (!r.ok) { banner = { ok: false, text: 'Failed to load plan.' }; return }
    plan = await r.json()
    expandedBand = -1
    editBandIdx  = -1
    editBand     = null
    banner = { ok: true, text: `Loaded "${plan.name}". Press Save to apply.` }
  }

  // ── save ──────────────────────────────────────────────────────────────────

  async function save() {
    saving = true
    banner = null
    try {
      const r = await fetch('/api/band_plan', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(plan),
      })
      if (!r.ok) throw new Error(await r.text())
      banner = { ok: true, text: 'Band plan saved.' }
    } catch (e) {
      banner = { ok: false, text: String(e.message || e) }
    } finally {
      saving = false
    }
  }

  // ── band CRUD ─────────────────────────────────────────────────────────────

  function startEditBand(i) {
    const b = plan.bands[i]
    editBandIdx = i
    editBand = { name: b.name, start_mhz: b.start_hz / 1e6, end_mhz: b.end_hz / 1e6 }
    // Open the accordion so the edit form is visible
    expandedBand = i
  }

  function applyEditBand() {
    plan.bands[editBandIdx] = {
      ...plan.bands[editBandIdx],
      name:     editBand.name,
      start_hz: editBand.start_mhz * 1e6,
      end_hz:   editBand.end_mhz   * 1e6,
    }
    plan = plan
    editBandIdx = -1
    editBand = null
  }

  function cancelEditBand() { editBandIdx = -1; editBand = null }

  function removeBand(i) {
    plan.bands = plan.bands.filter((_, idx) => idx !== i)
    if (expandedBand === i) expandedBand = -1
    else if (expandedBand > i) expandedBand--
    plan = plan
  }

  function addBand() {
    const nb = { name: 'New', start_hz: 0, end_hz: 0, modes: [], segments: [], activities: [] }
    plan.bands = [...plan.bands, nb]
    plan = plan
    const i = plan.bands.length - 1
    expandedBand = i
    startEditBand(i)
  }

  function toggleBand(i) {
    if (editBandIdx === i) return
    expandedBand = expandedBand === i ? -1 : i
  }

  // ── segment CRUD ──────────────────────────────────────────────────────────

  function startAddSegment(bandIdx) {
    addingSegment  = bandIdx
    addingActivity = -1
    editSeg = null
    newSeg  = emptySegment()
  }

  function applyAddSegment(bandIdx) {
    plan.bands[bandIdx].segments = [
      ...plan.bands[bandIdx].segments,
      {
        name:        newSeg.name,
        start_hz:    parseMHz(newSeg.start_mhz),
        end_hz:      parseMHz(newSeg.end_mhz),
        modes:       strToModes(newSeg.modes),
        description: newSeg.description,
      },
    ]
    plan = plan
    addingSegment = -1
  }

  function startEditSeg(bandIdx, segIdx) {
    const s = plan.bands[bandIdx].segments[segIdx]
    editSeg = {
      bandIdx, segIdx,
      name:        s.name,
      start_mhz:   String(s.start_hz / 1e6),
      end_mhz:     String(s.end_hz   / 1e6),
      modes:       modesToStr(s.modes),
      description: s.description,
    }
  }

  function applyEditSeg() {
    const { bandIdx, segIdx } = editSeg
    plan.bands[bandIdx].segments[segIdx] = {
      name:        editSeg.name,
      start_hz:    parseMHz(editSeg.start_mhz),
      end_hz:      parseMHz(editSeg.end_mhz),
      modes:       strToModes(editSeg.modes),
      description: editSeg.description,
    }
    plan = plan
    editSeg = null
  }

  function removeSeg(bandIdx, segIdx) {
    plan.bands[bandIdx].segments = plan.bands[bandIdx].segments.filter((_, i) => i !== segIdx)
    plan = plan
  }

  // ── activity CRUD ─────────────────────────────────────────────────────────

  function startAddActivity(bandIdx) {
    addingActivity = bandIdx
    addingSegment  = -1
    editAct = null
    newAct  = emptyActivity()
  }

  function applyAddActivity(bandIdx) {
    plan.bands[bandIdx].activities = [
      ...plan.bands[bandIdx].activities,
      {
        name:         newAct.name,
        frequency_hz: parseMHz(newAct.freq_mhz),
        mode:         newAct.mode,
        bandwidth_hz: parseFloat(newAct.bandwidth_hz) || 3000,
        description:  newAct.description,
      },
    ]
    plan = plan
    addingActivity = -1
  }

  function startEditAct(bandIdx, actIdx) {
    const a = plan.bands[bandIdx].activities[actIdx]
    editAct = {
      bandIdx, actIdx,
      name:         a.name,
      freq_mhz:     String(a.frequency_hz / 1e6),
      mode:         a.mode,
      bandwidth_hz: String(a.bandwidth_hz),
      description:  a.description,
    }
  }

  function applyEditAct() {
    const { bandIdx, actIdx } = editAct
    plan.bands[bandIdx].activities[actIdx] = {
      name:         editAct.name,
      frequency_hz: parseMHz(editAct.freq_mhz),
      mode:         editAct.mode,
      bandwidth_hz: parseFloat(editAct.bandwidth_hz) || 3000,
      description:  editAct.description,
    }
    plan = plan
    editAct = null
  }

  function removeAct(bandIdx, actIdx) {
    plan.bands[bandIdx].activities = plan.bands[bandIdx].activities.filter((_, i) => i !== actIdx)
    plan = plan
  }
</script>

{#if loading}
  <div class="loading">Loading band plan…</div>
{:else if plan}

  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <div class="bp-header">
    <div class="title-row">
      <h2 class="title">Band Plan</h2>
      <button class="btn-primary" on:click={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>

    {#if banner}
      <div class="banner" class:ok={banner.ok} class:err={!banner.ok}>{banner.text}</div>
    {/if}

    <div class="builtin-row">
      <label class="builtin-label">
        Base plan
        <select bind:value={selectedBuiltIn} class="builtin-select">
          {#each builtIns as b (b.key)}
            <option value={b.key}>{b.label}</option>
          {/each}
        </select>
      </label>
      <button class="btn-secondary" on:click={loadBuiltIn}>Load</button>
      <span class="plan-meta">
        {plan.name}{#if plan.region} · {plan.region}{/if}
      </span>
    </div>
  </div>

  <!-- ── Band list ─────────────────────────────────────────────────────── -->
  <div class="band-list">

    {#each plan.bands as band, i (i)}

      <!-- Band header row -->
      {#if editBandIdx === i && editBand}
        <div class="band-edit-row">
          <input class="inp inp-name" bind:value={editBand.name} placeholder="name (40m)" />
          <input class="inp inp-freq" type="number" step="0.001" bind:value={editBand.start_mhz} placeholder="start" />
          <span class="dash">–</span>
          <input class="inp inp-freq" type="number" step="0.001" bind:value={editBand.end_mhz}   placeholder="end" />
          <span class="unit">MHz</span>
          <button class="btn-sm" on:click={applyEditBand}>OK</button>
          <button class="btn-sm ghost" on:click={cancelEditBand}>Cancel</button>
        </div>
      {:else}
        <div class="band-row" class:expanded={expandedBand === i}>
          <button class="band-toggle" on:click={() => toggleBand(i)}>
            <span class="chevron">{expandedBand === i ? '▼' : '▶'}</span>
            <span class="band-name">{band.name}</span>
            <span class="band-range">{fmtMHz(band.start_hz)} – {fmtMHz(band.end_hz)} MHz</span>
          </button>
          <div class="band-actions">
            <button class="btn-sm" on:click={() => startEditBand(i)}>Edit</button>
            <button class="btn-sm ghost" on:click={() => removeBand(i)}>Remove</button>
          </div>
        </div>
      {/if}

      <!-- Expanded detail -->
      {#if expandedBand === i && editBandIdx !== i}
        <div class="band-detail">

          <!-- Segments -->
          <div class="detail-section">
            <div class="section-hdr">
              <span class="section-title">Segments</span>
              <button class="btn-sm" on:click={() => startAddSegment(i)}>+ Add</button>
            </div>

            {#if band.segments.length > 0}
              <table class="dtable">
                <thead>
                  <tr>
                    <th>Name</th><th>Start MHz</th><th>End MHz</th><th>Modes</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {#each band.segments as seg, si}
                    {#if editSeg && editSeg.bandIdx === i && editSeg.segIdx === si}
                      <!-- Inline edit row -->
                      <tr class="edit-row">
                        <td><input class="inp inp-sm" bind:value={editSeg.name} placeholder="name" /></td>
                        <td><input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={editSeg.start_mhz} /></td>
                        <td><input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={editSeg.end_mhz} /></td>
                        <td><input class="inp inp-sm" bind:value={editSeg.modes} placeholder="CW, USB, …" /></td>
                        <td class="act-cell">
                          <button class="btn-xs" on:click={applyEditSeg}>OK</button>
                          <button class="btn-xs ghost" on:click={() => editSeg = null}>✕</button>
                        </td>
                      </tr>
                    {:else}
                      <tr>
                        <td>
                          <span class="seg-dot" style="background:{segColor(seg.name)}"></span>
                          {seg.name}
                        </td>
                        <td class="num">{fmtMHz(seg.start_hz)}</td>
                        <td class="num">{fmtMHz(seg.end_hz)}</td>
                        <td class="modes-cell">
                          {#each (seg.modes || []) as m}
                            <span class="mode-badge">{m}</span>
                          {/each}
                        </td>
                        <td class="act-cell">
                          <button class="btn-xs" on:click={() => startEditSeg(i, si)}>Edit</button>
                          <button class="btn-xs ghost" on:click={() => removeSeg(i, si)}>✕</button>
                        </td>
                      </tr>
                    {/if}
                  {/each}
                </tbody>
              </table>
            {:else}
              <p class="empty">No segments defined.</p>
            {/if}

            {#if addingSegment === i}
              <div class="add-form">
                <input class="inp inp-sm" bind:value={newSeg.name} placeholder="name (cw/digital/phone)" />
                <input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={newSeg.start_mhz} placeholder="start MHz" />
                <input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={newSeg.end_mhz}   placeholder="end MHz" />
                <input class="inp inp-sm inp-modes" bind:value={newSeg.modes} placeholder="modes (CW, USB, …)" />
                <button class="btn-sm" on:click={() => applyAddSegment(i)}>Add</button>
                <button class="btn-sm ghost" on:click={() => addingSegment = -1}>Cancel</button>
              </div>
            {/if}
          </div>

          <!-- Activities -->
          <div class="detail-section">
            <div class="section-hdr">
              <span class="section-title">Activities</span>
              <button class="btn-sm" on:click={() => startAddActivity(i)}>+ Add</button>
            </div>

            {#if band.activities.length > 0}
              <table class="dtable">
                <thead>
                  <tr>
                    <th>Name</th><th>Frequency MHz</th><th>Mode</th><th>BW Hz</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {#each band.activities as act, ai}
                    {#if editAct && editAct.bandIdx === i && editAct.actIdx === ai}
                      <tr class="edit-row">
                        <td><input class="inp inp-sm" bind:value={editAct.name} placeholder="name" /></td>
                        <td><input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={editAct.freq_mhz} /></td>
                        <td><input class="inp inp-sm inp-mode" bind:value={editAct.mode} placeholder="FT8" /></td>
                        <td><input class="inp inp-sm inp-num" type="number" bind:value={editAct.bandwidth_hz} /></td>
                        <td class="act-cell">
                          <button class="btn-xs" on:click={applyEditAct}>OK</button>
                          <button class="btn-xs ghost" on:click={() => editAct = null}>✕</button>
                        </td>
                      </tr>
                    {:else}
                      <tr>
                        <td class="act-name">{act.name}</td>
                        <td class="num">{fmtMHz(act.frequency_hz)}</td>
                        <td><span class="mode-badge">{act.mode}</span></td>
                        <td class="num">{act.bandwidth_hz}</td>
                        <td class="act-cell">
                          <button class="btn-xs" on:click={() => startEditAct(i, ai)}>Edit</button>
                          <button class="btn-xs ghost" on:click={() => removeAct(i, ai)}>✕</button>
                        </td>
                      </tr>
                    {/if}
                  {/each}
                </tbody>
              </table>
            {:else}
              <p class="empty">No activities defined.</p>
            {/if}

            {#if addingActivity === i}
              <div class="add-form">
                <input class="inp inp-sm" bind:value={newAct.name} placeholder="name (ft8/wspr…)" />
                <input class="inp inp-sm inp-num" type="number" step="0.001" bind:value={newAct.freq_mhz} placeholder="freq MHz" />
                <input class="inp inp-sm inp-mode" bind:value={newAct.mode} placeholder="mode (FT8)" />
                <input class="inp inp-sm inp-num" type="number" bind:value={newAct.bandwidth_hz} placeholder="BW Hz" />
                <button class="btn-sm" on:click={() => applyAddActivity(i)}>Add</button>
                <button class="btn-sm ghost" on:click={() => addingActivity = -1}>Cancel</button>
              </div>
            {/if}
          </div>

        </div><!-- /band-detail -->
      {/if}

    {/each}<!-- /each band -->

    <div class="add-band-row">
      <button class="btn-secondary" on:click={addBand}>+ Add Band</button>
    </div>

  </div><!-- /band-list -->

{/if}

<style>
  /* ── Layout ── */
  .loading { color: var(--text-muted); padding: 1rem; }

  .bp-header {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-bottom: 0.75rem;
  }
  .title-row {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .banner {
    padding: 0.4rem 0.75rem;
    border-radius: 5px;
    font-size: 0.82rem;
  }
  .banner.ok  { background: rgba(62,207,142,0.12); color: var(--green); }
  .banner.err { background: rgba(233,98,98,0.12);  color: var(--red);   }

  .builtin-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .builtin-label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.82rem;
    color: var(--text-muted);
  }
  .builtin-select {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.82rem;
  }
  .plan-meta {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-left: 0.5rem;
  }

  /* ── Band list ── */
  .band-list {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }

  .band-row {
    display: flex;
    align-items: center;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    transition: background 0.12s;
  }
  .band-row:last-of-type { border-bottom: none; }
  .band-row.expanded { background: rgba(78,154,241,0.06); }

  .band-toggle {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.55rem 0.75rem;
    background: transparent;
    border: none;
    color: var(--text);
    cursor: pointer;
    text-align: left;
    font-size: 0.85rem;
  }
  .band-toggle:hover { color: var(--accent); }

  .chevron { font-size: 0.65rem; color: var(--text-muted); width: 0.8rem; }
  .band-name { font-weight: 600; min-width: 3.5rem; }
  .band-range { color: var(--text-muted); font-variant-numeric: tabular-nums; font-size: 0.8rem; }

  .band-actions {
    display: flex;
    gap: 0.3rem;
    padding-right: 0.6rem;
    flex-shrink: 0;
  }

  /* band edit inline row */
  .band-edit-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .dash { color: var(--text-muted); }
  .unit { font-size: 0.78rem; color: var(--text-muted); }

  /* ── Band detail accordion ── */
  .band-detail {
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .detail-section { display: flex; flex-direction: column; gap: 0.4rem; }

  .section-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .section-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    font-weight: 600;
  }

  .empty { margin: 0; font-size: 0.8rem; color: var(--text-muted); }

  /* ── Tables ── */
  .dtable {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }
  .dtable th {
    text-align: left;
    color: var(--text-muted);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.2rem 0.4rem;
    border-bottom: 1px solid var(--border);
    font-weight: 500;
  }
  .dtable td {
    padding: 0.3rem 0.4rem;
    border-bottom: 1px solid rgba(42,47,62,0.5);
    vertical-align: middle;
  }
  .dtable tr:last-child td { border-bottom: none; }
  .dtable tr.edit-row { background: rgba(78,154,241,0.05); }
  .dtable tr:hover:not(.edit-row) { background: rgba(255,255,255,0.02); }

  .num { font-variant-numeric: tabular-nums; color: var(--text-muted); }
  .act-cell {
    display: flex;
    gap: 0.25rem;
    justify-content: flex-end;
    white-space: nowrap;
  }
  .act-name { color: var(--text-muted); }

  .seg-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    margin-right: 0.35rem;
    flex-shrink: 0;
  }
  .modes-cell { display: flex; flex-wrap: wrap; gap: 0.2rem; }
  .mode-badge {
    font-size: 0.67rem;
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
    background: var(--accent-dim);
    color: var(--accent);
    font-weight: 600;
    white-space: nowrap;
  }

  /* ── Add form ── */
  .add-form {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
    padding: 0.4rem 0.2rem;
    margin-top: 0.2rem;
    border-top: 1px dashed var(--border);
  }

  /* ── Add band row ── */
  .add-band-row {
    padding: 0.5rem 0.75rem;
    border-top: 1px solid var(--border);
    background: var(--surface);
  }

  /* ── Inputs ── */
  .inp {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    padding: 0.28rem 0.5rem;
    font-size: 0.82rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .inp:focus { border-color: var(--accent); }
  .inp-name  { width: 6rem; }
  .inp-freq  { width: 6rem; }
  .inp-sm    { font-size: 0.78rem; padding: 0.22rem 0.4rem; }
  .inp-num   { width: 6.5rem; }
  .inp-mode  { width: 5rem; }
  .inp-modes { width: 12rem; }

  /* ── Buttons ── */
  .btn-primary {
    padding: 0.35rem 0.9rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 5px;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn-primary:disabled { opacity: 0.5; cursor: default; }
  .btn-primary:hover:not(:disabled) { opacity: 0.85; }

  .btn-secondary {
    padding: 0.3rem 0.75rem;
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 5px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-secondary:hover { background: var(--accent-dim); }

  .btn-sm {
    padding: 0.22rem 0.55rem;
    font-size: 0.75rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    cursor: pointer;
    white-space: nowrap;
    transition: border-color 0.12s, color 0.12s;
  }
  .btn-sm:hover { border-color: var(--accent); color: var(--accent); }
  .btn-sm.ghost { background: transparent; border-color: transparent; color: var(--text-muted); }
  .btn-sm.ghost:hover { color: var(--red); border-color: transparent; }

  .btn-xs {
    padding: 0.15rem 0.4rem;
    font-size: 0.7rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--text-muted);
    cursor: pointer;
    transition: border-color 0.12s, color 0.12s;
  }
  .btn-xs:hover { border-color: var(--accent); color: var(--accent); }
  .btn-xs.ghost { background: transparent; border-color: transparent; }
  .btn-xs.ghost:hover { color: var(--red); border-color: transparent; }
</style>
