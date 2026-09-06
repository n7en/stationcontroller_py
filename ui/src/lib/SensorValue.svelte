<script>
  import { formatUnit } from './utils.js'

  export let name        // hardware key
  export let value = 0
  export let unit  = ''
  export let label = ''  // friendly name (falls back to name)

  $: display   = label || name
  $: dispUnit  = formatUnit(unit)
  $: formatted = dispUnit ? `${(+value).toFixed(2)} ${dispUnit}` : (+value).toFixed(2)
</script>

<div class="sensor">
  <span class="sensor-label">{display}</span>
  <span class="sensor-value">{formatted}</span>
</div>

<style>
  .sensor {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.35rem 0.6rem;
    border-radius: 4px;
    background: var(--surface);
  }
  .sensor-label { color: var(--text-muted); font-size: 0.8rem; }
  .sensor-value { font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
