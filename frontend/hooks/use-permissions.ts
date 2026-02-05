'use client'

import { useMemo, useState, useEffect } from 'react'
import { authApi, type User } from '@/lib/api'

export function usePermissions() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const userData = await authApi.getCurrentUser()
        setUser(userData)
      } catch {
        // Failed to get user info, may not be logged in
      } finally {
        setLoading(false)
      }
    }
    fetchUser()
  }, [])

  const permissions = useMemo(() => {
    if (!user) return new Set<string>()

    const perms = new Set<string>()

    // Superuser has all permissions
    if (user.is_superuser) {
      perms.add('*')
      return perms
    }

    // Collect all permissions from all roles
    for (const role of user.roles || []) {
      for (const perm of role.permissions || []) {
        perms.add(perm.code)
      }
    }

    return perms
  }, [user])

  const hasPermission = (permission: string): boolean => {
    if (permissions.has('*')) return true
    return permissions.has(permission)
  }

  const hasAnyPermission = (perms: string[]): boolean => {
    return perms.some((p) => hasPermission(p))
  }

  const hasAllPermissions = (perms: string[]): boolean => {
    return perms.every((p) => hasPermission(p))
  }

  const canAccessDashboard = hasPermission('dashboard:access')

  return {
    user,
    loading,
    permissions,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canAccessDashboard,
    isSuperuser: user?.is_superuser ?? false,
  }
}

/**
 * Permission map for sidebar menu items
 * Maps URL paths to required permissions
 */
export const MENU_PERMISSION_MAP: Record<string, string> = {
  // Dashboard requires dashboard:access
  '/dashboard': 'dashboard:access',
  // User management
  '/users': 'user:read',
  '/roles': 'role:read',
  '/permissions': 'permission:read',
  // Model management
  '/models': 'model:read',
  // Audit logs
  '/audit-logs': 'audit:read',
  // Site settings
  '/site-settings': 'settings:read',
  // API Keys (team-isolated, all users with apikey:read can access)
  '/api-keys': 'apikey:read',
  // Tools (team-isolated)
  '/tools': 'tool:read',
  // Notifications
  '/notifications': 'dashboard:access',
}

/**
 * Check if a menu item should be visible based on user permissions
 */
export function canAccessMenuItem(
  url: string,
  hasPermission: (perm: string) => boolean
): boolean {
  const requiredPerm = MENU_PERMISSION_MAP[url]
  // If no permission mapping exists, allow access
  if (!requiredPerm) return true
  return hasPermission(requiredPerm)
}
