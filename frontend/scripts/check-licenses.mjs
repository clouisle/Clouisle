import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..', '..')
const frontendDir = path.resolve(__dirname, '..')
const policyPath = path.join(rootDir, 'license-policy.yml')
const nextConfigPath = path.join(frontendDir, 'next.config.ts')

function stripComment(line) {
  let inSingle = false
  let inDouble = false
  let result = ''

  for (const char of line) {
    if (char === '"' && !inSingle) {
      inDouble = !inDouble
    } else if (char === "'" && !inDouble) {
      inSingle = !inSingle
    } else if (char === '#' && !inSingle && !inDouble) {
      break
    }
    result += char
  }

  return result.trimEnd()
}

function parseScalar(value) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (trimmed === '[]') return []
  if (trimmed === '{}') return {}
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1)
  }
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  return trimmed
}

function parsePolicy(text) {
  const lines = text.split('\n').map(stripComment).filter((line) => line.trim())
  const root = {}
  const stack = [{ indent: -1, value: root }]

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index]
    const indent = rawLine.length - rawLine.trimStart().length
    const line = rawLine.trim()

    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop()
    }

    const parent = stack[stack.length - 1].value

    if (line.startsWith('- ')) {
      if (!Array.isArray(parent)) {
        throw new Error(`Invalid list item placement: ${rawLine}`)
      }

      const itemText = line.slice(2).trim()
      if (itemText.includes(':')) {
        const separatorIndex = itemText.indexOf(':')
        const key = itemText.slice(0, separatorIndex).trim()
        const value = itemText.slice(separatorIndex + 1).trim()
        const item = { [key]: parseScalar(value) }
        parent.push(item)
        stack.push({ indent, value: item })
      } else {
        parent.push(parseScalar(itemText))
      }
      continue
    }

    const separatorIndex = line.indexOf(':')
    const key = line.slice(0, separatorIndex).trim()
    const value = line.slice(separatorIndex + 1).trim()

    if (Array.isArray(parent)) {
      throw new Error(`Unexpected mapping under list: ${rawLine}`)
    }

    if (!value) {
      let nextNonEmpty = null
      for (let nextIndex = index + 1; nextIndex < lines.length; nextIndex += 1) {
        const nextLine = lines[nextIndex]
        const nextIndent = nextLine.length - nextLine.trimStart().length
        if (nextIndent <= indent) {
          break
        }
        nextNonEmpty = nextLine.trim()
        break
      }
      const container = nextNonEmpty && nextNonEmpty.startsWith('- ') ? [] : {}
      parent[key] = container
      stack.push({ indent, value: container })
      continue
    }

    parent[key] = parseScalar(value)
  }

  return root
}

function normalizeToken(token) {
  const cleaned = token
    .trim()
    .replace(/^\(+|\)+$/g, '')
    .replace(/\s+/g, ' ')
    .split('\n', 1)[0]
    .replace(/\s*\([^)]*\)$/g, '')
    .trim()
  const mapping = {
    'Apache 2.0': 'Apache-2.0',
    'Apache*': 'Apache-2.0',
    'Apache License 2.0': 'Apache-2.0',
    'Apache Software License': 'Apache-2.0',
    'MIT License': 'MIT',
    'MIT*': 'MIT',
    'BSD': 'BSD-3-Clause',
    'BSD License': 'BSD-3-Clause',
    '3-Clause BSD License': 'BSD-3-Clause',
    'BSD-3-Clause License': 'BSD-3-Clause',
    'BSD-2-Clause License': 'BSD-2-Clause',
    'The Unlicense': 'Unlicense',
    'ISC License': 'ISC',
    'Python Software Foundation License': 'PSF-2.0',
    'Mozilla Public License 2.0': 'MPL-2.0',
    'PSF': 'PSF-2.0',
    'ZLIB': 'Zlib',
    'UNLICENSED': 'UNLICENSED',
  }
  return mapping[cleaned] ?? cleaned
}

function splitExpression(licenseValue) {
  const cleaned = licenseValue.trim().replace(/\s+/g, ' ')
  if (!cleaned) return { mode: 'single', parts: [] }

  const inner = cleaned.replace(/^\(+|\)+$/g, '').replaceAll(';', ' OR ').replaceAll(',', ' OR ')
  if (inner.includes(' OR ')) {
    return { mode: 'or', parts: inner.split(' OR ').map(normalizeToken).filter(Boolean) }
  }
  if (inner.includes(' AND ')) {
    return { mode: 'and', parts: inner.split(' AND ').map(normalizeToken).filter(Boolean) }
  }
  if (inner.includes('/') && !inner.includes('http')) {
    return { mode: 'or', parts: inner.split('/').map(normalizeToken).filter(Boolean) }
  }
  return { mode: 'single', parts: [normalizeToken(inner)] }
}

function classify(policy, token) {
  if (policy.denied.has(token)) return 'denied'
  if (policy.allowed.has(token) || policy.conditional.has(token)) return 'allowed'
  return 'unknown'
}

