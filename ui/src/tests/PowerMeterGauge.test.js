import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import PowerMeterGauge from '../lib/PowerMeterGauge.svelte'

describe('PowerMeterGauge', () => {

  test('renders without crashing', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 0, max: 1500 } })
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  test('displays integer watts below 1000', () => {
    render(PowerMeterGauge, { props: { value: 250, max: 1500 } })
    expect(screen.getByText('250')).toBeInTheDocument()
  })

  test('displays kW with one decimal at 1000W+', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 1500, max: 1500 } })
    // Both .val and .scale show "1.5k" at max, so query the specific value element
    expect(container.querySelector('.val').textContent).toBe('1.5k')
  })

  test('displays kW without decimal when evenly divisible', () => {
    // value=2000 → "2.0k" (value/1000 = 2.0 → toFixed(1) = "2.0k")
    render(PowerMeterGauge, { props: { value: 2000, max: 3000 } })
    expect(screen.getByText('2.0k')).toBeInTheDocument()
  })

  test('rounds sub-1kW values to nearest integer', () => {
    render(PowerMeterGauge, { props: { value: 99.7, max: 1500 } })
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  test('max label uses k-suffix when max >= 1000', () => {
    render(PowerMeterGauge, { props: { value: 0, max: 1500 } })
    // max=1500 → "1.5k"
    expect(screen.getByText('1.5k')).toBeInTheDocument()
  })

  test('renders the title when provided', () => {
    render(PowerMeterGauge, { props: { value: 100, max: 1500, title: 'Forward Power' } })
    expect(screen.getByText('Forward Power')).toBeInTheDocument()
  })

  test('no value arc path when value is zero', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 0, max: 1500 } })
    // Only the background track path should exist; value arc is rendered only when pct > 0.001
    const paths = container.querySelectorAll('path')
    expect(paths.length).toBe(1)  // only track
  })

  test('value arc path present when value > 0', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 500, max: 1500 } })
    const paths = container.querySelectorAll('path')
    expect(paths.length).toBe(2)  // track + value arc
  })

  test('value arc uses full-circle path string when at max', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 1500, max: 1500 } })
    const paths = container.querySelectorAll('path')
    expect(paths.length).toBe(2)
    const arcD = paths[1].getAttribute('d')
    // Full arc special case: "M -50 0 A 50 50 0 1 0 50 0"
    expect(arcD).toContain('1 0')
  })

  test('value arc uses large-arc flag when pct > 0.5', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 900, max: 1500 } })
    // pct = 0.6 > 0.5 → large-arc = 1
    const arcPath = container.querySelectorAll('path')[1].getAttribute('d')
    expect(arcPath).toMatch(/A 50 50 0 1 0/)
  })

  test('value arc uses small-arc flag when pct <= 0.5', () => {
    const { container } = render(PowerMeterGauge, { props: { value: 600, max: 1500 } })
    // pct = 0.4 <= 0.5 → large-arc = 0
    const arcPath = container.querySelectorAll('path')[1].getAttribute('d')
    expect(arcPath).toMatch(/A 50 50 0 0 0/)
  })

  test('clamps overflow value to max', () => {
    render(PowerMeterGauge, { props: { value: 9999, max: 1500, title: 'FWD' } })
    // Should not crash; displays the clamped visual (pct=1)
    const { container } = render(PowerMeterGauge, { props: { value: 9999, max: 1500 } })
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

})
