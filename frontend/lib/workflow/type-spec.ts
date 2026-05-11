/**
 * Workflow value TypeSpec — frontend mirror of
 * `backend/app/services/workflow/types.py::TypeSpec`.
 *
 * Used by the variable picker / node-config UI to reason about the structure
 * of a value flowing between nodes (object fields, array item types) without
 * forcing the user to declare schemas by hand.
 *
 * `source` distinguishes user-declared specs from those auto-inferred from a
 * debug run; `nullable` records that null was seen alongside the kind.
 */

export type TypeKind =
  | 'string'
  | 'number'
  | 'boolean'
  | 'object'
  | 'array'
  | 'file'
  | 'image'
  | 'files'
  | 'images'
  | 'null'
  | 'any'

export interface TypeSpec {
  kind: TypeKind
  item?: TypeSpec
  fields?: Record<string, TypeSpec>
  nullable?: boolean
  source?: 'declared' | 'inferred'
  sample?: unknown
}

const LEGACY_TYPE_ALIASES: Record<string, TypeKind> = {
  string: 'string',
  text: 'string',
  paragraph: 'string',
  select: 'string',
  number: 'number',
  integer: 'number',
  float: 'number',
  boolean: 'boolean',
  checkbox: 'boolean',
  object: 'object',
  array: 'array',
  list: 'array',
  file: 'file',
  image: 'image',
  files: 'files',
  images: 'images',
  any: 'any',
  null: 'null',
}

/** Translate a legacy node-config type string into a flat TypeSpec. */
export function legacyTypeToSpec(type: string | null | undefined): TypeSpec {
  if (!type) return { kind: 'any' }
  const kind = LEGACY_TYPE_ALIASES[type.toLowerCase()] ?? 'any'
  return { kind }
}

/** Compact label for a TypeSpec, used in the variable picker chip. */
export function describeTypeSpec(spec: TypeSpec | undefined): string {
  if (!spec) return ''
  switch (spec.kind) {
    case 'array':
      return spec.item ? `array<${describeTypeSpec(spec.item)}>` : 'array'
    case 'object': {
      if (!spec.fields) return 'object'
      const keys = Object.keys(spec.fields)
      if (keys.length === 0) return 'object'
      if (keys.length <= 3) return `object{${keys.join(', ')}}`
      return `object{${keys.slice(0, 3).join(', ')}, …}`
    }
    default:
      return spec.kind
  }
}

/**
 * Soft assignability check: can a value of `source` be used where `target` is
 * expected? Used by the variable selector to gray out (not hide) mismatched
 * options. Permissive on purpose:
 * - `any` / undefined target accepts anything
 * - `any` source is accepted by anything (we don't yet know its shape)
 * - kinds must otherwise match
 * - array: item types compared (or accepted if either has no item info)
 * - object: target fields must be a subset of source fields
 */
export function isAssignable(
  source: TypeSpec | undefined,
  target: TypeSpec | undefined,
): boolean {
  if (!target || target.kind === 'any') return true
  if (!source || source.kind === 'any') return true
  if (source.kind === 'null') return target.nullable === true
  if (source.kind !== target.kind) return false
  if (source.kind === 'array') {
    if (!source.item || !target.item) return true
    return isAssignable(source.item, target.item)
  }
  if (source.kind === 'object') {
    if (!target.fields) return true
    const sf = source.fields ?? {}
    return Object.entries(target.fields).every(([k, v]) =>
      k in sf ? isAssignable(sf[k], v) : false,
    )
  }
  return true
}
