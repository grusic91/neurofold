import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import dns from 'node:dns'
import net from 'node:net'
import dgram from 'node:dgram'
import { denyNetwork } from './transport'

const originalBeacon = Object.getOwnPropertyDescriptor(navigator, 'sendBeacon')

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(denyNetwork))
  vi.stubGlobal('XMLHttpRequest', class { constructor() { denyNetwork() } })
  vi.stubGlobal('WebSocket', class { constructor() { denyNetwork() } })
  vi.stubGlobal('EventSource', class { constructor() { denyNetwork() } })
  Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: denyNetwork })
  vi.spyOn(net.Socket.prototype, 'connect').mockImplementation(denyNetwork)
  vi.spyOn(dgram.Socket.prototype, 'connect').mockImplementation(denyNetwork)
  vi.spyOn(dgram.Socket.prototype, 'send').mockImplementation(denyNetwork)
  vi.spyOn(dns, 'lookup').mockImplementation(denyNetwork)
  vi.spyOn(dns, 'resolve').mockImplementation(denyNetwork)
  vi.spyOn(dns.promises, 'lookup').mockImplementation(denyNetwork)
  vi.spyOn(dns.promises, 'resolve').mockImplementation(denyNetwork)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  if (originalBeacon) Object.defineProperty(navigator, 'sendBeacon', originalBeacon)
  else Reflect.deleteProperty(navigator, 'sendBeacon')
})
