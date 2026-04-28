<script>
  import { sensors, labels, sendCmd } from '../stores/ws.js'
  import CoaxPortSelector from './CoaxPortSelector.svelte'
  import RelayButton      from './RelayButton.svelte'
  import PowerMeterGauge  from './PowerMeterGauge.svelte'
  import SwrBar           from './SwrBar.svelte'

  export let device

  const TYPE_LABELS = {
    gpio:           'GPIO Module (#321)',
    coax_switch:    'HF Coax Switch (#331)',
    watt_meter:     'RF Watt Meter (#335)',
    vhf_relay:      'VHF Coax Relay (#332)',
    antenna_relay:  'Antenna Relay (#361)',
  }

  $: cardTitle = $labels[device.name] ?? device.name
  $: cardType  = device.type === 'antenna_relay'
      ? (device.persona_label ?? TYPE_LABELS[device.type])
      : (TYPE_LABELS[device.type] ?? device.type)

  $: relaySensors  = (device.sensors ?? []).filter(s => s.role === 'relay')
  $: fwdKey        = (device.sensors ?? []).find(s => s.role === 'forward_power')?.key
  $: refKey        = (device.sensors ?? []).find(s => s.role === 'reflected_power')?.key
  $: swrKey        = (device.sensors ?? []).find(s => s.role === 'swr')?.key
  $: voltSensors   = (device.sensors ?? []).filter(s => s.role === 'voltmeter')
  $: tempSensors   = (device.sensors ?? []).filter(s => s.role === 'temperature')
  $: inputSensors  = (device.sensors ?? []).filter(s => s.role === 'digital_input')

  // one_hot mode: active position derived from relay states
  $: activePosition = (() => {
    if (device.mode !== 'one_hot') return null
    const on = relaySensors.findIndex(s => ($sensors[s.key]?.value ?? 0) >= 0.5)
    return on >= 0 ? on + 1 : 0
  })()

  function selectPosition(pos) {
    sendCmd({ type: 'pos_select', device_addr: device.address, position: pos })
  }

  function posLabel(s) {
    return $labels[s.key] || `Position ${s.relay_num}`
  }
</script>

<div class="device-card">
  <div class="card-header">
    <span class="card-name">{cardTitle}</span>
    <span class="card-type">{cardType}</span>
    <span class="card-addr">addr {device.address}</span>
  </div>

  <div class="card-body">

    {#if device.type === 'coax_switch'}
      <CoaxPortSelector
        deviceName={device.name}
        deviceAddr={device.address}
        labelsMap={$labels}
        sensorsMap={$sensors}
      />

    {:else if device.type === 'watt_meter'}
      <div class="power-grid">
        {#if fwdKey}
          <PowerMeterGauge
            value={$sensors[fwdKey]?.value ?? 0}
            max={1500} color="var(--accent)"
            title={$labels[fwdKey] || 'Forward Power'}
          />
        {/if}
        {#if refKey}
          <PowerMeterGauge
            value={$sensors[refKey]?.value ?? 0}
            max={1500} color="var(--red)"
            title={$labels[refKey] || 'Reflected Power'}
          />
        {/if}
        {#if swrKey}
          <SwrBar
            value={$sensors[swrKey]?.value ?? 0}
            title={$labels[swrKey] || 'SWR'}
            thresholds={{ good: 1.5, warning: 2.0, critical: 3.0 }}
          />
        {/if}
      </div>

    {:else if device.type === 'gpio'}
      {#if relaySensors.length}
        <div class="block-label">Relays</div>
        <div class="relay-grid">
          {#each relaySensors as s (s.key)}
            <RelayButton
              hardwareKey={s.key}
              label={$labels[s.key] ?? ''}
              value={$sensors[s.key]?.value ?? 0}
              deviceAddr={device.address}
              relayNum={s.relay_num}
            />
          {/each}
        </div>
      {/if}
      {#if inputSensors.length || voltSensors.length || tempSensors.length}
        <div class="sensor-rows">
          {#each inputSensors as s (s.key)}
            <div class="sensor-row">
              <span class="sr-label">{$labels[s.key] || `Input ${s.input_num}`}</span>
              <span class="sr-value" class:sr-high={($sensors[s.key]?.value ?? 0) >= 0.5}>
                {($sensors[s.key]?.value ?? 0) >= 0.5 ? 'HIGH' : 'LOW'}
              </span>
            </div>
          {/each}
          {#each voltSensors as s (s.key)}
            <div class="sensor-row">
              <span class="sr-label">{$labels[s.key] || `Voltmeter ${s.voltmeter_num}`}</span>
              <span class="sr-value">{($sensors[s.key]?.value ?? 0).toFixed(2)} V</span>
            </div>
          {/each}
          {#each tempSensors as s (s.key)}
            <div class="sensor-row">
              <span class="sr-label">{$labels[s.key] || `Temp ${s.probe_num}`}</span>
              <span class="sr-value">{($sensors[s.key]?.value ?? 0).toFixed(1)} degF</span>
            </div>
          {/each}
        </div>
      {/if}

    {:else if device.type === 'antenna_relay' && device.mode === 'one_hot'}
      <div class="pos-grid">
        {#each relaySensors as s (s.key)}
          <button
            class="pos-btn"
            class:active={activePosition === s.relay_num}
            on:click={() => selectPosition(s.relay_num)}
          >
            {posLabel(s)}
          </button>
        {/each}
      </div>

    {:else if device.type === 'antenna_relay' || device.type === 'vhf_relay'}
      <div class="relay-grid">
        {#each relaySensors as s (s.key)}
          <RelayButton
            hardwareKey={s.key}
            label={$labels[s.key] ?? ''}
            value={$sensors[s.key]?.value ?? 0}
            deviceAddr={device.address}
            relayNum={s.relay_num}
          />
        {/each}
      </div>

    {/if}

  </div>
</div>

<style>
  .device-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.85rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .card-name {
    font-weight: 600;
    font-size: 0.88rem;
  }
  .card-type {
    flex: 1;
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .card-addr {
    font-family: monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
  }

  .card-body {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .block-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .relay-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.4rem;
  }

  .pos-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 0.4rem;
  }
  .pos-btn {
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
  .pos-btn.active {
    border-color: var(--accent);
    background: var(--accent-dim);
    font-weight: 700;
    color: var(--accent);
  }
  .pos-btn:hover:not(.active) { border-color: var(--accent); }

  .power-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 0.5rem;
  }

  .sensor-rows {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .sensor-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.82rem;
    padding: 0.15rem 0;
  }
  .sr-label { color: var(--text-muted); }
  .sr-value { font-family: monospace; }
  .sr-high  { color: var(--accent); }
</style>
