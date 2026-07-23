import { expect, mock, test } from 'bun:test'

const redirect = mock(() => {})

mock.module('next/navigation', () => ({ redirect }))

const { default: Home } = await import('./page')

test('redirects the root route to the application home', () => {
  Home()

  expect(redirect).toHaveBeenCalledWith('/app')
})
