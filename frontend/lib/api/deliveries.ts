import { api } from './client'

export type DeliveryProvider = 'feishu' | 'wechat'
export type DeliveryStatus =
  | 'pending'
  | 'sending'
  | 'sent'
  | 'error'
  | 'unavailable'
  | 'unknown'

export interface DeliveryRecord {
  id: string
  provider_type: DeliveryProvider
  run_id: string | null
  user_id: string | null
  agent_id: string | null
  chat_id: string | null
  message_id: string | null
  event_key: string
  sequence: number
  kind: string
  filename: string | null
  content_type: string | null
  size: number | null
  media_type: string | null
  status: DeliveryStatus
  error: string | null
  error_detail: string | null
  has_media_key: boolean
  created_at: string
  updated_at: string
}

export interface DeliveryPage {
  items: DeliveryRecord[]
  total: number
  limit: number
  offset: number
}

export interface DeliveryQuery {
  provider_type?: DeliveryProvider[]
  status?: DeliveryStatus[]
  run_id?: string
  filename?: string
  limit?: number
  offset?: number
}

export const deliveriesApi = {
  list: (params: DeliveryQuery): Promise<DeliveryPage> => {
    const query = new URLSearchParams()
    params.provider_type?.forEach((value) => query.append('provider_type', value))
    params.status?.forEach((value) => query.append('status', value))
    if (params.run_id) query.set('run_id', params.run_id)
    if (params.filename) query.set('filename', params.filename)
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    if (params.offset !== undefined) query.set('offset', String(params.offset))
    return api.get<DeliveryPage>(`/admin/deliveries?${query}`)
  },
}
