import { copyFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = resolve(fileURLToPath(new URL('..', import.meta.url)))
const source = resolve(frontendDir, 'node_modules/@embedpdf/pdfium/dist/pdfium.wasm')
const target = resolve(frontendDir, 'public/pdfium/pdfium.wasm')

await mkdir(dirname(target), { recursive: true })
await copyFile(source, target)

console.log(`[copy-pdfium-wasm] ${source} -> ${target}`)
