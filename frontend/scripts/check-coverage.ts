const SOURCE_ROOTS = ['app/', 'components/', 'contexts/', 'hooks/', 'lib/']

export function eligibleSource(path: string): boolean {
  return SOURCE_ROOTS.some((root) => path.startsWith(root))
    && /\.tsx?$/.test(path)
    && !/\.(?:test|spec)\.tsx?$/.test(path)
    && !path.endsWith('.d.ts')
}

export function missingCoverageSources(tracked: string[], lcov: string): string[] {
  const covered = new Set(
    lcov.match(/^SF:(.+)$/gm)?.map((line) => line.slice(3).replace(/^\.\//, '')) ?? [],
  )
  return tracked.filter(eligibleSource).filter((path) => !covered.has(path)).sort()
}

if (import.meta.main) {
  const tracked = Bun.spawnSync(['git', 'ls-files', '--', ...SOURCE_ROOTS], {
    cwd: import.meta.dir + '/..',
  })
  if (!tracked.success) {
    console.error(tracked.stderr.toString())
    process.exit(1)
  }

  const lcovPath = import.meta.dir + '/../coverage/lcov.info'
  const lcov = await Bun.file(lcovPath).text().catch(() => '')
  if (!lcov) {
    console.error(`Coverage report not found: ${lcovPath}`)
    process.exit(1)
  }

  const sources = tracked.stdout.toString().trim().split('\n').filter(Boolean)
  const missing = missingCoverageSources(sources, lcov)
  if (missing.length) {
    console.error(`${missing.length} eligible source files are absent from LCOV:`)
    console.error(missing.join('\n'))
    process.exit(1)
  }

  console.log(`All ${sources.filter(eligibleSource).length} eligible source files appear in LCOV.`)
}
