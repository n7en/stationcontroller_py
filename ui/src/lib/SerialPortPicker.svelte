<script>
  /** Current port value, e.g. "COM3" or "/dev/ttyACM0" */
  export let value = ''
  /** Detected ports from /api/radio/serial-ports */
  export let ports = []
  /** Port strings already assigned to other configs — pushed to the bottom of the list */
  export let usedPorts = []
  export let placeholder = 'COM3  or  /dev/ttyUSB0'

  const CUSTOM = '\x00'

  $: inList = ports.some(p => p.port === value)
  $: showInput = ports.length === 0 || (!inList && (value !== '' || customMode))

  $: freePorts = ports.filter(p => !usedPorts.includes(p.port))
  $: takenPorts = ports.filter(p =>  usedPorts.includes(p.port))

  let customMode = false

  function onSelect(e) {
    const v = e.currentTarget.value
    if (v === CUSTOM) {
      customMode = true
    } else {
      customMode = false
      value = v
    }
  }

  $: if (inList) customMode = false

  function portLabel(p) {
    return p.description && p.description !== p.port
      ? `${p.port} — ${p.description}`
      : p.port
  }
</script>

{#if ports.length > 0}
  <select value={inList ? value : CUSTOM} on:change={onSelect}>
    {#each freePorts as p}
      <option value={p.port}>{portLabel(p)}</option>
    {/each}
    {#if takenPorts.length > 0}
      <optgroup label="Already in use">
        {#each takenPorts as p}
          <option value={p.port}>{portLabel(p)}</option>
        {/each}
      </optgroup>
    {/if}
    <option value={CUSTOM}>Type manually…</option>
  </select>
{/if}

{#if showInput}
  <input bind:value
         class:stacked={ports.length > 0}
         {placeholder} />
{/if}

<style>
  select, input {
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    font-size: 0.85rem;
    width: 100%;
    box-sizing: border-box;
  }
  select:focus, input:focus { outline: none; border-color: var(--accent); }
  .stacked { margin-top: 0.3rem; }
</style>
