import { useEffect, useState } from 'react'
import Workflow from './Workflow'
import { apiUrl } from './api'

type HealthStatus = 'checking' | 'ok' | 'unavailable'

const healthMessages: Record<HealthStatus, string> = {
  checking: 'Checking service status…',
  ok: 'Service is online.',
  unavailable: 'Service is unavailable. Please try again later.',
}

function App() {
  const [health, setHealth] = useState<HealthStatus>('checking')

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch(apiUrl('/health'), {
          redirect: 'error',
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(5000),
          ]),
        })
        if (!response.ok) throw new Error('Health request failed')

        const payload: unknown = await response.json()
        if (
          typeof payload !== 'object' ||
          payload === null ||
          !('status' in payload) ||
          payload.status !== 'ok'
        ) {
          throw new Error('Unexpected health response')
        }
        if (!controller.signal.aborted) setHealth('ok')
      } catch {
        if (!controller.signal.aborted) setHealth('unavailable')
      }
    }

    void checkHealth()
    return () => controller.abort()
  }, [])

  return (
    <main>
      <p className="eyebrow">Open computational biology</p>
      <h1>NeuroFold</h1>
      <p>
        Protein structure prediction and neurodegenerative disease research,
        built for open and reproducible science.
      </p>
      <section aria-labelledby="status-heading">
        <h2 id="status-heading">Platform status</h2>
        <p role="status">{healthMessages[health]}</p>
        <p>Prediction and molecular visualization are planned for future releases.</p>
      </section>
      <Workflow />
      <a href="https://github.com/grusic91/neurofold">View the project on GitHub</a>
    </main>
  )
}

export default App
