import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import AlertLifecycle from '../components/AlertLifecycle'

const CREATED = '2026-10-12T09:30:00.000Z'
const RESOLVED = '2026-10-12T11:00:00.000Z'

describe('AlertLifecycle', () => {
  it('renders an ordered, labelled lifecycle for an active alert', () => {
    render(<AlertLifecycle status="active" createdAt={CREATED} resolvedAt={null} />)

    const list = screen.getByLabelText('Alert lifecycle')
    expect(list.tagName).toBe('OL')
    expect(within(list).getByText('Issued')).toBeInTheDocument()
    expect(within(list).getByText('Acknowledged')).toBeInTheDocument()
    expect(within(list).getByText('Resolved')).toBeInTheDocument()

    const issued = within(list).getByText('Issued').closest('li')
    expect(issued).toHaveAttribute('aria-current', 'step')

    // The issued timestamp comes from the API, never invented.
    const time = list.querySelector('time')
    expect(time).not.toBeNull()
    expect(time.getAttribute('datetime')).toBe(CREATED)
  })

  it('marks the acknowledged step and says the timestamp is not recorded', () => {
    render(<AlertLifecycle status="acknowledged" createdAt={CREATED} resolvedAt={null} />)

    const list = screen.getByLabelText('Alert lifecycle')
    const ack = within(list).getByText('Acknowledged').closest('li')
    expect(ack).toHaveAttribute('aria-current', 'step')
    expect(within(list).getByText('time not recorded')).toBeInTheDocument()
    expect(
      screen.getByText(/does not record an acknowledgement timestamp/i),
    ).toBeInTheDocument()
  })

  it('shows the resolved timestamp for a resolved alert', () => {
    render(<AlertLifecycle status="resolved" createdAt={CREATED} resolvedAt={RESOLVED} />)

    const list = screen.getByLabelText('Alert lifecycle')
    const resolved = within(list).getByText('Resolved').closest('li')
    expect(resolved).toHaveAttribute('aria-current', 'step')

    const values = Array.from(list.querySelectorAll('time')).map((t) =>
      t.getAttribute('datetime'),
    )
    expect(values).toContain(CREATED)
    expect(values).toContain(RESOLVED)
  })
})
