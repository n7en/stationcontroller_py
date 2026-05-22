<script>
  import { createEventDispatcher, onMount } from 'svelte'

  export let value = 1       // bound model_id
  export let placeholder = 'Search manufacturer or model…'

  const dispatch = createEventDispatcher()

  let models    = []
  let filtered  = []
  let query     = ''
  let loading   = true
  let error     = null
  let open      = false
  let inputEl

  // Display label shown in the text input when a model is selected
  $: selectedModel = models.find(m => m.model_id === value)
  $: displayLabel  = selectedModel
    ? `${selectedModel.model_id} — ${selectedModel.manufacturer} ${selectedModel.model}`
    : (value ? `Model ${value}` : '')

  onMount(async () => {
    try {
      const r = await fetch('/api/radio/hamlib-models')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      models = d.models || []
      filtered = models
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })

  function applyFilter() {
    const q = query.trim().toLowerCase()
    filtered = q
      ? models.filter(m =>
          m.manufacturer.toLowerCase().includes(q) ||
          m.model.toLowerCase().includes(q) ||
          String(m.model_id).includes(q)
        )
      : models
  }

  function select(m) {
    value = m.model_id
    query = ''
    open  = false
    dispatch('select', m)
  }

  function onInputFocus() {
    open = true
    applyFilter()
  }

  function onInputBlur() {
    // Delay so click on list item fires first
    setTimeout(() => { open = false }, 180)
  }

  function onKeydown(e) {
    if (e.key === 'Escape') { open = false; inputEl?.blur() }
  }

  function statusBadge(s) {
    if (!s) return ''
    const l = s.toLowerCase()
    if (l === 'stable')   return 'status-stable'
    if (l === 'beta')     return 'status-beta'
    if (l === 'alpha')    return 'status-alpha'
    return ''
  }
</script>

<div class="picker-wrap">
  <input
    bind:this={inputEl}
    class="picker-input"
    type="text"
    bind:value={query}
    on:input={applyFilter}
    on:focus={onInputFocus}
    on:blur={onInputBlur}
    on:keydown={onKeydown}
    placeholder={open ? placeholder : displayLabel || placeholder}
  />

  {#if !open && displayLabel}
    <span class="picker-preview">{displayLabel}</span>
  {/if}

  {#if open}
    <div class="picker-dropdown">
      {#if loading}
        <div class="picker-msg">Loading models…</div>
      {:else if error}
        <div class="picker-msg picker-err">
          rigctl not found — enter model ID manually.<br/>
          <small>{error}</small>
        </div>
      {:else if filtered.length === 0}
        <div class="picker-msg">No models match "{query}"</div>
      {:else}
        <div class="picker-list">
          {#each filtered.slice(0, 200) as m (m.model_id)}
            <button
              class="picker-row"
              class:selected={m.model_id === value}
              on:mousedown|preventDefault={() => select(m)}
            >
              <span class="picker-id">{m.model_id}</span>
              <span class="picker-mfg">{m.manufacturer}</span>
              <span class="picker-model">{m.model}</span>
              {#if m.status}
                <span class="picker-status {statusBadge(m.status)}">{m.status}</span>
              {/if}
            </button>
          {/each}
          {#if filtered.length > 200}
            <div class="picker-msg">…and {filtered.length - 200} more — refine your search</div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .picker-wrap { position: relative; width: 100%; }

  .picker-input {
    width: 100%; box-sizing: border-box;
    background: var(--surface, #1a1a2e); color: var(--text, #e0e0e0);
    border: 1px solid var(--border, #333); border-radius: 4px;
    padding: 4px 8px; font-size: 0.85rem;
  }
  .picker-input:focus { outline: none; border-color: var(--accent, #4fc3f7); }

  .picker-preview {
    position: absolute; left: 8px; top: 50%; transform: translateY(-50%);
    font-size: 0.82rem; color: var(--text, #e0e0e0);
    pointer-events: none; white-space: nowrap; overflow: hidden;
    max-width: calc(100% - 16px);
  }

  .picker-dropdown {
    position: absolute; z-index: 200; left: 0; right: 0; top: calc(100% + 2px);
    background: var(--surface, #1a1a2e); border: 1px solid var(--border, #333);
    border-radius: 4px; box-shadow: 0 4px 16px rgba(0,0,0,.5);
    max-height: 280px; overflow: hidden; display: flex; flex-direction: column;
  }

  .picker-list { overflow-y: auto; flex: 1; }

  .picker-row {
    display: flex; align-items: center; gap: 6px;
    width: 100%; padding: 4px 8px; text-align: left;
    background: none; border: none; cursor: pointer;
    color: var(--text, #e0e0e0); font-size: 0.8rem;
  }
  .picker-row:hover, .picker-row.selected { background: var(--surface2, #252540); }

  .picker-id   { min-width: 38px; color: var(--muted, #888); font-variant-numeric: tabular-nums; }
  .picker-mfg  { min-width: 100px; color: var(--accent, #4fc3f7); }
  .picker-model{ flex: 1; }
  .picker-status {
    font-size: 0.65rem; border-radius: 3px; padding: 1px 5px;
    background: var(--surface2, #252540); color: var(--muted, #aaa);
  }
  .status-stable { background: #1b3320; color: #66bb6a; }
  .status-beta   { background: #2a2a00; color: #f0a030; }
  .status-alpha  { background: #2a1500; color: #ef9a30; }

  .picker-msg {
    padding: 8px 10px; font-size: 0.78rem; color: var(--muted, #888);
  }
  .picker-err { color: var(--red, #ef5350); }
</style>
