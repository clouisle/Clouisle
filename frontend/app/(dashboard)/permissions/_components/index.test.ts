import { expect, mock, test } from 'bun:test'

const PermissionsClient = {}
const PermissionDialog = {}
const DeletePermissionDialog = {}

mock.module('./permissions-client', () => ({ PermissionsClient }))
mock.module('./permission-dialog', () => ({ PermissionDialog }))
mock.module('./delete-permission-dialog', () => ({ DeletePermissionDialog }))

const components = await import('./index')

test('re-exports the permission management components', () => {
  expect(components).toMatchObject({ PermissionsClient, PermissionDialog, DeletePermissionDialog })
})
