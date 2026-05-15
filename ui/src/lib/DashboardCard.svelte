<script>
  import PowerMeterGauge from './PowerMeterGauge.svelte'
  import SwrBar          from './SwrBar.svelte'
  import RelayButton     from './RelayButton.svelte'
  import RadioStatus     from './RadioStatus.svelte'

  export let card    // card config object from dashboard YAML
  export let sensors = {}
  export let labels  = {}
  export let radio   = null

  $: val = (key) => sensors[key]?.value ?? 0
  $: lbl = (key) => labels[key] || card.title || key

  $: sensorVal = val(card.sensor)

  $: thresholdColor = (() => {
    const v = sensorVal
    if (card.critical_above !== undefined && v >= card.critical_above) return 'var(--red)'
    if (card.critical_below !== undefined && v <= card.critical_below) return 'var(--red)'
    if (card.warn_above     !== undefined && v >= card.warn_above)     return '#f0a030'
    if (card.warn_below     !== undefined && v <= card.warn_below)     return '#f0a030'
    if (card.warn_above !== undefined || card.warn_below !== undefined) return 'var(--green)'
    return 'var(--text)'
  })()
</script>

{#if card.type === 'power_meter'}
  <PowerMeterGauge
    value={sensorVal}
    max={card.max_w ?? 1500}
    color={card.color ?? 'var(--accent)'}
    title={card.title}
    unit="W"
  />

{:else if card.type === 'swr_bar'}
  <SwrBar
    value={sensorVal}
    title={card.title}
    thresholds={card.thresholds ?? { good: 1.5, warning: 2.0, critical: 3.0 }}
  />

{:else if card.type === 'relay'}
  <RelayButton
    hardwareKey={card.relay_key}
    label={labels[card.relay_key] ?? card.title}
    value={val(card.relay_key)}
    deviceAddr={card.device_addr ?? '01'}
    relayNum={card.relay_num ?? 1}
  />

{:else if card.type === 'sensor'}
  <div class="sensor-card">
    <span class="s-label">{card.title}</span>
    <span class="s-val" style="color:{thresholdColor}">
      {(+sensorVal).toFixed(1)}{card.unit ?? ''}
    </span>
  </div>

{:else if card.type === 'radio_status'}
  <RadioStatus radioState={radio} />

{:else if card.type === 'blank'}
  <div class="blank-card"></div>

{:else}
  <div class="unknown-card">Unknown card type: {card.type}</div>
{/if}

<style>
  .blank-card {
    /* Invisible in view mode — just holds the grid cell open.
       min-height prevents row collapse when an entire row is blanks. */
    min-height: 48px;
  }

  .sensor-card {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
    height: 100%; box-sizing: border-box;
  }
  .s-label { font-size: 0.78rem; color: var(--text-muted); }
  .s-val   { font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .unknown-card {
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border-radius: 6px;
    color: var(--text-muted);
    font-size: 0.75rem;
  }
</style>
