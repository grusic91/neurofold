import { vi } from 'vitest'

export function denyNetwork(): never {
  throw new Error('Network is disabled in component tests; use an explicit fake.')
}

// Tests explicitly replace fetch per case; every unmatched URL still fails.
export function mockHealth(
  respond: (signal: AbortSignal) => Promise<Response>,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (input !== '/api/health' || !(init?.signal instanceof AbortSignal)) {
      return denyNetwork()
    }
    return respond(init.signal)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
