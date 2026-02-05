'use client'

import * as React from 'react'
import { usePermissions } from '@/hooks/use-permissions'

interface PermissionGuardProps {
  /**
   * Required permission(s) to render children
   * Can be a single permission string or an array of permissions
   */
  permission: string | string[]
  /**
   * If true, requires ALL permissions (AND logic)
   * If false (default), requires ANY permission (OR logic)
   */
  requireAll?: boolean
  /**
   * Content to render when user has permission
   */
  children: React.ReactNode
  /**
   * Optional fallback content when user doesn't have permission
   * If not provided, nothing will be rendered
   */
  fallback?: React.ReactNode
}

/**
 * A component that conditionally renders children based on user permissions.
 *
 * @example
 * // Single permission
 * <PermissionGuard permission="user:create">
 *   <Button>Create User</Button>
 * </PermissionGuard>
 *
 * @example
 * // Multiple permissions (OR logic - any permission grants access)
 * <PermissionGuard permission={["user:update", "user:delete"]}>
 *   <ActionMenu />
 * </PermissionGuard>
 *
 * @example
 * // Multiple permissions (AND logic - all permissions required)
 * <PermissionGuard permission={["settings:read", "settings:update"]} requireAll>
 *   <SettingsForm />
 * </PermissionGuard>
 *
 * @example
 * // With fallback
 * <PermissionGuard permission="user:create" fallback={<span>No permission</span>}>
 *   <Button>Create User</Button>
 * </PermissionGuard>
 */
export function PermissionGuard({
  permission,
  requireAll = false,
  children,
  fallback = null,
}: PermissionGuardProps) {
  const { hasPermission, hasAnyPermission, hasAllPermissions, loading } = usePermissions()

  // Don't render anything while loading to prevent flash
  if (loading) {
    return null
  }

  const permissions = Array.isArray(permission) ? permission : [permission]

  let hasAccess: boolean
  if (permissions.length === 1) {
    hasAccess = hasPermission(permissions[0])
  } else if (requireAll) {
    hasAccess = hasAllPermissions(permissions)
  } else {
    hasAccess = hasAnyPermission(permissions)
  }

  if (hasAccess) {
    return <>{children}</>
  }

  return <>{fallback}</>
}

/**
 * Hook version for more complex permission logic
 * Returns a function to check if user can perform an action
 */
export function useCanPerform() {
  const { hasPermission, hasAnyPermission, hasAllPermissions, loading, isSuperuser } = usePermissions()

  const canPerform = React.useCallback(
    (permission: string | string[], requireAll = false): boolean => {
      if (loading) return false
      if (isSuperuser) return true

      const permissions = Array.isArray(permission) ? permission : [permission]

      if (permissions.length === 1) {
        return hasPermission(permissions[0])
      }

      return requireAll ? hasAllPermissions(permissions) : hasAnyPermission(permissions)
    },
    [hasPermission, hasAnyPermission, hasAllPermissions, loading, isSuperuser]
  )

  return { canPerform, loading }
}
