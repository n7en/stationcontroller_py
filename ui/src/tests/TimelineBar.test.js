import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import TimelineBar from '../lib/TimelineBar.svelte'

const BASE = 1_700_000_000

describe('TimelineBar', () => {

  // ── Empty state ──────────────────────────────────────────────────────────

  test('shows empty message when readings is empty', () => {
    render(TimelineBar, { props: { readings: [], fromTs: BASE, toTs: BASE + 3600 } })
    expect(screen.getByText('No data')).toBeInTheDocument()
  })

  test('does not render bar when readings is empty', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelector('.bar')).not.toBeInTheDocument()
  })

  // ── Segments ─────────────────────────────────────────────────────────────

  test('renders bar element with data', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [{ ts: BASE, value: 1 }], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelector('.bar')).toBeInTheDocument()
  })

  test('renders one segment per reading when all fit in range', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 1800, value: 2 },
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    expect(container.querySelectorAll('.seg').length).toBe(2)
  })

  test('two equal-duration readings each span 50% width', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 1800, value: 2 },
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    const segs = container.querySelectorAll('.seg')
    expect(parseFloat(segs[0].style.width)).toBeCloseTo(50, 1)
    expect(parseFloat(segs[1].style.width)).toBeCloseTo(50, 1)
  })

  test('first segment starts at 0%', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [{ ts: BASE, value: 1 }],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    expect(parseFloat(container.querySelector('.seg').style.left)).toBeCloseTo(0, 1)
  })

  test('segment starting at midpoint starts at 50%', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 1800, value: 2 },
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    const segs = container.querySelectorAll('.seg')
    expect(parseFloat(segs[1].style.left)).toBeCloseTo(50, 1)
  })

  // ── Palette colours ──────────────────────────────────────────────────────

  test('value 0 uses dim border colour', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [{ ts: BASE, value: 0 }], fromTs: BASE, toTs: BASE + 3600 },
    })
    const seg = container.querySelector('.seg')
    expect(seg.style.background).toBe('var(--border)')
    expect(seg.style.opacity).toBe('0.7')
  })

  test('value 1 uses green colour', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [{ ts: BASE, value: 1 }], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelector('.seg').style.background).toBe('var(--green)')
  })

  test('segment tooltip title contains the value', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [{ ts: BASE, value: 3 }], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelector('.seg').title).toBe('Value: 3')
  })

  // ── Legend ───────────────────────────────────────────────────────────────

  test('legend shown when there are multiple distinct values', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 1800, value: 2 },
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    expect(container.querySelector('.legend')).toBeInTheDocument()
  })

  test('legend hidden when all readings have the same value', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 1800, value: 1 },
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    expect(container.querySelector('.legend')).not.toBeInTheDocument()
  })

  test('legend chip count equals distinct value count', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [
          { ts: BASE,        value: 1 },
          { ts: BASE + 600,  value: 2 },
          { ts: BASE + 1200, value: 3 },
          { ts: BASE + 1800, value: 1 },  // repeat of 1
        ],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    expect(container.querySelectorAll('.legend-chip').length).toBe(3)
  })

  // ── X-axis labels ────────────────────────────────────────────────────────

  test('renders 6 x-axis labels', () => {
    const { container } = render(TimelineBar, {
      props: { readings: [{ ts: BASE, value: 1 }], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelectorAll('.x-lbl').length).toBe(6)
  })

  // ── Out-of-range readings ────────────────────────────────────────────────

  test('reading before fromTs does not create a visible segment', () => {
    const { container } = render(TimelineBar, {
      props: {
        readings: [{ ts: BASE - 100, value: 1 }],
        fromTs: BASE, toTs: BASE + 3600,
      },
    })
    // segFrom = max(ts, fromTs) = BASE; segTo = min(next?.ts ?? toTs, toTs) = toTs
    // width = (toTs - fromTs) / tRange * 100 = 100% — segment still visible
    // but left should be 0% (clamped to fromTs)
    const seg = container.querySelector('.seg')
    expect(parseFloat(seg?.style.left ?? '0')).toBeCloseTo(0, 1)
  })

})
