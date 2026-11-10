import { act, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App'
import { mockHealth } from './test/transport'

it('shows checking, then online for the health contract', async () => {
  let complete!: (response: Response) => void
  mockHealth(() => new Promise((resolve) => { complete = resolve }))
  render(<App />)
  expect(screen.getByRole('heading', { name: 'NeuroFold' })).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Checking service status')
  await act(async () => { complete(Response.json({ status: 'ok' })) })
  expect(screen.getByRole('status')).toHaveTextContent('Service is online.')
})

it.each([
  ['HTTP failure', () => Promise.resolve(new Response('', { status: 503 }))],
  ['network failure', () => Promise.reject(new TypeError('Synthetic disconnect'))],
  ['malformed JSON', () => Promise.resolve(new Response('{'))],
  ['null payload', () => Promise.resolve(Response.json(null))],
  ['wrong status', () => Promise.resolve(Response.json({ status: 'ready' }))],
  ['missing status', () => Promise.resolve(Response.json({}))],
])('shows unavailable for %s', async (_name, respond) => {
  mockHealth(respond)
  render(<App />)
  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('Service is unavailable.')
  })
})

it('shows unavailable after the five-second timeout', async () => {
  vi.useFakeTimers()
  // jsdom/Node native AbortSignal timers are outside Vitest fake timers.
  vi.spyOn(AbortSignal, 'timeout').mockImplementation((milliseconds) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), milliseconds)
    return controller.signal
  })
  mockHealth((signal) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  }))
  render(<App />)
  await act(async () => { await vi.advanceTimersByTimeAsync(4999) })
  expect(screen.getByRole('status')).toHaveTextContent('Checking service status')
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(screen.getByRole('status')).toHaveTextContent('Service is unavailable.')
})

it('aborts the pending request on unmount', () => {
  let signal: AbortSignal | undefined
  mockHealth((requestSignal) => {
    signal = requestSignal
    return new Promise(() => {})
  })
  const { unmount } = render(<App />)
  expect(signal?.aborted).toBe(false)
  unmount()
  expect(signal?.aborted).toBe(true)
})
