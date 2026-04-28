<script>
  import { onMount } from 'svelte'

  const CONFIGS = [
    { key: 'comms',      label: 'Communications', restart: true  },
    { key: 'radio',      label: 'Radio',          restart: true  },
    { key: 'automation', label: 'Automation',      restart: false },
    { key: 'telemetry',  label: 'Telemetry',       restart: true  },
  ]

  let activeTab  = $state('comms')
  let contents   = $state({})   // key → string | null
  let dirty      = $state({})   // key → bool
  let loading    = $state({})   // key → bool
  let saveStatus = $state({})   // key → { ok: bool, msg: string } | null
  let errors     = $state({})   // key → string | null

  onMount(loadAll)

  async function loadAll() {
    await Promise.all(CONFIGS.map(c => load(c.key)))
  }

  async function load(key) {
    loading[key]    = true
    errors[key]     = null
    saveStatus[key] = null
    try {
      const res = await fetch(`/api/config/${key}`)
      if (res.ok) {
        contents[key] = await res.text()
        dirty[key]    = false
      } else {
        errors[key]   = `Server returned ${res.status}`
        contents[key] = ''
      }
    } catch (e) {
      errors[key]   = `Fetch failed: ${e.message ?? e}`
      contents[key] = ''
    } finally {
      loading[key] = false
    }
  }

  async function save(key) {
    loading[key]    = true
    saveStatus[key] = null
    try {
      const res = await fetch(`/api/config/${key}`, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content: contents[key] }),
      })
      if (res.ok) {
        dirty[key] = false
        const cfg  = CONFIGS.find(c => c.key === key)
        saveStatus[key] = {
          ok:  true,
          msg: cfg?.restart ? 'Saved. Restart the app for changes to take effect.'
                            : 'Saved.',
        }
      } else {
        const data = await res.json().catch(() => ({}))
        saveStatus[key] = { ok: false, msg: data.detail ?? 'Save failed.' }
      }
    } catch (e) {
      saveStatus[key] = { ok: false, msg: String(e) }
    } finally {
      loading[key] = false
    }
  }

  function onInput(key, value) {
    contents[key]   = value
    dirty[key]      = true
    saveStatus[key] = null
  }
</script>

<div class="config-editor">
  <div class="tabs">
    {#each CONFIGS as cfg (cfg.key)}
      <button
        class="tab"
        class:active={activeTab === cfg.key}
        onclick={() => activeTab = cfg.key}
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
          <div class="loading">Loading...</div>
        {:else if errors[cfg.key]}
          <div class="error-msg">{errors[cfg.key]}</div>
          <textarea
            class="yaml-area"
            value={contents[cfg.key] ?? ''}
            oninput={(e) => onInput(cfg.key, e.currentTarget.value)}
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        {:else}
          <textarea
            class="yaml-area"
            value={contents[cfg.key] ?? ''}
            oninput={(e) => onInput(cfg.key, e.currentTarget.value)}
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
            <button class="reload-btn" onclick={() => load(cfg.key)} disabled={loading[cfg.key]}>
              Reload
            </button>
            <button
              class="save-btn"
              disabled={!dirty[cfg.key] || loading[cfg.key]}
              onclick={() => save(cfg.key)}
            >
              {loading[cfg.key] ? 'Saving...' : 'Save'}
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

  .error-msg {
    font-size: 0.8rem;
    color: var(--red);
    padding: 0.35rem 0.6rem;
    background: rgba(233,98,98,0.08);
    border: 1px solid var(--red);
    border-radius: 5px;
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
