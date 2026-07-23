import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { adminSkillsApi } from './skills'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let patch: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>
let spies: Array<ReturnType<typeof spyOn>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  patch = spyOn(api, 'patch').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
  spies = [get, post, patch, remove]
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
})

describe('adminSkillsApi', () => {
  test('serializes default and filtered list requests', async () => {
    await adminSkillsApi.list()
    await adminSkillsApi.list({
      page: 2,
      pageSize: 50,
      search: 'git & zip',
      team_id: ['team-1', 'team-2'],
      include_system: false,
      enabled: false,
      status: ['enabled', 'disabled'],
      source_type: ['git', 'zip'],
      creator: ['user-1', 'user-2'],
    })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/skills?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/admin/skills?page=2&page_size=50&search=git+%26+zip&team_id=team-1&team_id=team-2&include_system=false&enabled=false&status=enabled&status=disabled&source_type=git&source_type=zip&creator=user-1&creator=user-2'
    )
  })

  test('constructs detail, filter, update, delete, and test requests', async () => {
    const updateInput = { display_name: 'Updated skill', is_enabled: false }
    const testInput = { arguments: { prompt: 'hello' }, config: { model: 'test' } }

    await adminSkillsApi.getFilterOptions()
    await adminSkillsApi.get('skill-1')
    await adminSkillsApi.update('skill-1', updateInput)
    await adminSkillsApi.delete('skill-1')
    await adminSkillsApi.test('skill-1', testInput)

    expect(get).toHaveBeenNthCalledWith(1, '/admin/skills/filters')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/skills/skill-1')
    expect(patch).toHaveBeenCalledWith('/admin/skills/skill-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/admin/skills/skill-1')
    expect(post).toHaveBeenCalledWith('/admin/skills/skill-1/test', testInput)
  })

  test('constructs zip previews with and without a team', async () => {
    const file = new File(['skill'], 'skill.zip', { type: 'application/zip' })

    await adminSkillsApi.previewZip('team-1', file)
    await adminSkillsApi.previewZip(null, file)

    const firstForm = post.mock.calls[0]?.[1] as FormData
    const secondForm = post.mock.calls[1]?.[1] as FormData
    expect(post.mock.calls[0]?.[0]).toBe('/admin/skills/import/preview-zip')
    expect(post.mock.calls[0]?.[2]).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
    expect(firstForm.get('team_id')).toBe('team-1')
    expect(firstForm.get('file')).toEqual(file)
    expect(post.mock.calls[1]?.[0]).toBe('/admin/skills/import/preview-zip')
    expect(post.mock.calls[1]?.[2]).toEqual({ headers: { 'Content-Type': 'multipart/form-data' } })
    expect(secondForm.has('team_id')).toBe(false)
    expect(secondForm.get('file')).toEqual(file)
  })

  test('constructs git preview and install requests with exact options and payloads', async () => {
    const previewInput = { team_id: 'team-1', repo_url: 'https://example.com/skills.git', ref: 'main' }
    const installInput = { items: [{ package_path: 'skills/review', action: 'install' as const }], is_enabled: false }

    await adminSkillsApi.previewGit(previewInput)
    await adminSkillsApi.install('session-1', installInput)

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/admin/skills/import/preview-git',
      previewInput,
      { timeout: 180000 }
    )
    expect(post).toHaveBeenNthCalledWith(2, '/admin/skills/import/session-1/install', installInput)
  })

  test('propagates request errors', async () => {
    const error = new Error('request failed')
    post.mockRejectedValueOnce(error)
    const input = { team_id: 'team-1', repo_url: 'https://example.com/skills.git' }

    await expect(adminSkillsApi.previewGit(input)).rejects.toBe(error)
    expect(post).toHaveBeenCalledWith('/admin/skills/import/preview-git', input, { timeout: 180000 })
  })
})
