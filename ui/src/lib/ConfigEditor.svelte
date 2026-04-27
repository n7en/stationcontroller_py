<script>
  import { onMount } from 'svelte'

  const CONFIGS = [
    { key: 'comms',      label: 'Communications', restart: true  },
    { key: 'radio',      label: 'Radio',          restart: true  },
    { key: 'automation', label: 'Automation',      restart: false },
    { key: 'telemetry',  label: 'Telemetry',       restart: true  },
  ]

  let activeTab = 'comms'
  let contents  = {}   // key → string
  let dirty     = {}   // key → bool
  let loading   = {}   // key → bool
  let saveStatus = {}  // key → { ok: bool, msg: string } | null

  onMount(loadAll)

  async function loadAll() {
    await Promise.all(CONFIGS.map(c => load(c.key)))
  }

  async function load(key) {
    loading = { ...loading, [key]: true }
    try {
      const res = await fetch(`/api/config/${key}`)
      contents  = { ...contents,  [key]: res.ok ? await res.text() : '' }
      dirty     = { ...dirty,     [key]: false }
      saveStatus = { ...saveStatus, [key]: null }
    } catch {
      contents = { ...contents, [key]: '' }
    } finally {
      loading = { ...loading, [key]: false }
    }
  }

  async function save(key) {
    loading    = { ...loading,    [key]: true  }
    saveStatus = { ...saveStatus, [key]: null  }
    try {
      const res = await fetch(`/api/config/${key}`, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content: contents[key] }),
      })
      if (res.ok) {
        dirty = { ...dirty, [key]: false }
        const cfg = CONFIGS.find(c => c.key === key)
        saveStatus = { ...saveStatus, [key]: {
          ok:  true,
          msg: cfg?.restart ? 'Saved — restart the app for changes to take effect.'
                            : 'Saved.',
        }}
      } else {
        const data = await res.json().catch(() => ({}))
        saveStatus = { ...saveStatus, [key]: { ok: false, msg: data.detail ?? 'Save failed.' } }
      }
    } catch (e) {
      saveStatus = { ...saveStatus, [key]: { ok: false, msg: String(e) } }
    } finally {
      loading = { ...loading, [key]: false }
    }
  }

  function onInput(key, value) {
    contents   = { ...contents,   [key]: value }
    dirty      = { ...dirty,      [key]: true  }
    saveStatus = { ...saveStatus, [key]: null  }
  }
</script>

<div class="config-editor">
  <div class="tabs">
    {#each CONFIGS as cfg (cfg.key)}
      <button
        class="tab"
        class:active={activeTab === cfg.key}
        on:click={() => activeTab = cfg.key}
      >
        {cfg.label}
        {#if dirty[cfg.key]}<span class="unsaved-dot" title="Unsaved changes"></span>{/if}
      </button>
    {/each}
  </div>

  {#each CONFIGS as cfg (cfg.key)}
    {#if activeTab === cfg.key}
      <div class="pane">
        {#if cfg.restart}
          <div class="restart-note">Changes require an application restart to take effect.</div>
        {/if}

        {#if loading[cfg.key] && contents[cfg.key] == null}
          <div class="loading">Loading…</div>
        {:else}
          <textarea
            class="yaml-area"
            value={contents[cfg.key] ?? ''}
            on:input={(e) => onInput(cfg.key, e.currentTarget.value)}
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        {/if}

        <div class="pane-footer">
          {#if saveStatus[cfg.key]}
            <span class="status" class:ok={saveStatus[cfg.key].ok}>
              {saveStatus[cfg.key].msg}
            </span>
          {:else}
            <span></span>
          {/if}
          <div class="footer-actions">
            <button class="reload-btn" on:click={() => load(cfg.key)} disabled={loading[cfg.key]}>
              Reload
            </button>
            <button
              class="save-btn"
              disabled={!dirty[cfg.key] || loading[cfg.key]}
              on:click={() => save(cfg.key)}
            >
              {loading[cfg.key] ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    {/if}
  {/each}
</div>

<style>
  .config-editor {
    display: flex;
    flex-direction: column;
    gap: 0;
    height: 100%;
  }

  .tabs {
    display: flex;
    gap: 0.25rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    flex-wrap: wrap;
  }

  .tab {
    padding: 0.3rem 0.75rem;
    border: 1px solid transparent;
    border-radius: 5px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    transition: color 0.15s, background 0.15s;
  }
  .tab:hover  { background: var(--border); color: var(--text); }
  .tab.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

  .unsaved-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
    display: inline-block;
  }

  .pane {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding-top: 0.75rem;
    flex: 1;
    min-height: 0;
  }

  .restart-note {
    font-size: 0.75rem;
    color: var(--text-muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 0.35rem 0.6rem;
  }

  .loading {
    color: var(--text-muted);
    font-size: 0.85rem;
    padding: 1rem 0;
  }

  .yaml-area {
    flex: 1;
    min-height: 480px;
    width: 100%;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem;
    font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.82rem;
    line-height: 1.55;
    resize: vertical;
    outline: none;
    transition: border-color 0.15s;
  }
  .yaml-area:focus { border-color: var(--accent); }

  .pane-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding-top: 0.25rem;
  }

  .footer-actions { display: flex; gap: 0.5rem; }

  .status {
    font-size: 0.8rem;
    color: var(--red);
  }
  .status.ok { color: var(--green); }

  .reload-btn, .save-btn {
    padding: 0.35rem 0.9rem;
    border-radius: 5px;
    border: 1px solid var(--border);
    cursor: pointer;
    font-size: 0.85rem;
    transition: background 0.15s, border-color 0.15s;
  }
  .reload-btn {
    background: transparent;
    color: var(--text-muted);
  }
  .reload-btn:hover:not(:disabled) { background: var(--border); color: var(--text); }

  .save-btn {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
    font-weight: 600;
  }
  .save-btn:hover:not(:disabled) { filter: brightness(1.1); }
  .save-btn:disabled, .reload-btn:disabled { opacity: 0.4; cursor: default; }
</style>
