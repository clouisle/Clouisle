import { ApiError } from '@/lib/api/client'

export type FieldErrors = Record<string, string>
export type RawFieldErrors = Record<string, string[]>
export type ValidationPathMap = Record<string, string>

export function normalizeValidationErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || !error.isValidationError()) {
    return {}
  }
  return error.getFieldErrors()
}

export function normalizeValidationErrorsRaw(error: unknown): RawFieldErrors {
  if (!(error instanceof ApiError) || !error.isValidationError()) {
    return {}
  }
  return error.getFieldErrorsRaw()
}

export function clearValidationError(errors: FieldErrors, key: string): FieldErrors {
  if (!errors[key]) {
    return errors
  }

  const next = { ...errors }
  delete next[key]
  return next
}

export function clearValidationErrorsByPrefix(errors: FieldErrors, prefix: string): FieldErrors {
  const nextEntries = Object.entries(errors).filter(([key]) => key !== prefix && !key.startsWith(`${prefix}.`))
  if (nextEntries.length === Object.keys(errors).length) {
    return errors
  }
  return Object.fromEntries(nextEntries)
}

export function mapValidationErrors(errors: FieldErrors, pathMap?: ValidationPathMap): FieldErrors {
  if (!pathMap) {
    return errors
  }

  return Object.fromEntries(
    Object.entries(errors).map(([key, value]) => {
      if (pathMap[key]) {
        return [pathMap[key], value]
      }

      const prefixEntry = Object.entries(pathMap).find(([backendKey]) => key.startsWith(`${backendKey}.`))
      if (!prefixEntry) {
        return [key, value]
      }

      const [backendKey, frontendKey] = prefixEntry
      return [key.replace(backendKey, frontendKey), value]
    })
  )
}

export function getFieldErrorObjects(errors: FieldErrors, key: string): Array<{ message: string }> | undefined {
  const message = errors[key]
  if (!message) {
    return undefined
  }
  return [{ message }]
}

export function getValidationSummaryEntries(
  errors: FieldErrors,
  inlineFields: Iterable<string>
): Array<[string, string]> {
  const inlineFieldSet = new Set(inlineFields)
  return Object.entries(errors).filter(([key]) => !inlineFieldSet.has(key))
}

export function formatValidationSummaryMessage(
  field: string,
  message: string,
  fieldLabels?: Record<string, string>
): string {
  if (field === '__all__') {
    return message
  }

  const label = fieldLabels?.[field]
  return label ? `${label}: ${message}` : message
}
