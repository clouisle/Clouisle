import { expect, mock, test } from 'bun:test'

const UserTable = {}
const UserHeader = {}
const UserDialog = {}
const DeleteUserDialog = {}
const UsersClient = {}

mock.module('./user-table', () => ({ UserTable }))
mock.module('./user-header', () => ({ UserHeader }))
mock.module('./user-dialog', () => ({ UserDialog }))
mock.module('./delete-user-dialog', () => ({ DeleteUserDialog }))
mock.module('./users-client', () => ({ UsersClient }))

const components = await import('./index')

test('re-exports the dashboard user management components', () => {
  expect(components).toMatchObject({
    UserTable,
    UserHeader,
    UserDialog,
    DeleteUserDialog,
    UsersClient,
  })
})
