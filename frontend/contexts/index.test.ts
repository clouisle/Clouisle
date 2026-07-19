import { expect, mock, test } from 'bun:test'

const SiteSettingsProvider = () => null
const useSiteSettings = () => ({ theme: 'system' })
const TeamProvider = () => null
const useTeam = () => ({ id: 'team-1' })

mock.module('./site-settings-context', () => ({ SiteSettingsProvider, useSiteSettings }))
mock.module('./team-context', () => ({ TeamProvider, useTeam }))

const contexts = await import('./index')

test('exposes the site-settings and team context public APIs', () => {
  expect(contexts.SiteSettingsProvider).toBe(SiteSettingsProvider)
  expect(contexts.useSiteSettings()).toEqual({ theme: 'system' })
  expect(contexts.TeamProvider).toBe(TeamProvider)
  expect(contexts.useTeam()).toEqual({ id: 'team-1' })
})
