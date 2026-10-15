import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App routing', () => {
  it('renders the landing page as the initial view at "/"', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      /AI-Powered Landslide/i,
    )
    expect(
      screen.getByRole('heading', { level: 2, name: /Landslides threaten communities across Northeast India/i }),
    ).toBeInTheDocument()
  })

  it('renders the landing page for an unknown route (catch-all)', () => {
    renderAt('/route-that-does-not-exist')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      /AI-Powered Landslide/i,
    )
  })

  it('redirects an unauthenticated visitor from a protected route to login', async () => {
    renderAt('/dashboard')
    expect(
      await screen.findByText(/Sign in to the monitoring platform/i),
    ).toBeInTheDocument()
  })
})
