'use client'

import { usePermissions } from '@/hooks/use-permissions'
import { canAccessRoute } from '@/lib/route-permissions'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

interface PermissionGuardProps {
  /**
   * Required permission code (e.g., 'user:read', 'dashboard:access')
   */
  permission: string
  /**
   * Content to render if user has permission
   */
  children: React.ReactNode
  /**
   * Optional fallback content to render if user doesn't have permission
   * If not provided, nothing will be rendered
   */
  fallback?: React.ReactNode
  /**
   * If true, redirect to specified path when permission is denied
   */
  redirectTo?: string
}

/**
 * Component that conditionally renders children based on user permissions.
 *
 * Usage:
 * ```tsx
 * <PermissionGuard permission="user:read">
 *   <UserList />
 * </PermissionGuard>
 *
 * <PermissionGuard permission="settings:update" fallback={<ReadOnlyView />}>
 *   <EditableView />
 * </PermissionGuard>
 *
 * <PermissionGuard permission="dashboard:access" redirectTo="/app">
 *   <DashboardContent />
 * </PermissionGuard>
 * ```
 */
export function PermissionGuard({
  permission,
  children,
  fallback,
  redirectTo,
}: PermissionGuardProps) {
  const { hasPermission, loading } = usePermissions()
  const router = useRouter()

  const hasAccess = hasPermission(permission)

  useEffect(() => {
    if (!loading && !hasAccess && redirectTo) {
      router.replace(redirectTo)
    }
  }, [loading, hasAccess, redirectTo, router])

  // Show nothing while loading
  if (loading) {
    return null
  }

  // User has permission, render children
  if (hasAccess) {
    return <>{children}</>
  }

  // User doesn't have permission
  if (redirectTo) {
    // Will redirect via useEffect, show nothing
    return null
  }

  // Show fallback if provided
  if (fallback) {
    return <>{fallback}</>
  }

  // No fallback, render nothing
  return null
}

interface AnyPermissionGuardProps {
  /**
   * Array of permission codes - user needs at least one
   */
  permissions: string[]
  children: React.ReactNode
  fallback?: React.ReactNode
  redirectTo?: string
}

/**
 * Component that renders children if user has ANY of the specified permissions.
 */
export function AnyPermissionGuard({
  permissions,
  children,
  fallback,
  redirectTo,
}: AnyPermissionGuardProps) {
  const { hasAnyPermission, loading } = usePermissions()
  const router = useRouter()

  const hasAccess = hasAnyPermission(permissions)

  useEffect(() => {
    if (!loading && !hasAccess && redirectTo) {
      router.replace(redirectTo)
    }
  }, [loading, hasAccess, redirectTo, router])

  if (loading) {
    return null
  }

  if (hasAccess) {
    return <>{children}</>
  }

  if (redirectTo) {
    return null
  }

  if (fallback) {
    return <>{fallback}</>
  }

  return null
}

interface AllPermissionsGuardProps {
  /**
   * Array of permission codes - user needs all of them
   */
  permissions: string[]
  children: React.ReactNode
  fallback?: React.ReactNode
  redirectTo?: string
}

/**
 * Component that renders children only if user has ALL of the specified permissions.
 */
export function AllPermissionsGuard({
  permissions,
  children,
  fallback,
  redirectTo,
}: AllPermissionsGuardProps) {
  const { hasAllPermissions, loading } = usePermissions()
  const router = useRouter()

  const hasAccess = hasAllPermissions(permissions)

  useEffect(() => {
    if (!loading && !hasAccess && redirectTo) {
      router.replace(redirectTo)
    }
  }, [loading, hasAccess, redirectTo, router])

  if (loading) {
    return null
  }

  if (hasAccess) {
    return <>{children}</>
  }

  if (redirectTo) {
    return null
  }

  if (fallback) {
    return <>{fallback}</>
  }

  return null
}

interface SuperuserGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  redirectTo?: string
}

/**
 * Component that renders children only if user is a superuser.
 */
export function SuperuserGuard({
  children,
  fallback,
  redirectTo,
}: SuperuserGuardProps) {
  const { isSuperuser, loading } = usePermissions()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !isSuperuser && redirectTo) {
      router.replace(redirectTo)
    }
  }, [loading, isSuperuser, redirectTo, router])

  if (loading) {
    return null
  }

  if (isSuperuser) {
    return <>{children}</>
  }

  if (redirectTo) {
    return null
  }

  if (fallback) {
    return <>{fallback}</>
  }

  return null
}

interface RoutePermissionGuardProps {
  children: React.ReactNode
  redirectTo?: string
  fallback?: React.ReactNode
}

export function RoutePermissionGuard({
  children,
  redirectTo = '/app',
  fallback,
}: RoutePermissionGuardProps) {
  const pathname = usePathname()
  const { hasPermission, isSuperuser, loading } = usePermissions()
  const router = useRouter()

  const hasAccess = pathname ? canAccessRoute(pathname, hasPermission, isSuperuser) : true

  useEffect(() => {
    if (!loading && !hasAccess && redirectTo) {
      router.replace(redirectTo)
    }
  }, [loading, hasAccess, redirectTo, router])

  if (loading) {
    return null
  }

  if (hasAccess) {
    return <>{children}</>
  }

  if (redirectTo) {
    return null
  }

  if (fallback) {
    return <>{fallback}</>
  }

  return null
}
