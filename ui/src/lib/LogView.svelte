<script>
  import { afterUpdate, onMount } from 'svelte'
  import { logEntries, dcnEntries } from '../stores/ws.js'

  let tab         = 'general'
  let paused      = false
  let logEl       = null
  let dcnEl       = null
  let clearedAt   = { general: 0, dcn: 0 }
  let dcnBusFilter  = 'all'
  let dcnDirFilter  = 'all'   // 'all' | 'rx' | 'tx'
  let dcnAddrFilter = ''
  let dcnRaw        = false
  let configuredBuses = []

  onMount(async () => {
    try {
      const res = await fetch('/api/comms/buses')
      if (res.ok) {
        const data = await res.json()
        configuredBuses = data.buses ?? []
      }
    } catch { /* ignore */ }
  })

  $: trafficBuses = [...new Set($dcnEntries.map(e => e.bus).filter(Boolean))]
  $: dcnBuses    = [...new Set([...configuredBuses, ...trafficBuses])].sort()
  $: visibleLogs = $logEntries.filter(e => e.ts > clearedAt.general)
  $: visibleDcn  = $dcnEntries.filter(e => {
      if (e.ts <= clearedAt.dcn) return false
      if (dcnBusFilter !== 'all' && e.bus !== dcnBusFilter) return false
      if (dcnDirFilter !== 'all' && e.direction !== dcnDirFilter) return false
      if (dcnAddrFilter) {
        const a = dcnAddrFilter.trim().toLowerCase()
        if (!e.from_addr?.toLowerCase().includes(a) && !e.to_addr?.toLowerCase().includes(a)) return false
      }
      return true
    })

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

  {#if tab === 'dcn'}
    <div class="filter-bar">
      <div class="dir-group">
        <button class="dir-btn" class:active={dcnDirFilter === 'all'} on:click={() => dcnDirFilter = 'all'}>All</button>
        <button class="dir-btn rx" class:active={dcnDirFilter === 'rx'} on:click={() => dcnDirFilter = 'rx'}>RX</button>
        <button class="dir-btn tx" class:active={dcnDirFilter === 'tx'} on:click={() => dcnDirFilter = 'tx'}>TX</button>
      </div>
      <input
        class="addr-input"
        type="text"
        placeholder="Address"
        bind:value={dcnAddrFilter}
        maxlength="4"
      />
      {#if dcnBuses.length > 0}
        <select class="bus-select" bind:value={dcnBusFilter}>
          <option value="all">All buses</option>
          {#each dcnBuses as b}
            <option value={b}>{b}</option>
          {/each}
        </select>
      {/if}
      <button class="act-btn" class:active={dcnRaw} on:click={() => dcnRaw = !dcnRaw}>Raw</button>
    </div>
  {/if}

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
          {#if dcnRaw}
            <span class="msg raw">{e.raw ?? e.payload ?? ''}</span>
          {:else}
            <span class="addr">{e.from_addr ?? '?'}&#x2192;{e.to_addr ?? '?'}</span>
            <span class="msg">{e.payload ?? e.raw ?? ''}</span>
          {/if}
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

  .actions { display: flex; gap: 0.4rem; align-items: center; }

  /* DCN filter bar */
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .dir-group {
    display: flex;
    border: 1px solid var(--border);
    border-radius: 5px;
    overflow: hidden;
  }
  .dir-btn {
    padding: 0.22rem 0.55rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.78rem;
    font-weight: 600;
    transition: background 0.12s, color 0.12s;
  }
  .dir-btn + .dir-btn { border-left: 1px solid var(--border); }
  .dir-btn:hover { background: var(--border); color: var(--text); }
  .dir-btn.active          { background: var(--accent-dim); color: var(--accent); }
  .dir-btn.rx.active       { background: color-mix(in srgb, var(--green) 15%, transparent); color: var(--green); }
  .dir-btn.tx.active       { background: var(--accent-dim); color: var(--accent); }

  .addr-input {
    width: 7ch;
    padding: 0.22rem 0.45rem;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--surface);
    color: var(--text);
    font-size: 0.78rem;
    font-family: ui-monospace, monospace;
    text-transform: uppercase;
  }
  .addr-input::placeholder { color: var(--text-muted); text-transform: none; }
  .addr-input:focus { outline: none; border-color: var(--accent); }

  .bus-select {
    padding: 0.22rem 0.45rem;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--surface);
    color: var(--text);
    font-size: 0.78rem;
    cursor: pointer;
  }
  .bus-select:focus { outline: none; border-color: var(--accent); }

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
  .act-btn:hover  { background: var(--border); color: var(--text); }
  .act-btn.paused { border-color: var(--accent); color: var(--accent); }
  .act-btn.active { border-color: var(--accent); color: var(--accent); }

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
  .msg.raw { font-size: 0.74rem; color: var(--text-muted); }

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
