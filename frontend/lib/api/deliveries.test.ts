import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from './client'
import { deliveriesApi } from './deliveries'

let get: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
})

describe('deliveriesApi', () => {
  test('omits absent, empty and falsy filters from the list query', async () => {
    await deliveriesApi.list({})
    await deliveriesApi.list({ provider_type: [], status: [] })
    await deliveriesApi.list({ run_id: '', filename: '' })

    expect(get).toHaveBeenCalledTimes(3)
    expect(get).toHaveBeenNthCalledWith(1, '/admin/deliveries?')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/deliveries?')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/deliveries?')
  })

  test('repeats each provider and status value so the backend filters on any of them', async () => {
    await deliveriesApi.list({
      provider_type: ['feishu', 'wechat'],
      status: ['sent', 'error', 'unavailable'],
    })

    expect(get).toHaveBeenCalledWith(
      '/admin/deliveries?provider_type=feishu&provider_type=wechat&status=sent&status=error&status=unavailable'
    )
  })

  test('keeps run_id and filename independent of one another', async () => {
    await deliveriesApi.list({ run_id: 'run-1' })
    await deliveriesApi.list({ filename: 'report.pptx' })
    await deliveriesApi.list({ run_id: 'run-1', filename: 'report.pptx' })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/deliveries?run_id=run-1')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/deliveries?filename=report.pptx')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/deliveries?run_id=run-1&filename=report.pptx')
  })

  test('percent-encodes filenames and run identifiers that are not URL safe', async () => {
    await deliveriesApi.list({ filename: '报告 v1.pptx' })
    await deliveriesApi.list({ filename: 'a&b c' })
    await deliveriesApi.list({ filename: '+plus #hash :colon' })
    await deliveriesApi.list({ run_id: 'run/id ?' })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/deliveries?filename=%E6%8A%A5%E5%91%8A+v1.pptx')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/deliveries?filename=a%26b+c')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/deliveries?filename=%2Bplus+%23hash+%3Acolon')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/deliveries?run_id=run%2Fid+%3F')
  })

  test('sends explicit pagination bounds, including zero, alongside every other filter', async () => {
    await deliveriesApi.list({ limit: 25, offset: 0 })
    await deliveriesApi.list({
      provider_type: ['feishu'],
      status: ['error'],
      filename: 'a&b c',
      limit: 10,
      offset: 20,
    })
    await deliveriesApi.list({
      provider_type: ['feishu', 'wechat'],
      status: ['error', 'unknown'],
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      limit: 20,
      offset: 0,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/deliveries?limit=25&offset=0')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/admin/deliveries?provider_type=feishu&status=error&filename=a%26b+c&limit=10&offset=20'
    )
    expect(get).toHaveBeenNthCalledWith(
      3,
      '/admin/deliveries?provider_type=feishu&provider_type=wechat&status=error&status=unknown&run_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890&limit=20&offset=0'
    )
  })

  test('returns the decoded page payload and propagates request failures', async () => {
    const page = { items: [], total: 0, limit: 25, offset: 0 }
    const error = new Error('request failed')
    get.mockResolvedValueOnce(page).mockRejectedValueOnce(error)

    await expect(deliveriesApi.list({ limit: 25, offset: 0 })).resolves.toBe(page)
    await expect(deliveriesApi.list({})).rejects.toBe(error)
  })
})
