import { test as base, expect } from '@playwright/test'

export const test = base.extend<{ blockedRequests: string[] }>({
  blockedRequests: [async ({ context, baseURL }, use) => {
    const blocked: string[] = []
    await context.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      const isStatic = url.origin === baseURL && (
        url.pathname === '/' || url.pathname.startsWith('/assets/') ||
        url.pathname === '/favicon.ico'
      )
      if (isStatic && route.request().method() === 'GET') {
        await route.continue()
      } else {
        blocked.push(url.href)
        await route.abort('blockedbyclient')
      }
    })
    await context.routeWebSocket('**/*', (socket) => {
      blocked.push(socket.url())
      socket.close()
    })
    await use(blocked)
    expect(blocked, 'Unmocked requests must not escape browser tests').toEqual([])
  }, { auto: true }],
})

export { expect } from '@playwright/test'
