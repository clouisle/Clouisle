import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api, axiosInstance } from '../client'
import { auditLogsApi } from './audit-logs'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let exportGet: ReturnType<typeof spyOn>
let spies: Array<ReturnType<typeof spyOn>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  exportGet = spyOn(axiosInstance, 'get').mockResolvedValue({ data: undefined })
  spies = [get, post, exportGet]
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
})

describe('auditLogsApi', () => {
  test('serializes empty and filtered list queries', async () => {
    await auditLogsApi.list({})
    await auditLogsApi.list({
      page: 2,
      page_size: 50,
      search: 'sign in & out',
      status: ['success', 'failed'],
      action: ['user.login', 'user.logout'],
    })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/audit-logs?')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/admin/audit-logs?page=2&page_size=50&search=sign+in+%26+out&status=success&status=failed&action=user.login&action=user.logout'
    )
  })

  test('constructs detail, metadata, stats, and archive requests', async () => {
    await auditLogsApi.get('log-1')
    await auditLogsApi.getActions()
    await auditLogsApi.getStats()
    await auditLogsApi.getRetentionStats()
    await auditLogsApi.triggerArchive()

    expect(get).toHaveBeenNthCalledWith(1, '/admin/audit-logs/log-1')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/audit-logs/actions')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/audit-logs/stats')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/audit-logs/stats/retention')
    expect(post).toHaveBeenCalledWith('/admin/audit-logs/archive')
  })

  test('exports blobs with the default and requested formats', async () => {
    const csv = new Blob(['csv'])
    const json = new Blob(['json'])
    exportGet.mockResolvedValueOnce({ data: csv }).mockResolvedValueOnce({ data: json })

    await expect(auditLogsApi.export({ page: 1 })).resolves.toBe(csv)
    await expect(auditLogsApi.export({ status: ['failed'] }, 'json')).resolves.toBe(json)

    expect(exportGet).toHaveBeenNthCalledWith(
      1,
      '/admin/audit-logs/export?page=1&format=csv',
      { responseType: 'blob' }
    )
    expect(exportGet).toHaveBeenNthCalledWith(
      2,
      '/admin/audit-logs/export?status=failed&format=json',
      { responseType: 'blob' }
    )
  })

  test('propagates request and export errors', async () => {
    const requestError = new Error('request failed')
    const exportError = new Error('export failed')
    get.mockRejectedValueOnce(requestError)
    exportGet.mockRejectedValueOnce(exportError)

    await expect(auditLogsApi.get('log-1')).rejects.toBe(requestError)
    await expect(auditLogsApi.export({})).rejects.toBe(exportError)
  })
})
