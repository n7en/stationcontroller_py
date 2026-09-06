<script>
  let state = 'idle'   // idle | confirming | restarting | error
  let errorMsg = ''

  function requestRestart() {
    state = 'confirming'
  }

  function cancelRestart() {
    state = 'idle'
  }

  async function confirmRestart() {
    state = 'restarting'
    try {
      const r = await fetch('/api/system/restart', { method: 'POST' })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        throw new Error(d.detail ?? `HTTP ${r.status}`)
      }
      // The server will restart — poll until it responds again, then reload.
      await pollUntilBack()
      window.location.reload()
    } catch (e) {
      errorMsg = e.message
      state = 'error'
    }
  }

  async function pollUntilBack(maxWaitMs = 30_000, intervalMs = 800) {
    const deadline = Date.now() + maxWaitMs
    // Brief pause so the server has time to begin its exit
    await sleep(1200)
    while (Date.now() < deadline) {
      try {
        const r = await fetch('/api/update/status', { cache: 'no-store' })
        if (r.ok) return   // server is back
      } catch (_) {}
      await sleep(intervalMs)
    }
    throw new Error('Server did not come back within 30 s')
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms))
</script>

<div class="system-controls">
  <h2>System</h2>

  <div class="card">
    <div class="card-body">
      <div class="card-label">Application</div>
      <div class="card-desc">
        Restart the StationController process. The page will reload automatically
        once the server is back online.
      </div>
    </div>

    <div class="card-action">
      {#if state === 'idle'}
        <button class="btn-danger-outline" on:click={requestRestart}>
          Restart app
        </button>

      {:else if state === 'confirming'}
        <span class="confirm-label">Restart now?</span>
        <button class="btn-danger" on:click={confirmRestart}>Yes, restart</button>
        <button on:click={cancelRestart}>Cancel</button>

      {:else if state === 'restarting'}
        <span class="status-msg">
          <span class="spinner"></span> Restarting…
        </span>

      {:else if state === 'error'}
        <span class="error-msg">{errorMsg}</span>
        <button on:click={() => state = 'idle'}>Dismiss</button>
      {/if}
    </div>
  </div>
</div>

<style>
  .system-controls {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-width: 700px;
  }
  h2 { margin: 0; font-size: 1.1rem; }

  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    flex-wrap: wrap;
  }
  .card-body { display: flex; flex-direction: column; gap: 0.2rem; flex: 1; }
  .card-label { font-size: 0.85rem; font-weight: 600; }
  .card-desc  { font-size: 0.75rem; color: var(--text-muted); }

  .card-action {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .confirm-label { font-size: 0.82rem; color: var(--text-muted); }

  .status-msg, .error-msg {
    font-size: 0.82rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .error-msg { color: var(--red); }

  /* Spinner */
  .spinner {
    display: inline-block;
    width: 12px; height: 12px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Buttons */
  button {
    padding: 0.3rem 0.75rem;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.82rem;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    transition: background 0.15s, border-color 0.15s;
    white-space: nowrap;
  }
  button:hover { background: var(--border); }

  .btn-danger-outline {
    color: var(--red);
    border-color: rgba(233, 98, 98, 0.4);
  }
  .btn-danger-outline:hover { background: rgba(233, 98, 98, 0.08); }

  .btn-danger {
    color: var(--red);
    border-color: rgba(233, 98, 98, 0.4);
    background: rgba(233, 98, 98, 0.08);
  }
  .btn-danger:hover { background: rgba(233, 98, 98, 0.18); }
</style>
