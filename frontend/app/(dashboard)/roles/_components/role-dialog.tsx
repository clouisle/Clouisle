'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { rolesApi, permissionsApi, type Role, type Permission } from '@/lib/api/admin/roles'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Search, Shield, ChevronRight } from 'lucide-react'

interface RoleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  role: Role | null
  onSuccess: () => void
}

export function RoleDialog({ open, onOpenChange, role, onSuccess }: RoleDialogProps) {
  const t = useTranslations('roles')
  const commonT = useTranslations('common')
  
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [selectedPermissions, setSelectedPermissions] = React.useState<Set<string>>(new Set())
  const [permissions, setPermissions] = React.useState<Permission[]>([])
  const [permissionSearch, setPermissionSearch] = React.useState('')
  const [expandedScopes, setExpandedScopes] = React.useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = React.useState(false)
  const [isLoadingPermissions, setIsLoadingPermissions] = React.useState(false)
  
  const isEdit = !!role
  
  // 加载权限列表
  React.useEffect(() => {
    const loadPermissions = async () => {
      setIsLoadingPermissions(true)
      try {
        const data = await permissionsApi.getPermissions(1, 100)
        setPermissions(data.items)
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingPermissions(false)
      }
    }
    
    if (open) {
      loadPermissions()
    }
  }, [open])
  
  // 初始化表单
  React.useEffect(() => {
    if (open) {
      if (role) {
        setName(role.name)
        setDescription(role.description || '')
        setSelectedPermissions(new Set(role.permissions?.map(p => p.code) || []))
      } else {
        setName('')
        setDescription('')
        setSelectedPermissions(new Set())
      }
      setPermissionSearch('')
      setExpandedScopes(new Set())
    }
  }, [open, role])
  
  // 过滤权限
  const filteredPermissions = React.useMemo(() => {
    if (!permissionSearch) return permissions
    const query = permissionSearch.toLowerCase()
    return permissions.filter(p => 
      p.code.toLowerCase().includes(query) ||
      p.description?.toLowerCase().includes(query)
    )
  }, [permissions, permissionSearch])
  
  // 按 scope 分组权限
  const groupedPermissions = React.useMemo(() => {
    const groups: Record<string, Permission[]> = {}
    filteredPermissions.forEach(p => {
      if (!groups[p.scope]) groups[p.scope] = []
      groups[p.scope].push(p)
    })
    return groups
  }, [filteredPermissions])
  
  // 切换权限选中
  const togglePermission = (code: string) => {
    const newSelected = new Set(selectedPermissions)
    if (newSelected.has(code)) {
      newSelected.delete(code)
    } else {
      newSelected.add(code)
    }
    setSelectedPermissions(newSelected)
  }
  
  // 切换整组权限
  const toggleScope = (scope: string, perms: Permission[]) => {
    const codes = perms.map(p => p.code)
    const allSelected = codes.every(c => selectedPermissions.has(c))
    
    const newSelected = new Set(selectedPermissions)
    if (allSelected) {
      codes.forEach(c => newSelected.delete(c))
    } else {
      codes.forEach(c => newSelected.add(c))
    }
    setSelectedPermissions(newSelected)
  }
  
  // 切换分组展开/折叠
  const toggleScopeExpand = (scope: string) => {
    const newExpanded = new Set(expandedScopes)
    if (newExpanded.has(scope)) {
      newExpanded.delete(scope)
    } else {
      newExpanded.add(scope)
    }
    setExpandedScopes(newExpanded)
  }
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    
    try {
      if (isEdit && role) {
        // 更新角色基本信息
        await rolesApi.updateRole(role.id, { name, description })
        // 更新角色权限
        await rolesApi.updateRolePermissions(role.id, Array.from(selectedPermissions))
        toast.success(t('roleUpdated'))
      } else {
        // 创建角色
        await rolesApi.createRole({
          name,
          description,
          permissions: Array.from(selectedPermissions),
        })
        toast.success(t('roleCreated'))
      }
      onSuccess()
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('editRole') : t('createRole')}</DialogTitle>
          <DialogDescription>
            {isEdit ? t('editRoleDescription') : t('createRoleDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="flex-1 overflow-hidden flex flex-col -mx-6">
          <div className="flex-1 overflow-y-auto space-y-6 py-4 px-6">
            {/* 基本信息 */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t('roleName')} *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('roleNamePlaceholder')}
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="description">{t('description')}</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('descriptionPlaceholder')}
                  rows={2}
                />
              </div>
            </div>
            
            {/* 权限选择 */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>{t('permissions')}</Label>
                <Badge variant="secondary">
                  {selectedPermissions.size} {t('selected')}
                </Badge>
              </div>
              
              {/* 搜索 */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('searchPermissions')}
                  value={permissionSearch}
                  onChange={(e) => setPermissionSearch(e.target.value)}
                  className="pl-8"
                />
              </div>
              
              {/* 权限列表 */}
              <div className="border rounded-lg max-h-[300px] overflow-y-auto">
                {isLoadingPermissions ? (
                  <div className="p-4 text-center text-muted-foreground">
                    {commonT('loading')}
                  </div>
                ) : Object.keys(groupedPermissions).length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground">
                    {t('noPermissions')}
                  </div>
                ) : (
                  Object.entries(groupedPermissions).map(([scope, perms]) => {
                    const allSelected = perms.every(p => selectedPermissions.has(p.code))
                    const someSelected = perms.some(p => selectedPermissions.has(p.code))
                    const isExpanded = expandedScopes.has(scope) || permissionSearch !== ''
                    
                    return (
                      <div key={scope} className="border-b last:border-b-0">
                        {/* 分组标题 */}
                        <div className="flex items-center gap-2 p-3 hover:bg-muted/50 transition-colors">
                          <button
                            type="button"
                            className="flex items-center justify-center"
                            onClick={() => toggleScopeExpand(scope)}
                          >
                            <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                          </button>
                          <button
                            type="button"
                            className="flex items-center"
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleScope(scope, perms)
                            }}
                          >
                            <Checkbox
                              checked={allSelected}
                              data-state={someSelected && !allSelected ? 'indeterminate' : undefined}
                            />
                          </button>
                          <button
                            type="button"
                            className="flex-1 flex items-center gap-2 text-left"
                            onClick={() => toggleScopeExpand(scope)}
                          >
                            <Shield className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium capitalize">{scope}</span>
                          </button>
                          <Badge variant="outline" className="text-xs">
                            {perms.filter(p => selectedPermissions.has(p.code)).length}/{perms.length}
                          </Badge>
                        </div>
                        
                        {/* 权限项 */}
                        {isExpanded && (
                          <div className="pl-10 pb-2 space-y-1">
                            {perms.map((perm) => (
                              <button
                                key={perm.id}
                                type="button"
                                className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-muted/50 transition-colors rounded text-left"
                                onClick={() => togglePermission(perm.code)}
                              >
                                <Checkbox checked={selectedPermissions.has(perm.code)} />
                                <code className="text-sm bg-muted px-1.5 py-0.5 rounded">
                                  {perm.code}
                                </code>
                                {perm.description && (
                                  <span className="text-sm text-muted-foreground truncate">
                                    {perm.description}
                                  </span>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </div>
          
          <DialogFooter className="pt-4 border-t mx-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading || !name}>
              {isLoading ? commonT('loading') : (isEdit ? commonT('save') : commonT('create'))}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
