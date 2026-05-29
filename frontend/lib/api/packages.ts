import { api, axiosInstance } from './client'

export type ClouisleResourceType = 'tool' | 'agent' | 'workflow' | 'knowledge_base'
export type ClouisleDependencyStatus = 'resolved' | 'missing' | 'forbidden' | 'unsupported'
export type ClouisleConflictAction = 'install' | 'rename' | 'update' | 'skip'

export interface ClouislePackageDependency {
  type: string
  source_id?: string | null
  name?: string | null
  required: boolean
  hints: Record<string, unknown>
  status?: ClouisleDependencyStatus | null
  matched_id?: string | null
  message?: string | null
}

export interface ClouislePackageConflict {
  type: string
  existing_id?: string | null
  existing_name?: string | null
  message?: string | null
}

export interface ClouisleImportPreview {
  session_id: string
  package_id: string
  resource_type: ClouisleResourceType
  resource_name: string
  source_resource_id: string
  format_version: string
  app_version: string
  exported_at: string
  valid: boolean
  errors: string[]
  warnings: string[]
  dependencies: ClouislePackageDependency[]
  conflict?: ClouislePackageConflict | null
  allowed_actions: ClouisleConflictAction[]
  default_action: ClouisleConflictAction
}

export interface ClouisleImportInstallRequest {
  action: ClouisleConflictAction
  target_name?: string | null
  dependency_mapping?: Record<string, string>
}

export interface ClouisleImportInstallResult {
  installed?: string | null
  updated?: string | null
  skipped: boolean
  errors: string[]
  warnings: string[]
}

export interface PackagesApi {
  preview(teamId: string, file: File): Promise<ClouisleImportPreview>
  install(sessionId: string, input: ClouisleImportInstallRequest): Promise<ClouisleImportInstallResult>
  export(resourceType: ClouisleResourceType, resourceId: string): Promise<{ blob: Blob; filename: string }>
}

function createPackagesApi(prefix: '/packages' | '/admin/packages'): PackagesApi {
  return {
    preview(teamId: string, file: File): Promise<ClouisleImportPreview> {
      const formData = new FormData()
      formData.append('team_id', teamId)
      formData.append('file', file)
      return api.post<ClouisleImportPreview>(`${prefix}/import/preview`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      })
    },

    install(sessionId: string, input: ClouisleImportInstallRequest): Promise<ClouisleImportInstallResult> {
      return api.post<ClouisleImportInstallResult>(`${prefix}/import/${sessionId}/install`, input)
    },

    async export(resourceType: ClouisleResourceType, resourceId: string): Promise<{ blob: Blob; filename: string }> {
      const response = await axiosInstance.get(`${prefix}/${resourceType}/${resourceId}/export`, {
        responseType: 'blob',
      })
      const disposition = response.headers['content-disposition'] as string | undefined
      const filename = parseContentDispositionFilename(disposition) ?? `${resourceType}-${resourceId}.clouisle`
      return { blob: response.data, filename }
    },
  }
}

export const packagesApi = createPackagesApi('/packages')
export const adminPackagesApi = createPackagesApi('/admin/packages')

function parseContentDispositionFilename(disposition?: string): string | null {
  if (!disposition) return null
  const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encodedFilename) {
    try {
      return decodeURIComponent(encodedFilename)
    } catch {
      return encodedFilename
    }
  }
  return disposition.match(/filename="?([^";]+)"?/)?.[1] ?? null
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
