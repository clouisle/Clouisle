export const coverageSummary = (output: string) => {
  const summary = output.match(/^All files\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|/m)
  return summary ? { functions: Number(summary[1]), lines: Number(summary[2]) } : null
}

if (import.meta.main) {
const minimum = 95
const result = Bun.spawnSync([
  'bun',
  'test',
  '--isolate',
  '--coverage',
  '--coverage-reporter=text',
  '--coverage-reporter=lcov',
], { cwd: import.meta.dir + '/..' })

const stdout = result.stdout.toString()
const stderr = result.stderr.toString()
process.stdout.write(stdout)
process.stderr.write(stderr)

if (!result.success) process.exit(result.exitCode)

const metrics = coverageSummary(`${stdout}\n${stderr}`)
if (!metrics) {
  console.error('Unable to read Bun coverage summary')
  process.exit(1)
}

for (const [name, percent] of Object.entries(metrics)) {
  console.log(`Frontend ${name} coverage: ${percent.toFixed(2)}% (required: ${minimum.toFixed(2)}%)`)
  if (percent < minimum) process.exitCode = 1
}
}
