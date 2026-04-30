<script>
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  let username = ''
  let password = ''
  let error    = ''
  let loading  = false

  async function submit() {
    if (!username.trim() || !password) return
    loading = true
    error   = ''
    try {
      const res = await fetch('/api/auth/login', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username: username.trim(), password }),
      })
      if (res.ok) {
        dispatch('login', { username: username.trim() })
      } else if (res.status === 429) {
        error = 'Too many attempts — please wait a moment.'
      } else {
        error = 'Invalid username or password.'
        password = ''
      }
    } catch {
      error = 'Connection error. Is the server running?'
    } finally {
      loading = false
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter') submit()
  }
</script>

<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
           stroke-linecap="round" stroke-linejoin="round" width="36" height="36">
        <path d="M18 7a5 5 0 010 10M6 7a5 5 0 000 10M6 12h12"/>
      </svg>
    </div>
    <h1 class="login-title">StationController</h1>
    <p class="login-sub">Sign in to continue</p>

    {#if error}
      <div class="error-banner" role="alert">{error}</div>
    {/if}

    <div class="field">
      <label class="field-label" for="username">Username</label>
      <input
        id="username"
        class="field-input"
        type="text"
        bind:value={username}
        on:keydown={onKeydown}
        autocomplete="username"
        autocapitalize="off"
        spellcheck="false"
        disabled={loading}
        placeholder="admin"
      />
    </div>

    <div class="field">
      <label class="field-label" for="password">Password</label>
      <input
        id="password"
        class="field-input"
        type="password"
        bind:value={password}
        on:keydown={onKeydown}
        autocomplete="current-password"
        disabled={loading}
        placeholder="••••••••"
      />
    </div>

    <button class="login-btn" on:click={submit} disabled={loading || !username.trim() || !password}>
      {loading ? 'Signing in…' : 'Sign in'}
    </button>
  </div>
</div>

<style>
  .login-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    background: var(--bg);
    padding: 1rem;
  }

  .login-card {
    width: 100%;
    max-width: 360px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 2rem 1.75rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.9rem;
  }

  .login-logo {
    color: var(--accent);
    margin-bottom: 0.25rem;
  }

  .login-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text);
  }

  .login-sub {
    margin: 0;
    font-size: 0.82rem;
    color: var(--text-muted);
  }

  .error-banner {
    width: 100%;
    padding: 0.45rem 0.75rem;
    background: rgba(233, 98, 98, 0.1);
    border: 1px solid var(--red);
    border-radius: 5px;
    color: var(--red);
    font-size: 0.82rem;
    text-align: center;
  }

  .field {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .field-label {
    font-size: 0.78rem;
    color: var(--text-muted);
  }

  .field-input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 5px;
    color: var(--text);
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
    box-sizing: border-box;
  }
  .field-input:focus   { border-color: var(--accent); }
  .field-input:disabled { opacity: 0.5; }

  .login-btn {
    width: 100%;
    margin-top: 0.25rem;
    padding: 0.55rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 5px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: filter 0.15s;
  }
  .login-btn:hover:not(:disabled) { filter: brightness(1.1); }
  .login-btn:disabled { opacity: 0.45; cursor: default; }
</style>
