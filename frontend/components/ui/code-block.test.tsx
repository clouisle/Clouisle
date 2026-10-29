import { afterEach, expect, mock, test } from 'bun:test'
import React, { act } from 'react'
import { Window } from 'happy-dom'
import { createRoot, type Root } from 'react-dom/client'
import { CodeBlock, CodeBlockActions, CodeBlockContent, CodeBlockCopyButton, CodeBlockFooter, CodeBlockHeader, CodeBlockTitle } from './code-block'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, { window, document: window.document, navigator: window.navigator, HTMLElement: window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true })
let root: Root | undefined
afterEach(() => { if (root) act(() => root!.unmount()); root = undefined; document.body.replaceChildren() })

test('shows numbered lines and copies the code', async () => {
  const writeText = mock(async () => {})
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root!.render(<CodeBlock>
    <CodeBlockHeader><CodeBlockTitle>Script</CodeBlockTitle><CodeBlockActions><CodeBlockCopyButton value={'one\ntwo'} /></CodeBlockActions></CodeBlockHeader>
    <CodeBlockContent lineNumbers startLine={9}>{'one\ntwo'}</CodeBlockContent>
    <CodeBlockFooter>JavaScript</CodeBlockFooter>
  </CodeBlock>))
  expect(container.textContent).toContain('9one10two')
  expect(container.textContent).toContain('Script')
  expect(container.textContent).toContain('JavaScript')
  await act(async () => container.querySelector('button')!.click())
  expect(writeText).toHaveBeenCalledWith('one\ntwo')
  expect(container.textContent).toContain('Copied')
})

test('reports a clipboard failure to the caller', async () => {
  const onError = mock(() => {})
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async () => { throw new Error('denied') } } })
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root!.render(<CodeBlockCopyButton value="secret" onError={onError} />))
  await act(async () => container.querySelector('button')!.click())
  expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'denied' }))
  expect(container.textContent).not.toContain('Copied')
})
