<script>
  import { onMount } from 'svelte'
  import { updateAvailable } from '../stores/ws.js'

  let githubUrl    = ''
  let currentVer   = '…'
  let editingUrl   = false
  let urlDraft     = ''
  let checking     = false
  let savingUrl    = false
  let result       = null   // null | { update_available, latest_version, release_url,
                            //           release_notes, published_at, message, error }

  // When the background task finds an update and broadcasts it, reflect it here.
  $: if ($updateAvailable && !result?.update_available) {
    result = {
      configured:       true,
      update_available: true,
      latest_version:   $updateAvailable.latest_version,
      release_url:      $updateAvailable.release_url,
      published_at:     $updateAvailable.published_at,
      release_notes:    '',
    }
  }

  onMount(async () => {
    const [cfgRes, statusRes] = await Promise.all([
      fetch('/api/update/config'),
      fetch('/api/update/status'),
    ])
    const cfg    = await cfgRes.json()
    const status = await statusRes.json()

    githubUrl  = cfg.github_url      || ''
    currentVer = cfg.current_version || 'unknown'

    // Show cached result immediately if a check has already run.
    if (status.current_version) result = status
  })

  function startEdit() {
    urlDraft   = githubUrl
    editingUrl = true
    result     = null
  }

  function cancelEdit() {
    editingUrl = false
  }

  async function saveUrl() {
    savingUrl = true
    try {
      await fetch('/api/update/config', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ github_url: urlDraft }),
      })
      githubUrl  = urlDraft
      editingUrl = false
      result     = null
    } finally {
      savingUrl = false
    }
  }

  async function checkForUpdates() {
    checking = true
    result   = null
    try {
      const r = await fetch('/api/update/check')
      result  = await r.json()
    } catch (e) {
      result = { error: e.message }
    }
    checking = false
  }

  $: resultClass = !result ? ''
    : result.error          ? 'error'
    : result.update_available ? 'update'
    : 'ok'

  function fmtDate(iso) {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  }
</script>

<div class="update-cfg">
  <h2>Software Update</h2>

  <!-- Current version row -->
  <div class="version-row">
    <span class="version-label">Installed version</span>
    <span class="version-badge">v{currentVer}</span>
  </div>

  <!-- GitHub URL -->
  <div class="field">
    <label for="gh-url">GitHub repository</label>
    {#if editingUrl}
      <div class="url-edit-row">
        <input
          id="gh-url"
          bind:value={urlDraft}
          placeholder="https://github.com/owner/repo"
          on:keydown={(e) => e.key === 'Enter' && saveUrl()}
        />
        <button class="btn-primary" on:click={saveUrl} disabled={savingUrl}>
          {savingUrl ? 'Saving…' : 'Save'}
        </button>
        <button class="btn-secondary" on:click={cancelEdit}>Cancel</button>
      </div>
    {:else}
      <div class="url-display-row">
        <span class="url-text">
          {#if githubUrl}
            <a href={githubUrl} target="_blank" rel="noopener">{githubUrl}</a>
          {:else}
            <span class="placeholder">Not configured</span>
          {/if}
        </span>
        <button class="btn-secondary" on:click={startEdit}>Edit</button>
      </div>
    {/if}
  </div>

  <!-- Check button -->
  <div class="actions">
    <button class="btn-primary" on:click={checkForUpdates}
            disabled={checking || !githubUrl || editingUrl}>
      {checking ? 'Checking…' : 'Check for updates'}
    </button>
  </div>

  <!-- Result -->
  {#if result}
    <div class="result {resultClass}">
      {#if result.error}
        <span class="result-icon">✕</span>
        <span>{result.error}</span>

      {:else if !result.configured}
        <span class="result-icon">—</span>
        <span>No repository configured.</span>

      {:else if result.message}
        <!-- no releases yet -->
        <span class="result-icon">·</span>
        <span>{result.message}</span>

      {:else if result.update_available}
        <div class="result-header">
          <span class="result-icon">↑</span>
          <strong>{result.latest_version} available</strong>
          {#if result.published_at}
            <span class="result-date">— released {fmtDate(result.published_at)}</span>
          {/if}
          <a class="gh-link" href={result.release_url} target="_blank" rel="noopener">
            View on GitHub ↗
          </a>
        </div>
        {#if result.release_notes}
          <pre class="release-notes">{result.release_notes}</pre>
        {/if}

      {:else}
        <span class="result-icon">✓</span>
        <span>Already up to date (v{result.current_version}).</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .update-cfg { max-width: 600px; }
  h2 { margin: 0 0 1rem; font-size: 1.1rem; }

  .version-row {
    display: flex; align-items: center; gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .version-label { font-size: 0.78rem; color: var(--text-muted); }
  .version-badge {
    font-size: 0.82rem; font-weight: 600;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    background: var(--accent-dim);
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }

  .field { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.9rem; }
  label  { font-size: 0.75rem; color: var(--text-muted); }

  .url-edit-row {
    display: flex; gap: 0.5rem; align-items: center;
  }
  .url-edit-row input {
    flex: 1;
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    font-size: 0.85rem;
  }
  .url-edit-row input:focus { outline: none; border-color: var(--accent); }

  .url-display-row {
    display: flex; align-items: center; gap: 0.75rem;
  }
  .url-text {
    flex: 1; font-size: 0.85rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .url-text a { color: var(--accent); text-decoration: none; }
  .url-text a:hover { text-decoration: underline; }
  .placeholder { color: var(--text-muted); font-style: italic; }

  .actions { margin-bottom: 0.9rem; }

  button {
    padding: 0.35rem 0.85rem;
    border-radius: 5px; cursor: pointer; font-size: 0.85rem;
    border: 1px solid var(--border);
    background: var(--surface); color: var(--text);
    transition: background 0.15s, border-color 0.15s;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary  { border-color: var(--accent); color: var(--accent); }
  .btn-primary:not(:disabled):hover  { background: var(--accent-dim); }
  .btn-secondary:not(:disabled):hover { background: var(--border); }

  /* Result banner */
  .result {
    padding: 0.55rem 0.75rem;
    border-radius: 5px;
    font-size: 0.83rem;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-muted);
  }
  .result.ok     { border-color: rgba(62,207,142,0.3);  background: rgba(62,207,142,0.07); color: var(--green); }
  .result.update { border-color: rgba(78,154,241,0.35); background: rgba(78,154,241,0.08); color: var(--accent); }
  .result.error  { border-color: rgba(233,98,98,0.3);   background: rgba(233,98,98,0.07);  color: var(--red); }

  .result-icon { font-weight: 700; margin-right: 0.4rem; }

  .result-header {
    display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap;
  }
  .result-date { font-size: 0.78rem; color: var(--text-muted); }
  .gh-link {
    margin-left: auto; font-size: 0.78rem;
    color: var(--accent); text-decoration: none;
  }
  .gh-link:hover { text-decoration: underline; }

  .release-notes {
    margin: 0.6rem 0 0;
    padding: 0.5rem 0.6rem;
    border-radius: 4px;
    background: var(--bg);
    font-size: 0.78rem;
    font-family: monospace;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-muted);
    max-height: 180px;
    overflow-y: auto;
  }
</style>
