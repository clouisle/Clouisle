import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'

import { api } from './client'
import { skillsApi } from './skills'

afterEach(() => {
  mock.restore()
})

describe('skillsApi requests', () => {
  it('lists skills and gets details with optional team context', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({ system: [], team: [] })
    const params = {
      team_id: 'team-1',
      include_system: true,
      enabled: false,
      search: 'writer',
      category: 'productivity',
    }

    await skillsApi.list(params)
    await skillsApi.get('skill-1')
    await skillsApi.get('skill-1', 'team-1')

    expect(get).toHaveBeenNthCalledWith(1, '/skills', { params })
    expect(get).toHaveBeenNthCalledWith(2, '/skills/skill-1', { params: undefined })
    expect(get).toHaveBeenNthCalledWith(3, '/skills/skill-1', { params: { team_id: 'team-1' } })
  })

  it('previews zip and git imports with the required payload and timeout', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})
    const file = new File(['skill'], 'skill.zip', { type: 'application/zip' })
    const gitInput = { team_id: 'team-1', repo_url: 'https://example.com/skills.git', ref: 'main' }

    await skillsApi.previewZip('team-1', file)
    await skillsApi.previewGit(gitInput)

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/skills/import/preview-zip',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const formData = post.mock.calls[0]?.[1] as FormData
    const uploadedFile = formData.get('file') as File
    expect(formData.get('team_id')).toBe('team-1')
    expect(uploadedFile.name).toBe('skill.zip')
    expect(uploadedFile.type).toBe('application/zip')
    expect(await uploadedFile.text()).toBe('skill')
    expect(post).toHaveBeenNthCalledWith(2, '/skills/import/preview-git', gitInput, { timeout: 180000 })
  })

  it('installs, updates, deletes, and tests skills on their public routes', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})
    const patch = spyOn(api, 'patch').mockResolvedValue({})
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined)
    const installInput = {
      items: [{ package_path: 'skills/writer', action: 'install' as const }],
      is_enabled: true,
    }
    const updateInput = { display_name: 'Writer', is_enabled: false }
    const testInput = { arguments: { prompt: 'Hello' }, config: { model: 'default' } }

    await skillsApi.install('session-1', installInput)
    await skillsApi.update('skill-1', updateInput)
    await skillsApi.delete('skill-1')
    await skillsApi.test('skill-1', testInput)

    expect(post).toHaveBeenNthCalledWith(1, '/skills/import/session-1/install', installInput)
    expect(patch).toHaveBeenCalledWith('/skills/skill-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/skills/skill-1')
    expect(post).toHaveBeenNthCalledWith(2, '/skills/skill-1/test', testInput)
  })

  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    spyOn(api, 'get').mockRejectedValue(error)
    spyOn(api, 'post').mockRejectedValue(error)
    spyOn(api, 'patch').mockRejectedValue(error)
    spyOn(api, 'delete').mockRejectedValue(error)

    await expect(skillsApi.get('skill-1')).rejects.toBe(error)
    await expect(skillsApi.previewGit({ repo_url: 'https://example.com/skills.git' })).rejects.toBe(error)
    await expect(skillsApi.update('skill-1', { display_name: 'Writer' })).rejects.toBe(error)
    await expect(skillsApi.delete('skill-1')).rejects.toBe(error)
  })
})
