<script>
  let includeDb  = false
  let restoring  = false
  let restoreRes = null    // {ok, restored_files, db_staged, ...}
  let error      = null
  let fileInput

  function download() {
    // Navigate to the endpoint - the browser handles the file download
    window.location.href = `/api/system/backup?include_db=${includeDb}`
  }

  async function restore() {
    const file = fileInput?.files?.[0]
    if (!file) return
    if (!confirm(
      `Restore configuration from "${file.name}"?\n\n` +
      'Current config files will be overwritten (a snapshot is saved first). ' +
      'A restart is required afterwards.'
    )) return

    restoring  = true
    error      = null
    restoreRes = null
    try {
      const r = await fetch('/api/system/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail ?? `HTTP ${r.status}`)
      restoreRes = d
    } catch (e) {
      error = e.message
    } finally {
      restoring = false
    }
  }

  async function restartNow() {
    await fetch('/api/system/restart', { method: 'POST' })
  }
</script>

<div class="backup-panel">
  <div class="panel-title">Backup &amp; Restore</div>

  <div class="row">
    <button class="btn-primary" on:click={download}>Download Backup</button>
    <label class="chk">
      <input type="checkbox" bind:checked={includeDb} />
      Include telemetry database
    </label>
  </div>
  <p class="hint">
    Backs up all YAML configuration (buses, devices, radio, automations,
    dashboards, labels). Certificates are excluded and regenerated on install.
  </p>

  <div class="row">
    <input type="file" accept=".zip" bind:this={fileInput} />
    <button on:click={restore} disabled={restoring}>
      {restoring ? 'Restoring…' : 'Restore'}
    </button>
  </div>

  {#if error}
    <div class="banner err">{error}</div>
  {/if}
  {#if restoreRes}
    <div class="banner ok">
      Restored {restoreRes.restored_files.length} config file(s){restoreRes.db_staged ? ' + staged database' : ''}.
      Previous config saved as {restoreRes.pre_restore_snapshot} in data/backups/.
      <button class="btn-restart" on:click={restartNow}>Restart now</button>
    </div>
  {/if}
</div>

<style>
  .backup-panel {
    display: flex; flex-direction: column; gap: 0.6rem;
    padding: 0.9rem 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    max-width: 700px;
  }
  .panel-title { font-weight: 600; font-size: 0.9rem; }

  .row { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }

  .chk {
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-size: 0.8rem; color: var(--text-muted); cursor: pointer;
  }

  .hint { font-size: 0.75rem; color: var(--text-muted); margin: 0; line-height: 1.5; }

  input[type="file"] {
    font-size: 0.78rem; color: var(--text-muted);
    max-width: 300px;
  }

  button {
    padding: 0.3rem 0.75rem; border-radius: 5px; cursor: pointer;
    font-size: 0.82rem; border: 1px solid var(--border);
    background: var(--surface); color: var(--text);
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { border-color: var(--accent); color: var(--accent); }
  .btn-primary:hover { background: var(--accent-dim); }

  .banner {
    padding: 0.4rem 0.6rem; border-radius: 4px; font-size: 0.82rem;
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
  }
  .banner.err {
    background: rgba(233, 98, 98, 0.12); color: var(--red);
    border: 1px solid rgba(233, 98, 98, 0.3);
  }
  .banner.ok {
    background: rgba(62, 207, 142, 0.1); color: var(--green);
    border: 1px solid rgba(62, 207, 142, 0.25);
  }
  .btn-restart { border-color: var(--green); color: var(--green); }
</style>
