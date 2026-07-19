import { expect, mock, test } from 'bun:test'

const ModelCard = {}
const ModelCardSkeleton = {}
const ModelDetailDialog = {}

mock.module('./model-card', () => ({ ModelCard, ModelCardSkeleton }))
mock.module('./model-detail-dialog', () => ({ ModelDetailDialog }))

const components = await import('./index')

test('re-exports the platform model components', () => {
  expect(components).toMatchObject({ ModelCard, ModelCardSkeleton, ModelDetailDialog })
})
