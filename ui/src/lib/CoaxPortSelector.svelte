<script>
  /**
   * CX-1 4-port coax switch widget.
   * Displays 4 port buttons; clicking one sends CX,<port> via WebSocket relay_cmd.
   */
  import { sendCmd } from '../stores/ws.js'

  export let deviceName = 'coax'   // matches the name used in SensorRegistry keys
  export let deviceAddr = '02'
  export let bus        = ''        // explicit DCN bus name; empty = auto-detect
  export let labelsMap = {}         // hardware_key → friendly label (full registry)
  export let sensorsMap = {}        // hardware_key → {value, ...}

  const N = 4

  // active_port sensor stores -1 (none) or 0..3 (0-based port index)
  $: activePort = (() => {
    const ap = sensorsMap[`${deviceName}_active_port`]
    return ap != null ? Math.round(ap.value) : -1
  })()

  function portLabel(i) {
    return labelsMap[`${deviceName}_port_${i}`] || `Port ${i + 1}`
  }

  function select(port) {
    const cmd = { type: 'coax_select', device_addr: deviceAddr, port }
    if (bus) cmd.bus = bus
    sendCmd(cmd)
  }
</script>

<div class="coax-switch">
  <div class="device-title">
    {labelsMap[`${deviceName}_active_port`] ? '' : ''}{deviceName.toUpperCase()} Coax Switch
    {#if activePort >= 0}
      <span class="active-badge">Port {activePort + 1} active</span>
    {/if}
  </div>
  <div class="port-grid">
    {#each Array.from({length: N}, (_, i) => i) as port}
      <button
        class="port-btn"
        class:active={activePort === port}
        on:click={() => select(port)}
      >
        {portLabel(port)}
      </button>
    {/each}
  </div>
</div>

<style>
  .coax-switch {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }
  .device-title {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .active-badge {
    background: var(--accent-dim);
    color: var(--accent);
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
    font-size: 0.7rem;
  }
  .port-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.4rem;
  }
  .port-btn {
    padding: 0.5rem 0.25rem;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 0.8rem;
    text-align: center;
    transition: border-color 0.15s, background 0.15s;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .port-btn.active { border-color: var(--accent); background: var(--accent-dim); font-weight: 700; }
  .port-btn:hover:not(.active) { border-color: var(--accent); }
</style>
