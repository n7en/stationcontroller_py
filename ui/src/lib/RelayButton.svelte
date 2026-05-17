<script>
  import { sendCmd } from '../stores/ws.js'

  export let hardwareKey   // e.g. "ant_relay_1"
  export let label = ''    // friendly name
  export let value = 0     // current state: 1=on, 0=off
  export let deviceAddr = '01'
  export let relayNum = 1

  $: active = value >= 0.5
  $: display = label || hardwareKey

  function toggle() {
    const next = active ? 0 : 1
    sendCmd({ type: 'relay_cmd', key: hardwareKey, relay_num: relayNum, state: next, device_addr: deviceAddr })
  }
</script>

<button class="relay-btn" class:active on:click={toggle} title={hardwareKey}>
  <span class="dot" class:on={active}></span>
  <span class="relay-label">{display}</span>
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
    transition: border-color 0.15s, background 0.15s;
    width: 100%; height: 100%; box-sizing: border-box;
    text-align: left;
  }
  .relay-btn.active { border-color: var(--accent); background: var(--accent-dim); }
  .relay-btn:hover { border-color: var(--accent); }

  .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--text-muted);
    flex-shrink: 0;
    transition: background 0.15s;
  }
  .dot.on { background: var(--green); box-shadow: 0 0 5px var(--green); }

  .relay-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
