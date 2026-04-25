'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, Type, AlignLeft, ListChecks, Hash, CheckSquare, Brackets, Braces, File, Image as ImageIcon, Files, Images } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { Parameter, ParameterType } from '../types'

interface ParameterEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingParam: Parameter | null
  existingParams: Parameter[]
  onSave: (param: Parameter) => void
}

export function ParameterEditDialog({
  open,
  onOpenChange,
  editingParam,
  existingParams,
  onSave,
}: ParameterEditDialogProps) {
  const t = useTranslations('workflow')
  const [paramForm, setParamForm] = React.useState<Partial<Parameter>>({})

  React.useEffect(() => {
    if (open) {
      if (editingParam) {
        setParamForm({ ...editingParam })
      } else {
        setParamForm({
          name: '',
          type: 'text',
          required: false,
          defaultValue: '',
          description: '',
        })
      }
    }
  }, [open, editingParam])

  // 检查变量名是否重复
  const isVariableNameDuplicate = (name: string): boolean => {
    const existingNames = existingParams
      .filter(p => editingParam ? p.id !== editingParam.id : true)
      .map(p => p.name.toLowerCase())
    return existingNames.includes(name.toLowerCase())
  }

  // 获取变量名验证错误信息
  const getVariableNameError = (): string | null => {
    const name = paramForm.name?.trim() || ''
    if (!name) return null
    if (!isValidVariableName(name)) {
      return t('dialogs.parameterEdit.nameFormatError')
    }
    if (isVariableNameDuplicate(name)) {
      return t('dialogs.parameterEdit.nameDuplicate')
    }
    return null
  }

  const variableNameError = getVariableNameError()

  const handleSave = () => {
    const name = paramForm.name?.trim()
    if (!name) return
    if (variableNameError) return
    
    const param: Parameter = {
      id: editingParam?.id || `param_${Date.now()}`,
      name,
      type: (paramForm.type as ParameterType) || 'text',
      required: paramForm.required || false,
      defaultValue: paramForm.defaultValue || '',
      description: paramForm.description || '',
      options: paramForm.options,
      fileConfig: paramForm.fileConfig,
    }
    
    onSave(param)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-100 max-h-[85vh] flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle className="text-base">
            {editingParam ? t('dialogs.parameterEdit.editTitle') : t('dialogs.parameterEdit.addTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto -mx-6 px-6">
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="param-name" className="text-xs">{t('dialogs.parameterEdit.nameLabel')}</Label>
              <Input
                id="param-name"
                value={paramForm.name || ''}
                onChange={(e) => setParamForm({ ...paramForm, name: e.target.value })}
                placeholder={t('dialogs.parameterEdit.namePlaceholder')}
                className={cn('h-9', variableNameError && paramForm.name && 'border-destructive! ring-destructive/20!')}
              />
              {variableNameError && paramForm.name && (
                <p className="text-[11px] text-destructive">{variableNameError}</p>
              )}
              <p className="text-[10px] text-muted-foreground">{t('dialogs.parameterEdit.nameHint')}</p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="param-type" className="text-xs">{t('dialogs.parameterEdit.typeLabel')}</Label>
              <Select
                value={paramForm.type || 'text'}
                onValueChange={(value) => setParamForm({ ...paramForm, type: value as ParameterType, fileConfig: undefined })}
              >
                <SelectTrigger size="default" className="w-full">
                  <SelectValue>
                    {paramForm.type && (
                      <span className="flex items-center gap-2">
                        {paramForm.type === 'text' && <><Type className="h-4 w-4" /> {t('dialogs.parameterEdit.typeText')}</>}
                        {paramForm.type === 'paragraph' && <><AlignLeft className="h-4 w-4" /> {t('dialogs.parameterEdit.typeParagraph')}</>}
                        {paramForm.type === 'select' && <><ListChecks className="h-4 w-4" /> {t('dialogs.parameterEdit.typeSelect')}</>}
                        {paramForm.type === 'number' && <><Hash className="h-4 w-4" /> {t('dialogs.parameterEdit.typeNumber')}</>}
                        {paramForm.type === 'checkbox' && <><CheckSquare className="h-4 w-4" /> {t('dialogs.parameterEdit.typeCheckbox')}</>}
                        {paramForm.type === 'array' && <><Brackets className="h-4 w-4" /> {t('dialogs.parameterEdit.typeArray')}</>}
                        {paramForm.type === 'object' && <><Braces className="h-4 w-4" /> {t('dialogs.parameterEdit.typeObject')}</>}
                        {paramForm.type === 'file' && <><File className="h-4 w-4" /> {t('dialogs.parameterEdit.typeFile')}</>}
                        {paramForm.type === 'image' && <><ImageIcon className="h-4 w-4" /> {t('dialogs.parameterEdit.typeImage')}</>}
                        {paramForm.type === 'files' && <><Files className="h-4 w-4" /> {t('dialogs.parameterEdit.typeFiles')}</>}
                        {paramForm.type === 'images' && <><Images className="h-4 w-4" /> {t('dialogs.parameterEdit.typeImages')}</>}
                      </span>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">
                    <span className="flex items-center gap-2"><Type className="h-4 w-4" /> {t('dialogs.parameterEdit.typeText')}</span>
                  </SelectItem>
                  <SelectItem value="paragraph">
                    <span className="flex items-center gap-2"><AlignLeft className="h-4 w-4" /> {t('dialogs.parameterEdit.typeParagraph')}</span>
                  </SelectItem>
                  <SelectItem value="select">
                    <span className="flex items-center gap-2"><ListChecks className="h-4 w-4" /> {t('dialogs.parameterEdit.typeSelect')}</span>
                  </SelectItem>
                  <SelectItem value="number">
                    <span className="flex items-center gap-2"><Hash className="h-4 w-4" /> {t('dialogs.parameterEdit.typeNumber')}</span>
                  </SelectItem>
                  <SelectItem value="checkbox">
                    <span className="flex items-center gap-2"><CheckSquare className="h-4 w-4" /> {t('dialogs.parameterEdit.typeCheckbox')}</span>
                  </SelectItem>
                  <SelectItem value="array">
                    <span className="flex items-center gap-2"><Brackets className="h-4 w-4" /> {t('dialogs.parameterEdit.typeArray')}</span>
                  </SelectItem>
                  <SelectItem value="object">
                    <span className="flex items-center gap-2"><Braces className="h-4 w-4" /> {t('dialogs.parameterEdit.typeObject')}</span>
                  </SelectItem>
                  <SelectItem value="file">
                    <span className="flex items-center gap-2"><File className="h-4 w-4" /> {t('dialogs.parameterEdit.typeFile')}</span>
                  </SelectItem>
                  <SelectItem value="image">
                    <span className="flex items-center gap-2"><ImageIcon className="h-4 w-4" /> {t('dialogs.parameterEdit.typeImage')}</span>
                  </SelectItem>
                  <SelectItem value="files">
                    <span className="flex items-center gap-2"><Files className="h-4 w-4" /> {t('dialogs.parameterEdit.typeFiles')}</span>
                  </SelectItem>
                  <SelectItem value="images">
                    <span className="flex items-center gap-2"><Images className="h-4 w-4" /> {t('dialogs.parameterEdit.typeImages')}</span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* 根据类型显示不同的默认值表单 */}
            {paramForm.type === 'text' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultValueLabel')}</Label>
                <Input
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder={t('dialogs.parameterEdit.defaultTextPlaceholder')}
                  className="h-9"
                />
              </div>
            )}

            {paramForm.type === 'paragraph' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultValueLabel')}</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder={t('dialogs.parameterEdit.defaultParagraphPlaceholder')}
                  className="min-h-20 resize-none"
                />
              </div>
            )}

            {paramForm.type === 'select' && (
              <div className="space-y-2">
                <Label className="text-xs">{t('dialogs.parameterEdit.optionsLabel')}</Label>
                <div className="space-y-1.5">
                  {(paramForm.options || ['']).map((option, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Input
                        value={option}
                        onChange={(e) => {
                          const newOptions = [...(paramForm.options || [''])]
                          newOptions[index] = e.target.value
                          setParamForm({ ...paramForm, options: newOptions })
                        }}
                        placeholder={t('dialogs.parameterEdit.optionPlaceholder', { index: index + 1 })}
                        className="h-8 text-sm flex-1"
                      />
                      {(paramForm.options || ['']).length > 1 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0"
                          onClick={() => {
                            const newOptions = (paramForm.options || ['']).filter((_, i) => i !== index)
                            setParamForm({ ...paramForm, options: newOptions })
                          }}
                        >
                          <Trash2 className="h-3 w-3 text-destructive" />
                        </Button>
                      )}
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs"
                    onClick={() => {
                      setParamForm({ ...paramForm, options: [...(paramForm.options || ['']), ''] })
                    }}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {t('dialogs.parameterEdit.addOption')}
                  </Button>
                </div>
                <div className="space-y-2 pt-2">
                  <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultSelectedLabel')}</Label>
                  <Select
                    value={paramForm.defaultValue || ''}
                    onValueChange={(value) => setParamForm({ ...paramForm, defaultValue: value ?? undefined })}
                  >
                    <SelectTrigger size="default" className="w-full">
                      <SelectValue>{paramForm.defaultValue || t('dialogs.parameterEdit.defaultSelectPlaceholder')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {(paramForm.options || []).filter(Boolean).map((option, index) => (
                        <SelectItem key={index} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {paramForm.type === 'number' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultValueLabel')}</Label>
                <Input
                  id="param-default"
                  type="number"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder={t('dialogs.parameterEdit.defaultNumberPlaceholder')}
                  className="h-9"
                />
              </div>
            )}

            {paramForm.type === 'checkbox' && (
              <div className="flex items-center justify-between">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultCheckedLabel')}</Label>
                <Switch
                  id="param-default"
                  checked={paramForm.defaultValue === 'true'}
                  onCheckedChange={(checked) => setParamForm({ ...paramForm, defaultValue: checked ? 'true' : 'false' })}
                />
              </div>
            )}

            {paramForm.type === 'array' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultJsonLabel')}</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder={t('dialogs.parameterEdit.arrayExample')}
                  className="min-h-24 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">{t('dialogs.parameterEdit.jsonArrayHint')}</p>
              </div>
            )}

            {paramForm.type === 'object' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">{t('dialogs.parameterEdit.defaultJsonLabel')}</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder={t('dialogs.parameterEdit.objectExample')}
                  className="min-h-24 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">{t('dialogs.parameterEdit.jsonObjectHint')}</p>
              </div>
            )}

            {/* 文件类型配置 */}
            {(paramForm.type === 'file' || paramForm.type === 'image') && (
              <div className="space-y-4 rounded-lg border p-3">
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.maxFileSizeLabel')}</Label>
                  <Input
                    type="number"
                    value={paramForm.fileConfig?.maxSize || (paramForm.type === 'image' ? 10 : 50)}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: { ...paramForm.fileConfig, maxSize: parseInt(e.target.value) || 10 }
                    })}
                    className="h-9"
                    min={1}
                    max={100}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.acceptFileTypesLabel')}</Label>
                  <Input
                    value={(paramForm.fileConfig?.accept || []).join(', ')}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: {
                        ...paramForm.fileConfig,
                        accept: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      }
                    })}
                    placeholder={paramForm.type === 'image' ? '.jpg, .png, .gif, .webp' : '.pdf, .doc, .docx, .txt'}
                    className="h-9"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    {t('dialogs.parameterEdit.fileTypeHint')}
                  </p>
                </div>
              </div>
            )}

            {paramForm.type === 'files' && (
              <div className="space-y-4 rounded-lg border p-3">
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.maxFilesLabel')}</Label>
                  <Input
                    type="number"
                    value={paramForm.fileConfig?.maxFiles || 5}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: { ...paramForm.fileConfig, maxFiles: parseInt(e.target.value) || 5 }
                    })}
                    className="h-9"
                    min={1}
                    max={20}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.maxSizePerFileLabel')}</Label>
                  <Input
                    type="number"
                    value={paramForm.fileConfig?.maxSize || 50}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: { ...paramForm.fileConfig, maxSize: parseInt(e.target.value) || 50 }
                    })}
                    className="h-9"
                    min={1}
                    max={100}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.acceptFileTypesLabel')}</Label>
                  <Input
                    value={(paramForm.fileConfig?.accept || []).join(', ')}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: {
                        ...paramForm.fileConfig,
                        accept: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      }
                    })}
                    placeholder=".pdf, .doc, .docx, .txt, image/*"
                    className="h-9"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    {t('dialogs.parameterEdit.fileTypeHint')}
                  </p>
                </div>
              </div>
            )}

            {paramForm.type === 'images' && (
              <div className="space-y-4 rounded-lg border p-3">
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.maxImagesLabel')}</Label>
                  <Input
                    type="number"
                    value={paramForm.fileConfig?.maxFiles || 9}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: { ...paramForm.fileConfig, maxFiles: parseInt(e.target.value) || 9 }
                    })}
                    className="h-9"
                    min={1}
                    max={20}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.maxSizePerImageLabel')}</Label>
                  <Input
                    type="number"
                    value={paramForm.fileConfig?.maxSize || 10}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: { ...paramForm.fileConfig, maxSize: parseInt(e.target.value) || 10 }
                    })}
                    className="h-9"
                    min={1}
                    max={50}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('dialogs.parameterEdit.acceptImageTypesLabel')}</Label>
                  <Input
                    value={(paramForm.fileConfig?.accept || []).join(', ')}
                    onChange={(e) => setParamForm({
                      ...paramForm,
                      fileConfig: {
                        ...paramForm.fileConfig,
                        accept: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      }
                    })}
                    placeholder=".jpg, .png, .gif, .webp"
                    className="h-9"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    {t('dialogs.parameterEdit.imageTypeHint')}
                  </p>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="param-desc" className="text-xs">{t('dialogs.parameterEdit.descriptionLabel')}</Label>
              <Input
                id="param-desc"
                value={paramForm.description || ''}
                onChange={(e) => setParamForm({ ...paramForm, description: e.target.value })}
                placeholder={t('dialogs.parameterEdit.descriptionPlaceholder')}
                className="h-9"
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="param-required" className="text-xs">{t('dialogs.parameterEdit.requiredLabel')}</Label>
              <Switch
                id="param-required"
                checked={paramForm.required || false}
                onCheckedChange={(checked) => setParamForm({ ...paramForm, required: checked })}
              />
            </div>
          </div>
        </div>
        <DialogFooter className="shrink-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t('dialogs.parameterEdit.cancel')}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!paramForm.name?.trim() || !!variableNameError}>
            {editingParam ? t('dialogs.parameterEdit.save') : t('dialogs.parameterEdit.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
