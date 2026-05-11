'use client'

import * as React from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { systemParameters, parameterTypeConfig } from '../constants'
import type { Parameter } from '../types'

interface StartNodeConfigProps {
  parameters: Parameter[]
  onAddParameter: () => void
  onEditParameter: (param: Parameter) => void
  onRemoveParameter: (id: string) => void
}

export function StartNodeConfig({
  parameters,
  onAddParameter,
  onEditParameter,
  onRemoveParameter,
}: StartNodeConfigProps) {
  const t = useTranslations('workflow')

  return (
    <div className="space-y-4">
      {/* 系统参数（只读） */}
      <div className="space-y-2">
        <Label className="text-xs font-medium text-muted-foreground">{t('configStart.system')}</Label>
        <div className="space-y-1">
          {systemParameters.map((param) => (
            <div 
              key={param.id} 
              className="flex items-center justify-between py-1 px-2 text-xs"
            >
              <span className="text-muted-foreground flex items-center gap-1.5">
                <span className="w-3 h-3 rounded border border-orange-400 flex items-center justify-center text-[8px] text-orange-400 font-medium">S</span>
                {param.name}
              </span>
              <span className="text-muted-foreground/60">
                {param.valueType}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 用户输入参数 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">{t('configStart.inputParameters')}</Label>
          <Button 
            variant="ghost" 
            size="sm" 
            className="h-6 px-2 text-xs"
            onClick={onAddParameter}
          >
            <Plus className="h-3 w-3 mr-1" />
            {t('configCommon.add')}
          </Button>
        </div>
        
        {parameters.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">
            {t('configStart.noParameters')}
          </p>
        ) : (
          <div className="space-y-1">
            {parameters.map((param) => {
              const typeConfig = parameterTypeConfig[param.type] || parameterTypeConfig.text
              const TypeIcon = typeConfig.icon
              return (
                <div 
                  key={param.id} 
                  className="group flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => onEditParameter(param)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <TypeIcon className="h-4 w-4 text-primary/70 shrink-0" />
                    <span className="text-xs font-medium truncate">{param.name || t('configCommon.unnamed')}</span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {param.required && (
                      <span className="text-xs text-muted-foreground group-hover:hidden">{t('configCommon.required')}</span>
                    )}
                    <span className="text-xs text-muted-foreground px-1.5 py-0.5 rounded border border-border group-hover:hidden">
                      {typeConfig.valueType}
                    </span>
                    {/* 悬浮显示的操作按钮 */}
                    <div className="hidden group-hover:flex items-center gap-0.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5"
                        onClick={(e) => {
                          e.stopPropagation()
                          onEditParameter(param)
                        }}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 text-destructive hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          onRemoveParameter(param.id)
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