function evaluateLicense(policy, licenseValue) {
  const normalized = normalizeToken(licenseValue)
  if (!normalized || normalized.toUpperCase() === 'UNKNOWN') {
    if (policy.failOnMissingLicense || policy.actionOnUnknown === 'deny') {
      return { ok: false, reason: 'unknown license' }
    }
    return { ok: true, reason: 'unknown license allowed by policy' }
  }

  const { mode, parts } = splitExpression(normalized)
  if (parts.length === 0) {
    return { ok: false, reason: 'missing license' }
  }

  const statuses = parts.map((part) => classify(policy, part))

  if (mode === 'or') {
    if (statuses.includes('allowed')) {
      return { ok: true, reason: `allowed via OR expression: ${parts.join(', ')}` }
    }
    if (statuses.includes('denied')) {
      return { ok: false, reason: `denied OR expression: ${parts.join(', ')}` }
    }
    return { ok: false, reason: `unknown OR expression: ${parts.join(', ')}` }
  }

  if (mode === 'and') {
    if (statuses.every((status) => status === 'allowed')) {
      return { ok: true, reason: `allowed AND expression: ${parts.join(', ')}` }
    }
    const denied = parts.filter((part, index) => statuses[index] === 'denied')
    if (denied.length > 0) {
      return { ok: false, reason: `denied AND expression component: ${denied.join(', ')}` }
    }
    const unknown = parts.filter((part, index) => statuses[index] === 'unknown')
    return { ok: false, reason: `unknown AND expression component: ${unknown.join(', ')}` }
  }

  const token = parts[0]
  if (policy.denied.has(token)) return { ok: false, reason: `denied license: ${token}` }
  if (policy.allowed.has(token)) return { ok: true, reason: `allowed license: ${token}` }
  if (policy.conditional.has(token)) return { ok: true, reason: `conditionally allowed license: ${token}` }
  return { ok: false, reason: `unknown license: ${token}` }
}

function isExceptionExpired(expiresOn) {
  if (!expiresOn) return false
  return new Date(`${expiresOn}T00:00:00Z`) < new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z')
}

function findException(policy, packageName, version, licenseValue) {
  const normalized = normalizeToken(licenseValue)
  return policy.exceptions.find((rule) => {
    if (rule.ecosystem && rule.ecosystem !== 'node') return false
    if (rule.package && rule.package !== packageName) return false
    if (rule.version && rule.version !== version) return false
    if (rule.license && rule.license !== normalized) return false
    if (isExceptionExpired(rule.expires_on)) return false
    return true
  })
}

async function loadPolicy() {
  const text = await readFile(policyPath, 'utf-8')
  const data = parsePolicy(text)
  return {
    actionOnUnknown: data.defaults?.action_on_unknown ?? 'deny',
    failOnMissingLicense: Boolean(data.defaults?.fail_on_missing_license ?? true),
    allowed: new Set(data.allowed_licenses ?? []),
    conditional: new Set(data.conditionally_allowed_licenses ?? []),
    denied: new Set(data.denied_licenses ?? []),
    exceptions: data.exceptions ?? [],
  }
}

async function runLicenseChecker() {
  const { stdout } = await execFileAsync(
    path.join(frontendDir, 'node_modules', '.bin', 'license-checker-rseidelsohn'),
    ['--json', '--production'],
    { cwd: frontendDir, maxBuffer: 10 * 1024 * 1024 },
  )
  return JSON.parse(stdout)
}

async function isNextImageOptimizationDisabled() {
  const config = await readFile(nextConfigPath, 'utf-8')
  return /images\s*:\s*\{[\s\S]*?unoptimized\s*:\s*true/.test(config)
}

function shouldIgnorePackage(name, disableNextImageOptimization) {
  if (!disableNextImageOptimization) {
    return false
  }

  return name === 'sharp' || name.startsWith('@img/sharp-') || name.startsWith('@img/sharp-libvips-')
}

function parsePackageKey(key) {
  const separatorIndex = key.lastIndexOf('@')
  return {
    name: key.slice(0, separatorIndex),
    version: key.slice(separatorIndex + 1),
  }
}

async function main() {
  const policy = await loadPolicy()
  const packages = await runLicenseChecker()
  const disableNextImageOptimization = await isNextImageOptimizationDisabled()
  const failures = []
  let ignoredPackages = 0

  for (const [key, info] of Object.entries(packages)) {
    const { name, version } = parsePackageKey(key)
    if (name === 'clouisle') {
      continue
    }
    if (shouldIgnorePackage(name, disableNextImageOptimization)) {
      ignoredPackages += 1
      continue
    }

    const licenseValue = String(info.licenses ?? '').trim().split('\n', 1)[0].trim()

    if (findException(policy, name, version, licenseValue)) {
      continue
    }

    const result = evaluateLicense(policy, licenseValue)
    if (!result.ok) {
      failures.push(`- ${name}@${version}: ${licenseValue || 'UNKNOWN'} (${result.reason})`)
    }
  }

  if (failures.length > 0) {
    console.error('License compliance check failed for frontend dependencies:')
    console.error(failures.join('\n'))
    process.exit(1)
  }

  const checkedCount = Object.keys(packages).length - ignoredPackages
  if (ignoredPackages > 0) {
    console.log(`Frontend license compliance check passed for ${checkedCount} dependencies. Ignored ${ignoredPackages} optional Next image optimization packages because images.unoptimized is enabled.`)
    return
  }

  console.log(`Frontend license compliance check passed for ${checkedCount} dependencies.`)
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
})
