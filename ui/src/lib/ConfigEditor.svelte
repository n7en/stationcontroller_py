<script>
  import { onMount } from 'svelte'

  const CONFIGS = [
    { key: 'comms',      label: 'Comms / Serial', restart: true  },
    { key: 'labels',     label: 'Labels',          restart: false },
    { key: 'radio',      label: 'Radio',           restart: true  },
    { key: 'automation', label: 'Automation',       restart: false },
    { key: 'telemetry',  label: 'Telemetry',        restart: true  },
    { key: 'auth',       label: 'Auth',             restart: true  },
  ]

  let activeTab  = $state('comms')
  let contents   = $state({})
  let dirty      = $state({})
  let loading    = $state({})
  let saveStatus = $state({})
  let errors     = $state({})

  // DOM refs to the highlight <pre> elements (keyed by config key)
  let hlEls = {}

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

  function syncScroll(key, e) {
    const el = hlEls[key]
    if (el) {
      el.scrollTop  = e.target.scrollTop
      el.scrollLeft = e.target.scrollLeft
    }
  }

  // Tab key → insert 2 spaces instead of moving focus
  function onKeydown(key, e) {
    if (e.key !== 'Tab') return
    e.preventDefault()
    const ta    = e.currentTarget
    const start = ta.selectionStart
    const end   = ta.selectionEnd
    ta.value    = ta.value.slice(0, start) + '  ' + ta.value.slice(end)
    ta.selectionStart = ta.selectionEnd = start + 2
    onInput(key, ta.value)
  }

  // ── YAML syntax highlighter ──────────────────────────────────────────────

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }

  function colorVal(v) {
    if (!v) return ''
    const trimmed = v.trimStart()
    const quoted  = trimmed.startsWith('"') || trimmed.startsWith("'")

    // Split off trailing inline comment (only when not inside a quoted string)
    let val = v, cmt = ''
    if (!quoted) {
      const ci = v.search(/ #/)
      if (ci > 0) { val = v.slice(0, ci); cmt = v.slice(ci) }
    }

    const t = val.trim()
    let colored
    if (t.startsWith('"') || t.startsWith("'")) {
      colored = `<span class="yc-str">${esc(val)}</span>`
    } else if (t && /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(t)) {
      colored = `<span class="yc-num">${esc(val)}</span>`
    } else if (t && /^(true|false|yes|no|null|~)$/i.test(t)) {
      colored = `<span class="yc-bool">${esc(val)}</span>`
    } else if (/^[|>]/.test(t)) {
      colored = `<span class="yc-str">${esc(val)}</span>`
    } else {
      colored = esc(val)
    }

    return colored + (cmt ? `<span class="yc-cmt">${esc(cmt)}</span>` : '')
  }

  function highlightLine(line) {
    if (!line.trim()) return ''

    // Full comment line
    if (/^\s*#/.test(line)) return `<span class="yc-cmt">${esc(line)}</span>`

    // Key: value  (handles optional indent + optional list bullet)
    // Match: indent  [- ]  key  [:space or :EOL]  value
    const km = line.match(/^(\s*)((?:-\s+)?)([^#:'"|\s][^:#]*)(\s*:\s+|\s*:\s*$)(.*)$/)
    if (km) {
      const [, indent, bullet, key, sep, rest] = km
      return esc(indent)
           + (bullet ? `<span class="yc-bull">${esc(bullet)}</span>` : '')
           + `<span class="yc-key">${esc(key)}</span>`
           + `<span class="yc-sep">${esc(sep)}</span>`
           + colorVal(rest)
    }

    // List item without a key
    const lm = line.match(/^(\s*)(- )(.*)$/)
    if (lm) {
      return esc(lm[1]) + `<span class="yc-bull">${esc(lm[2])}</span>` + colorVal(lm[3])
    }

    return esc(line)
  }

  function highlightYaml(text) {
    if (!text) return ''
    // Trailing \n keeps the pre tall enough to match the textarea's last blank line
    return text.split('\n').map(highlightLine).join('\n') + '\n'
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
        {:else}
          {#if errors[cfg.key]}
            <div class="error-msg">{errors[cfg.key]}</div>
          {/if}

          <div class="editor-wrap" class:focused={false}>
            <pre
              class="yaml-hl"
              bind:this={hlEls[cfg.key]}
              aria-hidden="true"
            >{@html highlightYaml(contents[cfg.key] ?? '')}</pre>
            <textarea
              class="yaml-area"
              value={contents[cfg.key] ?? ''}
              oninput={(e) => onInput(cfg.key, e.currentTarget.value)}
              onscroll={(e) => syncScroll(cfg.key, e)}
              onkeydown={(e) => onKeydown(cfg.key, e)}
              spellcheck="false"
              autocomplete="off"
            ></textarea>
          </div>
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

  /* ── Overlay editor ── */
  .editor-wrap {
    position: relative;
    flex: 1;
    min-height: 480px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg);
    overflow: hidden;
    transition: border-color 0.15s;
  }
  .editor-wrap:focus-within { border-color: var(--accent); }

  /* Shared font metrics — must be identical on both layers */
  .yaml-hl,
  .yaml-area {
    font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.82rem;
    line-height: 1.55;
    padding: 0.75rem;
    tab-size: 2;
    white-space: pre-wrap;
    word-wrap: break-word;
    text-align: left;
  }

  /* Highlight layer — sits behind the textarea */
  .yaml-hl {
    position: absolute;
    inset: 0;
    margin: 0;
    overflow: hidden;       /* scroll is driven by the textarea */
    pointer-events: none;
    color: var(--text);
    background: transparent;
  }

  /* Edit layer — transparent text so the highlight shows through */
  .yaml-area {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: none;
    outline: none;
    resize: none;
    background: transparent;
    color: transparent;
    caret-color: var(--text);
    overflow: auto;
  }

  /* ── YAML token colours ── */
  :global(.yc-key)  { color: var(--accent); }
  :global(.yc-str)  { color: var(--green);  }
  :global(.yc-num)  { color: #f0b860;       }
  :global(.yc-bool) { color: #c792ea;       }
  :global(.yc-cmt)  { color: var(--text-muted); font-style: italic; }
  :global(.yc-bull) { color: var(--accent); opacity: 0.7; }
  :global(.yc-sep)  { color: var(--text-muted); }

  /* ── Footer ── */
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
