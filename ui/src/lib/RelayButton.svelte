<script>
  import { sendCmd } from '../stores/ws.js'

  export let hardwareKey
  export let label      = ''
  export let value      = 0
  export let deviceAddr = '01'
  export let relayNum   = 1
  export let bus        = ''     // explicit DCN bus name; empty = auto-detect
  export let standalone = true   // false when hosted inside a dashboard card

  const TIMEOUT_MS   = 3000   // wait up to 3 s for device confirmation
  const FAIL_SHOW_MS = 4000   // show failure indicator for 4 s then reset

  $: active  = value >= 0.5
  $: display = label || hardwareKey

  let pending     = false
  let failed      = false
  let pendingFrom = null    // value at the moment the command was sent
  let pendingTimer = null
  let failTimer    = null

  // When the confirmed value changes away from what it was when we clicked,
  // the device has acknowledged the command — clear pending state.
  $: if (pending && value !== pendingFrom) {
    clearTimeout(pendingTimer)
    pendingTimer = null
    pending     = false
    failed      = false
    pendingFrom = null
  }

  function toggle() {
    if (pending) return
    const next = active ? 0 : 1
    pendingFrom = value
    pending     = true
    failed      = false
    if (failTimer) { clearTimeout(failTimer); failTimer = null }

    pendingTimer = setTimeout(() => {
      pending      = false
      failed       = true
      pendingFrom  = null
      failTimer = setTimeout(() => { failed = false }, FAIL_SHOW_MS)
    }, TIMEOUT_MS)

    const cmd = { type: 'relay_cmd', key: hardwareKey, relay_num: relayNum, state: next, device_addr: deviceAddr }
    if (bus) cmd.bus = bus
    sendCmd(cmd)
  }
</script>

<button
  class="relay-btn"
  class:active
  class:pending
  class:failed
  class:embedded={!standalone}
  disabled={pending}
  on:click={toggle}
  title={hardwareKey}
>
  <span class="dot" class:on={active && !pending && !failed} class:pending class:failed></span>
  <span class="relay-label">{display}</span>
  {#if failed}<span class="relay-err">✕ No response</span>{/if}
</button>

<style>
  .relay-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 0.85rem;
    transition: border-color 0.15s, background 0.15s, opacity 0.15s;
    width: 100%; height: 100%; box-sizing: border-box;
    text-align: left;
  }
  .relay-btn.active            { border-color: var(--accent); background: var(--accent-dim); }
  .relay-btn:hover:not(:disabled) { border-color: var(--accent); }
  .relay-btn.pending           { cursor: wait; opacity: 0.8; }
  .relay-btn.failed            { border-color: var(--red); }

  /* Inside a dashboard card — card provides border/background/radius */
  .relay-btn.embedded {
    border: none;
    border-radius: 0;
    background: transparent;
  }
  .relay-btn.embedded.active { background: var(--accent-dim); }
  .relay-btn.embedded.failed { background: rgba(204, 51, 51, 0.08); }

  .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
    transition: background 0.15s, box-shadow 0.15s;
  }
  .dot.on      { background: var(--green); box-shadow: 0 0 5px var(--green); }
  .dot.pending {
    background: #f0a030;
    box-shadow: 0 0 5px #f0a030;
    animation: blink 0.7s ease-in-out infinite alternate;
  }
  .dot.failed  { background: var(--red); box-shadow: 0 0 5px var(--red); }

  .relay-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }

  .relay-err {
    font-size: 0.68rem;
    color: var(--red);
    white-space: nowrap;
    flex-shrink: 0;
  }

  @keyframes blink {
    from { opacity: 1;   }
    to   { opacity: 0.3; }
  }
</style>
