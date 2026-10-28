/**
 * Convert an elicitation `requested_schema` into safe form fields.
 *
 * Only top-level object properties are collected. Credential-shaped fields are
 * never rendered as inputs: elicitation must not become a password/token form,
 * so a schema containing one blocks acceptance instead.
 */

export type ElicitationFieldType = 'string' | 'number' | 'boolean' | 'enum' | 'json'

export interface ElicitationField {
  name: string
  label: string
  description: string | null
  type: ElicitationFieldType
  required: boolean
  options: Array<{ value: string; label: string; raw: string | number }>
  defaultValue: string | boolean
  /** Credential-shaped property; the request cannot be accepted in the UI. */
  secret: boolean
}

// Credential-shaped property names only: `max_tokens` / `token_count` are
// ordinary values and must remain fillable.
const SECRET_NAME =
  /^(password|passwd|secret|token|credentials?|authorization)$|(^|[_-])(password|passwd|secret|token)$|^((api|access|refresh|id|client|private)[_-]?(key|token|secret)|private[_-]?key)$/i

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringDefault(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

/** Build renderable fields from an object schema. Invalid shapes yield none. */
export function getElicitationFields(schema: unknown): ElicitationField[] {
  const root = asRecord(schema)
  if (!root || root.type !== 'object') return []

  const properties = asRecord(root.properties)
  if (!properties) return []

  const required = new Set(
    Array.isArray(root.required)
      ? root.required.filter((item): item is string => typeof item === 'string')
      : []
  )

  const fields: ElicitationField[] = []
  for (const [name, rawProperty] of Object.entries(properties)) {
    const property = asRecord(rawProperty)
    if (!property) continue

    const declaredType = property.type
    const enumValues = Array.isArray(property.enum) ? property.enum : null
    const isEnum =
      enumValues !== null
      && enumValues.length > 0
      && enumValues.every((value) => typeof value === 'string' || typeof value === 'number')

    let type: ElicitationFieldType = 'json'
    if (isEnum) type = 'enum'
    else if (declaredType === 'string') type = 'string'
    else if (declaredType === 'number' || declaredType === 'integer') type = 'number'
    else if (declaredType === 'boolean') type = 'boolean'

    const format = typeof property.format === 'string' ? property.format : ''
    const secret =
      format === 'password'
      || property.writeOnly === true
      || property['x-sensitive'] === true
      || SECRET_NAME.test(name)

    const description =
      typeof property.description === 'string' && property.description.trim()
        ? property.description.trim()
        : null
    const label =
      typeof property.title === 'string' && property.title.trim()
        ? property.title.trim()
        : name

    fields.push({
      name,
      label,
      description,
      type,
      required: required.has(name),
      options: isEnum
        ? enumValues.map((value) => ({
            value: String(value),
            label: String(value),
            raw: value,
          }))
        : [],
      defaultValue:
        type === 'boolean'
          ? property.default === true
          : stringDefault(property.default),
      secret,
    })
  }
  return fields
}

export interface ElicitationValidation {
  content: Record<string, unknown>
  errors: Record<string, string>
}

/**
 * Validate form values and build the exact object sent to the backend.
 * Blank optional values are omitted; anything else is type-coerced.
 */
export function buildElicitationContent(
  fields: ElicitationField[],
  values: Record<string, string | boolean>,
  messages: {
    required: (field: string) => string
    invalidNumber: (field: string) => string
    invalidJson: (field: string) => string
  }
): ElicitationValidation {
  const content: Record<string, unknown> = {}
  const errors: Record<string, string> = {}

  for (const field of fields) {
    if (field.secret) continue
    const raw = values[field.name]

    if (field.type === 'boolean') {
      content[field.name] = raw === true
      continue
    }

    const text = typeof raw === 'string' ? raw : ''
    if (!text.trim()) {
      if (field.required) errors[field.name] = messages.required(field.label)
      continue
    }

    if (field.type === 'number') {
      const parsed = Number(text)
      if (!Number.isFinite(parsed)) {
        errors[field.name] = messages.invalidNumber(field.label)
        continue
      }
      content[field.name] = parsed
      continue
    }

    if (field.type === 'json') {
      try {
        content[field.name] = JSON.parse(text)
      } catch {
        errors[field.name] = messages.invalidJson(field.label)
      }
      continue
    }

    if (field.type === 'enum') {
      const option = field.options.find((candidate) => candidate.value === text)
      content[field.name] = option ? option.raw : text
      continue
    }

    content[field.name] = text
  }

  return { content, errors }
}
