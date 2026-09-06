<script>
  import { onMount } from 'svelte'
  import { labels, sensors } from '../stores/ws.js'

  let devices = []
  let open    = {}   // device name -> bool
  let editing = {}   // sensor key -> draft string
  let saving  = {}   // sensor key -> bool

  onMount(async () => {
    const res = await fetch('/api/devices')
    if (res.ok) {
      const data = await res.json()
      devices = data.devices ?? []
      const o = {}
      for (const d of devices) o[d.name] = true
      open = o
    }
  })

  function toggle(name) {
    open = { ...open, [name]: !open[name] }
  }

  function startEdit(key) {
    editing = { ...editing, [key]: $labels[key] ?? '' }
  }

  function cancelEdit(key) {
    const { [key]: _, ...rest } = editing
    editing = rest
  }

  async function save(key) {
    const label = editing[key].trim()
    saving = { ...saving, [key]: true }
    try {
      if (label) {
        await fetch(`/api/labels/${encodeURIComponent(key)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label }),
        })
      } else {
        await fetch(`/api/labels/${encodeURIComponent(key)}`, { method: 'DELETE' })
      }
    } finally {
      saving = { ...saving, [key]: false }
      cancelEdit(key)
    }
  }

  const TYPE_LABELS = {
    gpio:           'GPIO Module (#321)',
    coax_switch:    'HF Coax Switch (#331)',
    watt_meter:     'RF Watt Meter (#335)',
    vhf_relay:      'VHF Coax Relay (#332)',
    antenna_relay:  'Antenna Relay (#361)',
  }

  function deviceHeader(dev) {
    if (dev.type === 'antenna_relay') return dev.persona_label ?? TYPE_LABELS[dev.type]
    return TYPE_LABELS[dev.type] ?? dev.type
  }

  function roleLabel(s) {
    if (s.role === 'relay')               return `Relay ${s.relay_num}`
    if (s.role === 'digital_input')       return `Digital Input ${s.input_num}`
    if (s.role === 'voltmeter')           return `Voltmeter ${s.voltmeter_num}`
    if (s.role === 'temperature')         return `Temp Probe ${s.probe_num}`
    if (s.role === 'active_port')         return 'Active Port'
    if (s.role === 'port')                return `Port ${s.port}`
    if (s.role === 'forward_power')       return 'Forward Power'
    if (s.role === 'reflected_power')     return 'Reflected Power'
    if (s.role === 'swr')                 return 'SWR'
    if (s.role === 'reflection_coefficient') return 'Refl. Coeff.'
    if (s.role === 'return_loss')         return 'Return Loss'
    if (s.role === 'mismatch_loss')       return 'Mismatch Loss'
    if (s.role === 'nc_port')             return 'NC Port'
    if (s.role === 'no_port')             return 'NO Port'
    return s.key
  }

  function fmtValue(s) {
    const entry = $sensors[s.key]
    if (entry == null) return null
    const v = entry.value
    if (s.role === 'relay' || s.role === 'nc_port' || s.role === 'no_port') {
      return v >= 0.5 ? 'ON' : 'OFF'
    }
    if (s.role === 'port') return v >= 0.5 ? 'Active' : 'Idle'
    if (s.role === 'digital_input') return v >= 0.5 ? 'HIGH' : 'LOW'
    if (s.role === 'active_port') return `Port ${Math.round(v)}`
    return Number(v).toFixed(2)
  }
</script>

<div class="label-editor">
  <h2>Friendly Names</h2>
  <p class="hint">Assign a display name to any sensor. Changes apply instantly to automations and the dashboard.</p>

  {#each devices as dev (dev.name)}
    <div class="device-group">
      <button class="group-header" on:click={() => toggle(dev.name)}>
        <span class="twisty">{open[dev.name] ? '&#9660;' : '&#9658;'}</span>
        <span class="group-name">{dev.name}</span>
        <span class="group-desc">{deviceHeader(dev)}</span>
        <span class="group-addr">addr {dev.address}</span>
      </button>

      {#if open[dev.name]}
        <table class="sensor-table">
          <tbody>
            {#each dev.sensors as s (s.key)}
              <tr>
                <td class="role-col">{roleLabel(s)}</td>
                <td class="hw-key">{s.key}</td>
                <td class="value-col">
                  {#if fmtValue(s) != null}
                    <span class="val">{fmtValue(s)}</span>
                  {:else}
                    <span class="no-data">--</span>
                  {/if}
                </td>
                <td class="label-col">
                  {#if s.key in editing}
                    <input
                      class="label-input"
                      bind:value={editing[s.key]}
                      placeholder="friendly name"
                      on:keydown={(e) => { if (e.key === 'Enter') save(s.key); if (e.key === 'Escape') cancelEdit(s.key) }}
                    />
                  {:else}
                    <span class="label-display" class:unlabelled={!$labels[s.key]}>
                      {$labels[s.key] || '&mdash;'}
                    </span>
                  {/if}
                </td>
                <td class="actions">
                  {#if s.key in editing}
                    <button class="btn-save" on:click={() => save(s.key)} disabled={saving[s.key]}>
                      {saving[s.key] ? '...' : 'Save'}
                    </button>
                    <button class="btn-cancel" on:click={() => cancelEdit(s.key)}>Cancel</button>
                  {:else}
                    <button class="btn-edit" on:click={() => startEdit(s.key)}>Edit</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/each}

  {#if devices.length === 0}
    <p class="no-devices">No devices configured or application not running.</p>
  {/if}
</div>

<style>
  .label-editor { max-width: 900px; }
  h2 { margin: 0 0 0.4rem; font-size: 1.1rem; }
  .hint { color: var(--text-muted); font-size: 0.8rem; margin: 0 0 1.25rem; }

  .device-group {
    border: 1px solid var(--border);
    border-radius: 7px;
    margin-bottom: 0.6rem;
    overflow: hidden;
  }

  .group-header {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.55rem 0.8rem;
    background: var(--surface);
    border: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.85rem;
    color: var(--text);
    transition: background 0.15s;
  }
  .group-header:hover { background: var(--border); }

  .twisty { color: var(--text-muted); font-size: 0.7rem; flex-shrink: 0; }
  .group-name { font-family: monospace; font-weight: 600; color: var(--accent); }
  .group-desc { flex: 1; color: var(--text-muted); font-size: 0.8rem; }
  .group-addr { font-family: monospace; font-size: 0.75rem; color: var(--text-muted); }

  .sensor-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    background: var(--bg);
  }
  td { padding: 0.3rem 0.6rem; border-top: 1px solid var(--border); vertical-align: middle; }
  tr:first-child td { border-top: none; }

  .role-col { color: var(--text-muted); width: 130px; }
  .hw-key { font-family: monospace; font-size: 0.75rem; color: var(--text-muted); width: 220px; }
  .value-col { width: 70px; }

  .val { color: var(--text); }
  .no-data { color: var(--border); }

  .label-input {
    width: 100%;
    padding: 0.2rem 0.4rem;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: var(--bg);
    color: inherit;
    font-size: 0.82rem;
    outline: none;
  }
  .unlabelled { color: var(--text-muted); }

  .actions { white-space: nowrap; width: 120px; }
  button {
    padding: 0.18rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--border);
    cursor: pointer;
    font-size: 0.75rem;
    background: var(--surface);
    color: inherit;
  }
  .btn-save { border-color: var(--accent); color: var(--accent); }
  .btn-save:hover { background: var(--accent-dim); }
  .btn-edit:hover { border-color: var(--accent); }
  .btn-cancel:hover { background: var(--surface); }

  .no-devices { color: var(--text-muted); font-size: 0.85rem; }
</style>
