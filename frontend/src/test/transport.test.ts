import { expect, it } from 'vitest'
import dns from 'node:dns'
import net from 'node:net'
import { mockHealth } from './transport'

it('blocks unmocked browser transports', () => {
  expect(() => fetch('https://example.invalid')).toThrow('Network is disabled')
  expect(() => new XMLHttpRequest()).toThrow('Network is disabled')
  expect(() => new WebSocket('wss://example.invalid')).toThrow('Network is disabled')
  expect(() => new EventSource('https://example.invalid')).toThrow('Network is disabled')
  expect(() => navigator.sendBeacon('https://example.invalid')).toThrow('Network is disabled')
})

it('rejects unmatched requests even when health is mocked', async () => {
  mockHealth(async () => Response.json({ status: 'ok' }))
  await expect(fetch('https://example.invalid')).rejects.toThrow('Network is disabled')
})

it('blocks Node connections and DNS in component tests', () => {
  const socket = new net.Socket()
  expect(() => socket.connect(9, '127.0.0.1')).toThrow('Network is disabled')
  socket.destroy()
  expect(() => dns.lookup('example.invalid', () => {})).toThrow('Network is disabled')
})
