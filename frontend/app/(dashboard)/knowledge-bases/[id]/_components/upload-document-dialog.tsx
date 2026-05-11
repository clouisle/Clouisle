'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { Upload, FileText, X, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { knowledgeBasesApi, type Document } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { siteSettingsApi } from '@/lib/api/site-settings'
import {
  BYTES_PER_MB,
  KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES,
  KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
} from '@/lib/constants'

interface UploadDocumentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBaseId: string
  onSuccess: () => void
}

export function UploadDocumentDialog({
  open,
  onOpenChange,
  knowledgeBaseId,
  onSuccess,
}: UploadDocumentDialogProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const router = useRouter()
  
  const [files, setFiles] = React.useState<File[]>([])
  const [maxUploadSizeMb, setMaxUploadSizeMb] = React.useState(
    KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB
  )
  const [isUploading, setIsUploading] = React.useState(false)
  const [uploadProgress, setUploadProgress] = React.useState(0)
  const [isDragOver, setIsDragOver] = React.useState(false)
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const maxUploadSizeBytes = maxUploadSizeMb * BYTES_PER_MB
  const maxUploadSizeLabel = `${maxUploadSizeMb}MB`

  React.useEffect(() => {
    if (!open) return

    siteSettingsApi.getPublic()
      .then(settings => setMaxUploadSizeMb(settings.kb_document_max_upload_size_mb))
      .catch(() => setMaxUploadSizeMb(KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB))
  }, [open])

  // 重置状态
  React.useEffect(() => {
    if (!open) {
      setFiles([])
      setUploadProgress(0)
    }
  }, [open])
  
  // 验证文件
  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES.includes(ext)) {
      return t('unsupportedFileType', { type: ext })
    }
    if (file.size > maxUploadSizeBytes) {
      return t('fileTooLarge', { size: maxUploadSizeLabel })
    }
    return null
  }
  
  // 处理文件选择
  const handleFileSelect = (selectedFiles: FileList | null) => {
    if (!selectedFiles) return
    
    const newFiles: File[] = []
    const errors: string[] = []
    
    Array.from(selectedFiles).forEach(file => {
      const error = validateFile(file)
      if (error) {
        errors.push(`${file.name}: ${error}`)
      } else {
        newFiles.push(file)
      }
    })
    
    if (errors.length > 0) {
      toast.error(errors.join('\n'))
    }
    
    setFiles(prev => [...prev, ...newFiles])
  }
  
  // 拖放处理
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }
  
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }
  
  // 移除文件
  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }
  
  // 上传文件
  const handleUpload = async () => {
    if (files.length === 0) return

    const errors = files
      .map(file => {
        const error = validateFile(file)
        return error ? `${file.name}: ${error}` : null
      })
      .filter((error): error is string => error !== null)
    if (errors.length > 0) {
      toast.error(errors.join('\n'))
      return
    }

    setIsUploading(true)
    setUploadProgress(0)
    
    const uploadedDocs: Document[] = []
    let failCount = 0
    
    for (let i = 0; i < files.length; i++) {
      try {
        const doc = await knowledgeBasesApi.uploadDocument(knowledgeBaseId, files[i])
        uploadedDocs.push(doc)
      } catch {
        failCount++
      }
      setUploadProgress(((i + 1) / files.length) * 100)
    }
    
    setIsUploading(false)
    
    if (uploadedDocs.length > 0) {
      toast.success(t('uploadSuccess', { count: uploadedDocs.length }))
    }
    if (failCount > 0) {
      toast.error(t('uploadFailed', { count: failCount }))
    }
    
    if (uploadedDocs.length > 0) {
      onOpenChange(false)
      onSuccess()
      
      // 跳转到批量预览页面配置分段
      const docIds = uploadedDocs.map(doc => doc.id).join(',')
      router.push(`/knowledge-bases/${knowledgeBaseId}/documents/preview?docs=${docIds}`)
    }
  }
  
  // 格式化文件大小
  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{t('uploadDocument')}</DialogTitle>
          <DialogDescription>{t('uploadDocumentDescription')}</DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          {/* 拖放区域 */}
          <div
            className={`
              border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
              ${isDragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-muted-foreground/50'}
            `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-4" />
            <p className="text-sm text-muted-foreground mb-2">
              {t('dragDropHint')}
            </p>
            <p className="text-xs text-muted-foreground">
              {t('supportedFormats')}: PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, PPTX
            </p>
          </div>
          
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES.join(',')}
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files)}
          />
          
          {/* 文件列表 */}
          {files.length > 0 && (
            <div className="space-y-2 max-h-[200px] overflow-auto">
              {files.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-2 rounded-lg border bg-muted/50"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                    <span className="text-sm truncate">{file.name}</span>
                    <span className="text-xs text-muted-foreground flex-shrink-0">
                      ({formatSize(file.size)})
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 flex-shrink-0"
                    onClick={() => removeFile(index)}
                    disabled={isUploading}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          
          {/* 上传进度 */}
          {isUploading && (
            <div className="space-y-2">
              <Progress value={uploadProgress} />
              <p className="text-xs text-center text-muted-foreground">
                {t('uploading')} ({Math.round(uploadProgress)}%)
              </p>
            </div>
          )}
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isUploading}>
            {commonT('cancel')}
          </Button>
          <Button onClick={handleUpload} disabled={files.length === 0 || isUploading}>
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('uploading')}
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                {t('upload')} ({files.length})
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
