export const coverageSummary = (output: string) => {
  const summary = output.match(/^All files\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|/m)
  return summary ? { functions: Number(summary[1]), lines: Number(summary[2]) } : null
}

if (import.meta.main) {
const minimum = 95
// Stream the child output instead of buffering it: a long test run can exceed
// spawnSync's buffer, and a crashed runner hides the failing test entirely.
const child = Bun.spawn([
  'bun',
  'test',
  '--isolate',
  '--coverage',
  '--coverage-reporter=text',
  '--coverage-reporter=lcov',
], { cwd: import.meta.dir + '/..', stdout: 'pipe', stderr: 'pipe' })

let output = ''
const pump = async (
  stream: ReadableStream<Uint8Array>,
  sink: (text: string) => void
) => {
  const decoder = new TextDecoder()
  for await (const chunk of stream) {
    const text = decoder.decode(chunk, { stream: true })
    output += text
    sink(text)
  }
  const tail = decoder.decode()
  if (tail) {
    output += tail
    sink(tail)
  }
}

await Promise.all([
  pump(child.stdout, (text) => process.stdout.write(text)),
  pump(child.stderr, (text) => process.stderr.write(text)),
])
const exitCode = await child.exited
const stdout = output
const stderr = ''

if (exitCode !== 0) {
  const signal = child.signalCode ? ` signal=${child.signalCode}` : ''
  console.error(`bun test failed: exit=${exitCode}${signal}`)
  process.exit(exitCode || 1)
}

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
