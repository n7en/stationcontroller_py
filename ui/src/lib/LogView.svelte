<script>
  import { afterUpdate } from 'svelte'
  import { logEntries, dcnEntries } from '../stores/ws.js'

  let tab      = 'general'
  let paused   = false
  let logEl    = null
  let dcnEl    = null
  let clearedAt = { general: 0, dcn: 0 }

  $: visibleLogs = $logEntries.filter(e => e.ts > clearedAt.general)
  $: visibleDcn  = $dcnEntries.filter(e => e.ts > clearedAt.dcn)

  afterUpdate(() => {
    if (!paused && tab === 'general' && visibleLogs.length && logEl) {
      logEl.scrollTop = logEl.scrollHeight
    }
    if (!paused && tab === 'dcn' && visibleDcn.length && dcnEl) {
      dcnEl.scrollTop = dcnEl.scrollHeight
    }
  })

  function clear() {
    clearedAt = { ...clearedAt, [tab]: Date.now() / 1000 }
  }

  function fmtTs(ts) {
    return new Date(ts * 1000).toTimeString().slice(0, 8)
  }

  function levelCls(level) {
    if (level === 'WARNING')                    return 'warn'
    if (level === 'ERROR' || level === 'CRITICAL') return 'err'
    if (level === 'DEBUG')                      return 'debug'
    return ''
  }
</script>

<div class="log-view">
  <div class="toolbar">
    <div class="tabs">
      <button class="tab" class:active={tab === 'general'} on:click={() => tab = 'general'}>
        General <span class="badge">{visibleLogs.length}</span>
      </button>
      <button class="tab" class:active={tab === 'dcn'} on:click={() => tab = 'dcn'}>
        DCN <span class="badge">{visibleDcn.length}</span>
      </button>
    </div>
    <div class="actions">
      <button class="act-btn" class:paused on:click={() => paused = !paused}>
        {paused ? 'Resume' : 'Pause'}
      </button>
      <button class="act-btn" on:click={clear}>Clear</button>
    </div>
  </div>

  {#if tab === 'general'}
    <div class="pane" bind:this={logEl}>
      {#each visibleLogs as e, i (i)}
        <div class="row {levelCls(e.level)}">
          <span class="ts">{fmtTs(e.ts)}</span>
          <span class="lvl">{e.level}</span>
          <span class="src">{e.logger}</span>
          <span class="msg">{e.msg}</span>
          {#if e.exc}<div class="exc">{e.exc}</div>{/if}
        </div>
      {:else}
        <div class="empty">No log entries yet.</div>
      {/each}
    </div>

  {:else}
    <div class="pane" bind:this={dcnEl}>
      {#each visibleDcn as e, i (i)}
        <div class="row dcn-{e.direction}">
          <span class="ts">{fmtTs(e.ts)}</span>
          <span class="dir">{e.direction?.toUpperCase()}</span>
          <span class="src">{e.bus ?? ''}</span>
          <span class="addr">{e.from_addr ?? '?'}&#x2192;{e.to_addr ?? '?'}</span>
          <span class="msg">{e.payload ?? e.raw ?? ''}</span>
        </div>
      {:else}
        <div class="empty">No DCN messages yet.</div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .log-view {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    gap: 0;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .tabs { display: flex; gap: 0.25rem; }

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
    gap: 0.4rem;
    transition: color 0.15s, background 0.15s;
  }
  .tab:hover  { background: var(--border); color: var(--text); }
  .tab.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

  .badge {
    font-size: 0.7rem;
    background: var(--border);
    color: var(--text-muted);
    border-radius: 10px;
    padding: 0 0.4rem;
    min-width: 1.4em;
    text-align: center;
  }
  .tab.active .badge { background: var(--accent-dim); color: var(--accent); }

  .actions { display: flex; gap: 0.4rem; }

  .act-btn {
    padding: 0.28rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.8rem;
    transition: background 0.15s, color 0.15s;
  }
  .act-btn:hover { background: var(--border); color: var(--text); }
  .act-btn.paused { border-color: var(--accent); color: var(--accent); }

  .pane {
    flex: 1;
    overflow-y: auto;
    font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.78rem;
    line-height: 1.5;
    padding: 0.5rem 0;
    min-height: 0;
  }

  .row {
    display: flex;
    gap: 0.6rem;
    padding: 0.05rem 0.5rem;
    border-radius: 3px;
    white-space: pre;
    overflow: hidden;
  }
  .row:hover { background: var(--surface); }

  .ts   { color: var(--text-muted); flex-shrink: 0; }
  .lvl  { flex-shrink: 0; width: 8ch; color: var(--text-muted); }
  .src  { flex-shrink: 0; width: 18ch; overflow: hidden; color: var(--text-muted); }
  .dir  { flex-shrink: 0; width: 3ch; font-weight: 600; }
  .addr { flex-shrink: 0; width: 8ch; color: var(--text-muted); }
  .msg  { overflow: hidden; text-overflow: ellipsis; color: var(--text); }

  .exc {
    width: 100%;
    white-space: pre-wrap;
    color: var(--red);
    padding-left: 1rem;
    margin-top: 0.1rem;
  }

  /* Level colours */
  .warn .lvl  { color: #f0b860; }
  .warn .msg  { color: #f0b860; }
  .err .lvl   { color: var(--red); }
  .err .msg   { color: var(--red); }
  .debug .lvl { color: var(--border); }
  .debug .msg { color: var(--text-muted); }

  /* DCN direction colours */
  .dcn-rx .dir { color: var(--green); }
  .dcn-tx .dir { color: var(--accent); }

  .empty {
    color: var(--text-muted);
    font-size: 0.82rem;
    padding: 1rem 0.5rem;
    font-style: italic;
  }
</style>
