import { describe, test, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/svelte'
import LogView from '../lib/LogView.svelte'
import { logEntries, dcnEntries } from '../stores/ws.js'

const LOGS = [
  { ts: 1000, level: 'INFO',     logger: 'main',    msg: 'Server started' },
  { ts: 1001, level: 'WARNING',  logger: 'comms',   msg: 'Timeout on bus' },
  { ts: 1002, level: 'ERROR',    logger: 'radio',   msg: 'Connect failed' },
  { ts: 1003, level: 'CRITICAL', logger: 'app',     msg: 'Fatal error'    },
  { ts: 1004, level: 'DEBUG',    logger: 'sensors', msg: 'Tick'           },
]

const DCN = [
  { ts: 2000, direction: 'rx', bus: 'control', from_addr: '01', to_addr: 'FF', payload: 'STATUS,1' },
  { ts: 2001, direction: 'tx', bus: 'control', from_addr: '00', to_addr: '01', payload: 'RY0,1'    },
]

describe('LogView', () => {

  beforeEach(() => {
    logEntries.set([])
    dcnEntries.set([])
  })

  // ── Tabs ─────────────────────────────────────────────────────────────────

  test('renders both General and DCN tabs', () => {
    render(LogView)
    expect(screen.getByText(/General/)).toBeInTheDocument()
    expect(screen.getByText(/DCN/)).toBeInTheDocument()
  })

  test('General tab is active by default', () => {
    const { container } = render(LogView)
    const tabs = container.querySelectorAll('.tab')
    expect(tabs[0]).toHaveClass('active')
    expect(tabs[1]).not.toHaveClass('active')
  })

  test('clicking DCN tab makes it active', async () => {
    const { container } = render(LogView)
    const tabs = container.querySelectorAll('.tab')
    await fireEvent.click(tabs[1])
    expect(tabs[1]).toHaveClass('active')
    expect(tabs[0]).not.toHaveClass('active')
  })

  // ── Empty states ─────────────────────────────────────────────────────────

  test('shows empty message when no log entries', () => {
    render(LogView)
    expect(screen.getByText('No log entries yet.')).toBeInTheDocument()
  })

  test('shows DCN empty message after switching to DCN tab', async () => {
    const { container } = render(LogView)
    await fireEvent.click(container.querySelectorAll('.tab')[1])
    expect(screen.getByText('No DCN messages yet.')).toBeInTheDocument()
  })

  // ── Log entries ──────────────────────────────────────────────────────────

  test('renders log message text', () => {
    logEntries.set(LOGS)
    render(LogView)
    expect(screen.getByText('Server started')).toBeInTheDocument()
    expect(screen.getByText('Timeout on bus')).toBeInTheDocument()
  })

  test('renders logger name', () => {
    logEntries.set([LOGS[0]])
    render(LogView)
    expect(screen.getByText('main')).toBeInTheDocument()
  })

  test('renders level text', () => {
    logEntries.set([LOGS[1]])
    render(LogView)
    expect(screen.getByText('WARNING')).toBeInTheDocument()
  })

  test('badge shows count of visible entries', () => {
    logEntries.set(LOGS)
    const { container } = render(LogView)
    const badge = container.querySelector('.tab.active .badge')
    expect(badge.textContent).toBe(String(LOGS.length))
  })

  // ── Level CSS classes ────────────────────────────────────────────────────

  test('WARNING row has warn class', () => {
    logEntries.set([{ ts: 1000, level: 'WARNING', logger: 'x', msg: 'm' }])
    const { container } = render(LogView)
    expect(container.querySelector('.row.warn')).toBeInTheDocument()
  })

  test('ERROR row has err class', () => {
    logEntries.set([{ ts: 1000, level: 'ERROR', logger: 'x', msg: 'm' }])
    const { container } = render(LogView)
    expect(container.querySelector('.row.err')).toBeInTheDocument()
  })

  test('CRITICAL row has err class', () => {
    logEntries.set([{ ts: 1000, level: 'CRITICAL', logger: 'x', msg: 'm' }])
    const { container } = render(LogView)
    expect(container.querySelector('.row.err')).toBeInTheDocument()
  })

  test('DEBUG row has debug class', () => {
    logEntries.set([{ ts: 1000, level: 'DEBUG', logger: 'x', msg: 'm' }])
    const { container } = render(LogView)
    expect(container.querySelector('.row.debug')).toBeInTheDocument()
  })

  test('INFO row has no warn/err/debug class', () => {
    logEntries.set([{ ts: 1000, level: 'INFO', logger: 'x', msg: 'm' }])
    const { container } = render(LogView)
    const row = container.querySelector('.row')
    expect(row).not.toHaveClass('warn')
    expect(row).not.toHaveClass('err')
    expect(row).not.toHaveClass('debug')
  })

  test('entry with exc field renders exception text', () => {
    logEntries.set([{ ts: 1000, level: 'ERROR', logger: 'x', msg: 'boom', exc: 'Traceback (most recent call last)…' }])
    render(LogView)
    expect(screen.getByText('Traceback (most recent call last)…')).toBeInTheDocument()
  })

  // ── DCN entries ──────────────────────────────────────────────────────────

  test('DCN tab shows rx and tx payloads', async () => {
    dcnEntries.set(DCN)
    const { container } = render(LogView)
    await fireEvent.click(container.querySelectorAll('.tab')[1])
    expect(screen.getByText('STATUS,1')).toBeInTheDocument()
    expect(screen.getByText('RY0,1')).toBeInTheDocument()
  })

  test('RX entries have dcn-rx class', async () => {
    dcnEntries.set([DCN[0]])
    const { container } = render(LogView)
    await fireEvent.click(container.querySelectorAll('.tab')[1])
    expect(container.querySelector('.row.dcn-rx')).toBeInTheDocument()
  })

  test('TX entries have dcn-tx class', async () => {
    dcnEntries.set([DCN[1]])
    const { container } = render(LogView)
    await fireEvent.click(container.querySelectorAll('.tab')[1])
    expect(container.querySelector('.row.dcn-tx')).toBeInTheDocument()
  })

  test('direction text is uppercase', async () => {
    dcnEntries.set([DCN[0]])
    const { container } = render(LogView)
    await fireEvent.click(container.querySelectorAll('.tab')[1])
    expect(container.querySelector('.dir').textContent).toBe('RX')
  })

  // ── Pause / Resume ───────────────────────────────────────────────────────

  test('Pause button toggles label to Resume', async () => {
    render(LogView)
    await fireEvent.click(screen.getByText('Pause'))
    expect(screen.getByText('Resume')).toBeInTheDocument()
    expect(screen.queryByText('Pause')).not.toBeInTheDocument()
  })

  test('paused button gets paused CSS class', async () => {
    render(LogView)
    const btn = screen.getByText('Pause')
    await fireEvent.click(btn)
    expect(screen.getByText('Resume')).toHaveClass('paused')
  })

  test('clicking Resume restores Pause label', async () => {
    render(LogView)
    await fireEvent.click(screen.getByText('Pause'))
    await fireEvent.click(screen.getByText('Resume'))
    expect(screen.getByText('Pause')).toBeInTheDocument()
  })

  // ── Clear ────────────────────────────────────────────────────────────────

  test('Clear hides pre-existing log entries', async () => {
    logEntries.set(LOGS)
    render(LogView)
    expect(screen.getByText('Server started')).toBeInTheDocument()
    await fireEvent.click(screen.getByText('Clear'))
    expect(screen.queryByText('Server started')).not.toBeInTheDocument()
  })

  test('Clear on DCN tab hides DCN entries without affecting general tab', async () => {
    logEntries.set(LOGS)
    dcnEntries.set(DCN)
    const { container } = render(LogView)
    const tabs = container.querySelectorAll('.tab')
    await fireEvent.click(tabs[1])    // switch to DCN
    await fireEvent.click(screen.getByText('Clear'))
    expect(screen.queryByText('STATUS,1')).not.toBeInTheDocument()
    // General entries should still be there after switching back
    await fireEvent.click(tabs[0])
    expect(screen.getByText('Server started')).toBeInTheDocument()
  })

})
