import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// The page must never touch a real backend; mock the API module the same way
// the other page tests do.
vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  setToken: vi.fn(),
}))

import api, { setToken } from '../services/api'
import Login from '../pages/Login'

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )
}

describe('Login (demo hygiene)', () => {
  beforeEach(() => {
    api.post.mockReset()
    setToken.mockReset()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('starts with an empty password field (no prefilled demo password)', () => {
    const { container } = renderLogin()
    const password = container.querySelector('input[type="password"]')
    expect(password).not.toBeNull()
    expect(password.value).toBe('')
  })

  it('shows the demo-credential hint in development mode', () => {
    renderLogin()
    expect(screen.getByText(/Demo: admin@landslideguard\.ai/i)).toBeInTheDocument()
  })

  it('hides the demo-credential hint when development mode is false', () => {
    vi.stubEnv('DEV', false)
    renderLogin()
    expect(screen.queryByText(/Demo: admin@landslideguard\.ai/i)).toBeNull()
  })

  it('submits the user-entered email and password through the existing request path', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 'jwt-token', user: { name: 'Demo', role: 'viewer' } },
    })
    const { container } = renderLogin()

    fireEvent.change(container.querySelector('input[type="email"]'), {
      target: { value: 'viewer@example.com' },
    })
    fireEvent.change(container.querySelector('input[type="password"]'), {
      target: { value: 'my-secret-pw' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/auth/login', {
        email: 'viewer@example.com',
        password: 'my-secret-pw',
      }),
    )
    expect(setToken).toHaveBeenCalledWith('jwt-token')
  })

  it('keeps the router login heading intact', () => {
    renderLogin()
    expect(screen.getByText('Sign in to the monitoring platform')).toBeInTheDocument()
  })

  it('navigates to /dashboard and establishes the session on a successful login', async () => {
    api.post.mockResolvedValue({
      data: { access_token: 'jwt-token', user: { name: 'Demo', role: 'viewer' } },
    })
    const { container } = render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<div>Dashboard route</div>} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.change(container.querySelector('input[type="email"]'), {
      target: { value: 'viewer@example.com' },
    })
    fireEvent.change(container.querySelector('input[type="password"]'), {
      target: { value: 'my-secret-pw' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    // Actual resulting location: the /dashboard route renders after navigate().
    expect(await screen.findByText('Dashboard route')).toBeInTheDocument()
    expect(setToken).toHaveBeenCalledWith('jwt-token')

    // setSession(token, user) is not mocked; assert its observable effects.
    // Login calls setSession(res.data.access_token, res.data.user) -> writes
    // lg_token / lg_user into storage (see useAuth.js).
    expect(localStorage.getItem('lg_token')).toBe('jwt-token')
    expect(JSON.parse(localStorage.getItem('lg_user'))).toEqual({
      name: 'Demo',
      role: 'viewer',
    })
  })
})
