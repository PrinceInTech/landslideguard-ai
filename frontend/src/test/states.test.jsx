import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Loading, ErrorState, EmptyState, PageState } from '../components/States'

describe('shared page states', () => {
  it('Loading shows the default and a custom label', () => {
    const { rerender } = render(<Loading />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()

    rerender(<Loading label="Fetching locations…" />)
    expect(screen.getByText('Fetching locations…')).toBeInTheDocument()
  })

  it('ErrorState shows the message and calls onRetry when clicked', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Network down" onRetry={onRetry} />)

    expect(screen.getByText('Unable to load data')).toBeInTheDocument()
    expect(screen.getByText('Network down')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('EmptyState shows the default and a custom message', () => {
    const { rerender } = render(<EmptyState />)
    expect(screen.getByText('No data available')).toBeInTheDocument()

    rerender(<EmptyState message="No alerts in this window" />)
    expect(screen.getByText('No alerts in this window')).toBeInTheDocument()
  })

  it('PageState renders loading, then error, then children', () => {
    const { rerender } = render(<PageState loading>content</PageState>)
    expect(screen.getByText('Loading…')).toBeInTheDocument()

    rerender(<PageState error="boom" onRetry={() => {}}>content</PageState>)
    expect(screen.getByText('boom')).toBeInTheDocument()

    rerender(<PageState>content</PageState>)
    expect(screen.getByText('content')).toBeInTheDocument()
  })
})
