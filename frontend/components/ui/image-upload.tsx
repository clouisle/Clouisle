'use client'

import * as React from 'react'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { X, Loader2, ImageIcon } from 'lucide-react'
import { uploadApi } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ImageUploadProps {
  value?: string
  onChange?: (url: string) => void
  category?: string
  className?: string
  placeholder?: React.ReactNode
  disabled?: boolean
  /** 图片预览尺寸 */
  previewSize?: 'sm' | 'md' | 'lg'
  /** 接受的文件类型 */
  accept?: string
  /** 是否在更换/删除时自动清理旧文件 */
  autoCleanup?: boolean
}

/**
 * 判断 URL 是否是我们上传的文件
 */
function isUploadedFile(url: string): boolean {
  return url.includes('/api/v1/upload/files/')
}

export function ImageUpload({
  value,
  onChange,
  category = 'general',
  className,
  placeholder,
  disabled = false,
  previewSize = 'md',
  accept = 'image/*',
  autoCleanup = true,
}: ImageUploadProps) {
  const t = useTranslations('common')
  const [uploading, setUploading] = React.useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const sizeClasses = {
    sm: 'h-16 w-16',
    md: 'h-24 w-24',
    lg: 'h-32 w-32',
  }

  /**
   * 尝试删除旧文件（静默失败）
   */
  const tryDeleteOldFile = async (oldUrl: string) => {
    if (!oldUrl || !autoCleanup || !isUploadedFile(oldUrl)) return
    try {
      await uploadApi.deleteFile(oldUrl)
    } catch (error) {
      // 静默失败，旧文件可能已被删除或不存在
      console.warn('Failed to delete old file:', error)
    }
  }

  const handleClick = () => {
    if (!disabled && !uploading) {
      inputRef.current?.click()
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      toast.error(t('invalidFileType'))
      return
    }

    // 验证文件大小（10MB）
    if (file.size > 10 * 1024 * 1024) {
      toast.error(t('fileTooLarge'))
      return
    }

    const oldValue = value
    setUploading(true)
    try {
      const result = await uploadApi.uploadImage(file, category)
      const fullUrl = uploadApi.getFullUrl(result.url)
      onChange?.(fullUrl)
      toast.success(t('uploadSuccess'))
      
      // 上传成功后删除旧文件
      if (oldValue) {
        await tryDeleteOldFile(oldValue)
      }
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setUploading(false)
      // 重置 input 以允许重新选择相同文件
      if (inputRef.current) {
        inputRef.current.value = ''
      }
    }
  }

  const handleRemove = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const oldValue = value
    onChange?.('')
    
    // 删除文件
    if (oldValue) {
      await tryDeleteOldFile(oldValue)
    }
  }

  return (
    <div className={cn('relative inline-block', className)}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleFileChange}
        className="hidden"
        disabled={disabled || uploading}
      />
      
      <div
        onClick={handleClick}
        className={cn(
          sizeClasses[previewSize],
          'relative flex items-center justify-center rounded-lg border-2 border-dashed cursor-pointer transition-colors overflow-hidden',
          disabled ? 'cursor-not-allowed opacity-50' : 'hover:border-primary/50 hover:bg-muted/50',
          value ? 'border-transparent' : 'border-muted-foreground/25 bg-muted/50'
        )}
      >
        {uploading ? (
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        ) : value ? (
          <Image
            src={value}
            alt="Uploaded"
            fill
            className="object-cover"
            unoptimized
          />
        ) : (
          placeholder || <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
        )}
      </div>
      
      {/* 删除按钮放到外层，避免被 overflow-hidden 裁切 */}
      {value && !disabled && !uploading && (
        <button
          onClick={handleRemove}
          className="absolute -right-1.5 -top-1.5 rounded-full bg-destructive p-1 text-destructive-foreground shadow-sm hover:bg-destructive/90 z-10 cursor-pointer"
        >
          <X className="h-3 w-3 text-white" />
        </button>
      )}
    </div>
  )
}
