import { expect, mock, test } from 'bun:test'

const RolesClient = {}
const RoleDialog = {}
const DeleteRoleDialog = {}

mock.module('./roles-client', () => ({ RolesClient }))
mock.module('./role-dialog', () => ({ RoleDialog }))
mock.module('./delete-role-dialog', () => ({ DeleteRoleDialog }))

const components = await import('./index')

test('re-exports the role management components', () => {
  expect(components).toMatchObject({ RolesClient, RoleDialog, DeleteRoleDialog })
})
