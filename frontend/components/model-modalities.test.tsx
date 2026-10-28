import { expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
const { ModelModalities } = await import('./model-modalities')

test('shows model type defaults and combines declared modalities without duplicates', () => {
  const html = renderToStaticMarkup(<ModelModalities modelType="chat" capabilities={{ input_modalities: ['text', 'image'], output_modalities: [] }} />)
  expect(html.match(/aria-label="inputModalities: modality.text"/g)).toHaveLength(1)
  expect(html).toContain('aria-label="inputModalities: modality.image"')
  expect(html).toContain('aria-label="outputModalities: modality.text"')
})

test.each([
  ['embedding', 'text', 'embedding'], ['decision', 'text', 'decision'],
  ['rerank', 'text', 'ranking'], ['tts', 'text', 'audio'], ['stt', 'audio', 'text'],
  ['audio_generation', 'text', 'audio'], ['text_to_image', 'text', 'image'], ['text_to_video', 'text', 'video'],
])('%s shows its baseline input and output', (modelType, input, output) => {
  const html = renderToStaticMarkup(<ModelModalities modelType={modelType} />)
  expect(html).toContain(`aria-label="inputModalities: modality.${input}"`)
  expect(html).toContain(`aria-label="outputModalities: modality.${output}"`)
})

test('unknown types without declarations show an unknown marker', () => {
  expect(renderToStaticMarkup(<ModelModalities modelType="unknown" capabilities={{ input_modalities: ['invalid'] }} />)).toContain('—')
})
