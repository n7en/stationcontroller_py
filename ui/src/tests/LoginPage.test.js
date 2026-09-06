import { describe, test, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte'
import LoginPage from '../lib/LoginPage.svelte'

/** @param {string} username @param {string} password */
async function fillForm(username, password) {
  await fireEvent.input(screen.getByLabelText('Username'), { target: { value: username } })
  await fireEvent.input(screen.getByLabelText('Password'), { target: { value: password } })
}

describe('LoginPage', () => {

  afterEach(() => { vi.restoreAllMocks() })

  // ── Rendering ────────────────────────────────────────────────────────────

  test('renders title and sign-in button', () => {
    render(LoginPage)
    expect(screen.getByText('StationController')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  test('renders username and password fields', () => {
    render(LoginPage)
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  test('no error banner on initial render', () => {
    render(LoginPage)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  // ── Button disabled state ────────────────────────────────────────────────

  test('sign-in button disabled when both fields empty', () => {
    render(LoginPage)
    expect(screen.getByRole('button', { name: /sign in/i })).toBeDisabled()
  })

  test('sign-in button disabled when only username filled', async () => {
    render(LoginPage)
    await fireEvent.input(screen.getByLabelText('Username'), { target: { value: 'admin' } })
    expect(screen.getByRole('button', { name: /sign in/i })).toBeDisabled()
  })

  test('sign-in button disabled when only password filled', async () => {
    render(LoginPage)
    await fireEvent.input(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    expect(screen.getByRole('button', { name: /sign in/i })).toBeDisabled()
  })

  test('sign-in button enabled when both fields filled', async () => {
    render(LoginPage)
    await fillForm('admin', 'correct-horse')
    expect(screen.getByRole('button', { name: /sign in/i })).not.toBeDisabled()
  })

  test('sign-in button disabled when username is only whitespace', async () => {
    render(LoginPage)
    await fillForm('   ', 'password')
    expect(screen.getByRole('button', { name: /sign in/i })).toBeDisabled()
  })

  // ── Successful login ─────────────────────────────────────────────────────

  test('calls POST /api/auth/login with trimmed credentials', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
    render(LoginPage)
    await fillForm('  admin  ', 'correct-horse')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
        method: 'POST',
        body:   JSON.stringify({ username: 'admin', password: 'correct-horse' }),
      }))
    })
  })

  test('calls onlogin callback with trimmed username on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
    const onlogin = vi.fn()
    render(LoginPage, { props: { onlogin } })
    await fillForm('admin', 'correct-horse')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(onlogin).toHaveBeenCalledWith({ username: 'admin' }))
  })

  // ── Failed login ─────────────────────────────────────────────────────────

  test('shows invalid credentials error on 401', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    render(LoginPage)
    await fillForm('admin', 'wrong')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid username or password')
    )
  })

  test('clears password field after failed login', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    render(LoginPage)
    await fillForm('admin', 'wrong')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.getByLabelText('Password')).toHaveValue(''))
  })

  test('shows rate-limit message on 429', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 429 })
    render(LoginPage)
    await fillForm('admin', 'pw')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Too many attempts')
    )
  })

  test('shows connection error when fetch rejects', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network'))
    render(LoginPage)
    await fillForm('admin', 'pw')
    await fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Connection error')
    )
  })

  // ── Enter key ────────────────────────────────────────────────────────────

  test('Enter key in username field triggers submit', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    render(LoginPage)
    await fillForm('admin', 'pw')
    await fireEvent.keyDown(screen.getByLabelText('Username'), { key: 'Enter' })
    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce())
  })

  test('Enter key in password field triggers submit', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    render(LoginPage)
    await fillForm('admin', 'pw')
    await fireEvent.keyDown(screen.getByLabelText('Password'), { key: 'Enter' })
    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce())
  })

  test('non-Enter key does not submit form', async () => {
    global.fetch = vi.fn()
    render(LoginPage)
    await fillForm('admin', 'pw')
    await fireEvent.keyDown(screen.getByLabelText('Password'), { key: 'a' })
    expect(global.fetch).not.toHaveBeenCalled()
  })

})
