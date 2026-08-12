import { expect, mock, test } from 'bun:test'

const fetchMock = mock(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({ data: null }) }),
)

globalThis.fetch = fetchMock as typeof fetch
mock.module('@/lib/api/server-url', () => ({
  getServerApiBaseUrl: () => 'https://api.example.test',
  getServerBackendOrigin: () => 'https://backend.example.test',
}))

const { default: ChatLayout, generateMetadata } = await import('./layout')

test('returns chat children without an extra layout wrapper', () => {
  expect(ChatLayout({ children: 'chat content' })).toBe('chat content')
})

test('uses generic metadata when the public agent is unavailable', async () => {
  fetchMock.mockResolvedValueOnce({ ok: false })

  await expect(generateMetadata({ params: Promise.resolve({ id: 'missing' }) })).resolves.toEqual({
    title: 'Chat',
    description: 'AI Chat',
  })
  expect(fetchMock).toHaveBeenCalledWith('https://api.example.test/agents/missing/public', {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  })
})

test('builds agent metadata; favicon stays proxied, openGraph uses backend URLs', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: () =>
      Promise.resolve({
        data: { id: 'agent-1', name: 'Weather', description: '', icon: '/weather.svg' },
      }),
  })

  await expect(generateMetadata({ params: Promise.resolve({ id: 'agent-1' }) })).resolves.toEqual({
    title: 'Weather',
    description: 'Chat with Weather',
    // The browser resolves the favicon against the frontend origin, so the
    // path must stay relative to go through the Next.js API proxy.
    icons: { icon: '/weather.svg' },
    openGraph: {
      title: 'Weather',
      description: 'Chat with Weather',
      images: ['https://backend.example.test/weather.svg'],
    },
  })
})

test('uses the public avatar before the configured icon', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: () =>
      Promise.resolve({
        data: {
          id: 'agent-2',
          name: 'Support',
          description: 'Answers questions',
          avatar_url: '/avatars/support.png',
          icon: '/support.svg',
        },
      }),
  })

  await expect(
    generateMetadata({ params: Promise.resolve({ id: 'agent-2' }) }),
  ).resolves.toMatchObject({
    title: 'Support',
    description: 'Answers questions',
    icons: { icon: '/avatars/support.png' },
    openGraph: { images: ['https://backend.example.test/avatars/support.png'] },
  })
})

test('falls back to generic metadata when the agent request fails', async () => {
  fetchMock.mockRejectedValueOnce(new Error('offline'))

  await expect(generateMetadata({ params: Promise.resolve({ id: 'offline' }) })).resolves.toEqual({
    title: 'Chat',
    description: 'AI Chat',
  })
})
