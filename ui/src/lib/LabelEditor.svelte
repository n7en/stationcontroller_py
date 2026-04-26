<script>
  import { labels, sensors } from '../stores/ws.js'

  let editing = {}   // key → draft string
  let saving  = {}   // key → bool

  $: allKeys = Object.keys($sensors).sort()

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
</script>

<div class="label-editor">
  <h2>Friendly Names</h2>
  <p class="hint">Assign a display name to any sensor. Leave blank to remove. Changes save instantly and apply to automations and the dashboard.</p>

  <table>
    <thead>
      <tr>
        <th>Hardware Key</th>
        <th>Friendly Name</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each allKeys as key (key)}
        <tr>
          <td class="hw-key">{key}</td>
          <td>
            {#if key in editing}
              <input
                class="label-input"
                bind:value={editing[key]}
                placeholder="e.g. 20m Yagi"
                on:keydown={(e) => { if (e.key === 'Enter') save(key); if (e.key === 'Escape') cancelEdit(key) }}
                autofocus
              />
            {:else}
              <span class="label-display" class:unlabelled={!$labels[key]}>
                {$labels[key] || '—'}
              </span>
            {/if}
          </td>
          <td class="actions">
            {#if key in editing}
              <button class="btn-save" on:click={() => save(key)} disabled={saving[key]}>
                {saving[key] ? '…' : 'Save'}
              </button>
              <button class="btn-cancel" on:click={() => cancelEdit(key)}>Cancel</button>
            {:else}
              <button class="btn-edit" on:click={() => startEdit(key)}>Edit</button>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .label-editor { max-width: 780px; }
  h2 { margin: 0 0 0.4rem; font-size: 1.1rem; }
  .hint { color: var(--text-muted); font-size: 0.8rem; margin: 0 0 1.25rem; }

  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 0.4rem 0.6rem; color: var(--text-muted); border-bottom: 1px solid var(--border); }
  td { padding: 0.35rem 0.6rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }

  .hw-key { font-family: monospace; color: var(--text-muted); font-size: 0.78rem; }
  .label-display { }
  .unlabelled { color: var(--text-muted); }

  .label-input {
    width: 100%;
    padding: 0.25rem 0.4rem;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: var(--bg);
    color: inherit;
    font-size: 0.85rem;
    outline: none;
  }

  .actions { white-space: nowrap; }
  button { padding: 0.2rem 0.55rem; border-radius: 4px; border: 1px solid var(--border); cursor: pointer; font-size: 0.78rem; background: var(--surface); color: inherit; }
  .btn-save { border-color: var(--accent); color: var(--accent); }
  .btn-save:hover { background: var(--accent-dim); }
  .btn-cancel:hover { background: var(--surface); }
  .btn-edit:hover { border-color: var(--accent); }
</style>
