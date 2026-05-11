'use client';

import { useState, useRef, useCallback, KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Plus,
  StopCircle,
  Loader2,
  X,
  FileIcon,
  ArrowUp,
} from 'lucide-react';
import { GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES } from '@/lib/constants';
import { cn } from '@/lib/utils';

export interface ChatInputFile {
  id: string;
  name: string;
  size: number;
  type: string;
  file: File;
  previewUrl?: string;
  /** Whether this is a document file (for file upload) vs image (for vision) */
  isDocument?: boolean;
  /** Upload progress (0-100), undefined if not uploading */
  uploadProgress?: number;
  /** Whether the file is currently being uploaded */
  isUploading?: boolean;
}

export interface FileUploadConfig {
  max_file_size: number;  // bytes
  max_files: number;
  max_content_length: number;  // characters
  truncate_strategy: 'end' | 'start' | 'middle';
  allowed_extensions: string[];
}

interface ChatInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onSubmit?: (message: string, files?: ChatInputFile[]) => void;
  onStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  isStreaming?: boolean;
  /** Enable image attachments (vision) */
  allowAttachments?: boolean;
  /** Enable document file upload */
  enableFileUpload?: boolean;
  /** Document file upload configuration */
  fileUploadConfig?: FileUploadConfig | null;
  acceptedFileTypes?: string;
  maxFiles?: number;
  className?: string;
  minRows?: number;
  maxRows?: number;
  /** Whether files are currently being uploaded */
  isUploading?: boolean;
  /** External files state (for upload progress tracking) */
  files?: ChatInputFile[];
  /** Callback to update files (for upload progress tracking) */
  onFilesChange?: (files: ChatInputFile[]) => void;
}

// Document extensions supported by file upload
const DOCUMENT_EXTENSIONS = [
  '.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls',
  '.txt', '.md', '.csv', '.json', '.html'
];

// MIME types for document files (used in file input accept attribute)
const DOCUMENT_MIME_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/json',
  'text/html'
];

// Check if a file is a document (for file upload) vs image (for vision)
function isDocumentFile(file: File): boolean {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();
  return DOCUMENT_EXTENSIONS.includes(ext);
}

export function ChatInput({
  value: controlledValue,
  onChange: onControlledChange,
  onSubmit,
  onStop,
  placeholder,
  disabled = false,
  isLoading = false,
  isStreaming = false,
  allowAttachments = true,
  enableFileUpload = false,
  fileUploadConfig = null,
  acceptedFileTypes = 'image/*,.pdf,.doc,.docx,.txt,.md',
  maxFiles = 5,
  className,
  isUploading = false,
  files: controlledFiles,
  onFilesChange,
}: ChatInputProps) {
  const t = useTranslations('chat.input');
  const [internalValue, setInternalValue] = useState('');
  const [internalFiles, setInternalFiles] = useState<ChatInputFile[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  // Support both controlled and uncontrolled mode
  const value = controlledValue ?? internalValue;
  const onChange = onControlledChange ?? setInternalValue;
  
  // Support both controlled and uncontrolled files
  const files = controlledFiles ?? internalFiles;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const setFiles = onFilesChange ?? setInternalFiles;

  const documentMaxFileSize = fileUploadConfig?.max_file_size || GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES;
  const validateFileSize = useCallback((file: File) => {
    const maxFileSize = isDocumentFile(file) ? documentMaxFileSize : GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES;
    if (file.size <= maxFileSize) return true;
    const maxFileSizeMb = Math.round(maxFileSize / 1024 / 1024);
    setFileError(t('fileTooLarge', { maxSize: maxFileSizeMb }));
    return false;
  }, [documentMaxFileSize, t]);

  // Check if input is multiline (has newlines or is long enough to wrap)
  const isMultiline = value.includes('\n') || value.length > 60;

  const handleSubmit = useCallback(() => {
    const trimmedValue = value.trim();
    if (!trimmedValue && files.length === 0) return;
    if (disabled || isLoading || isUploading) return;

    onSubmit?.(trimmedValue, files.length > 0 ? files : undefined);
    onChange('');
    
    // Clear files
    if (onFilesChange) {
      onFilesChange([]);
    } else {
      setInternalFiles([]);
    }

    // Clean up file preview URLs
    files.forEach((f) => {
      if (f.previewUrl) {
        URL.revokeObjectURL(f.previewUrl);
      }
    });
  }, [value, files, disabled, isLoading, isUploading, onSubmit, onChange, onFilesChange]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Ignore Enter during IME composition (e.g., Chinese input)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // IME composition handlers
  const handleCompositionStart = () => setIsComposing(true);
  const handleCompositionEnd = () => setIsComposing(false);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = Array.from(e.target.files || []);
      if (selectedFiles.length === 0) return;

      const remainingSlots = maxFiles - files.length;
      const filesToAdd = selectedFiles.slice(0, remainingSlots).filter(validateFileSize);
      if (filesToAdd.length === 0) return;
      setFileError(null);

      const newFiles: ChatInputFile[] = filesToAdd.map((file) => ({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        name: file.name,
        size: file.size,
        type: file.type,
        file,
        previewUrl: file.type.startsWith('image/')
          ? URL.createObjectURL(file)
          : undefined,
        isDocument: isDocumentFile(file),
      }));

      if (onFilesChange) {
        onFilesChange([...files, ...newFiles]);
      } else {
        setInternalFiles((prev) => [...prev, ...newFiles]);
      }

      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [files, maxFiles, onFilesChange, validateFileSize]
  );

  const removeFile = useCallback((fileId: string) => {
    const fileToRemove = files.find((f) => f.id === fileId);
    if (fileToRemove?.previewUrl) {
      URL.revokeObjectURL(fileToRemove.previewUrl);
    }
    
    if (onFilesChange) {
      onFilesChange(files.filter((f) => f.id !== fileId));
    } else {
      setInternalFiles((prev) => prev.filter((f) => f.id !== fileId));
    }
  }, [files, onFilesChange]);

  // Handle paste event for images and files
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      // Check if any attachment feature is enabled
      if (!allowAttachments && !enableFileUpload) return;

      const items = e.clipboardData?.items;
      if (!items) return;

      const pastedFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind !== 'file') continue;
        
        const file = item.getAsFile();
        if (!file) continue;
        
        const isImage = file.type.startsWith('image/');
        const isDocument = isDocumentFile(file);
        
        // Handle images if vision is enabled (and not marked as document)
        if (isImage && allowAttachments && !isDocument) {
          pastedFiles.push(file);
        }
        // Handle document files if file upload is enabled
        else if (isDocument && enableFileUpload) {
          pastedFiles.push(file);
        }
      }

      if (pastedFiles.length === 0) return;

      // Prevent default paste behavior for files
      e.preventDefault();

      const remainingSlots = maxFiles - files.length;
      const filesToAdd = pastedFiles.slice(0, remainingSlots).filter(validateFileSize);
      if (filesToAdd.length === 0) return;
      setFileError(null);

      const newFiles: ChatInputFile[] = filesToAdd.map((file, index) => ({
        id: `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 9)}`,
        name: file.name || `pasted-image-${Date.now()}.png`,
        size: file.size,
        type: file.type,
        file,
        previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
        isDocument: isDocumentFile(file),
      }));

      if (onFilesChange) {
        onFilesChange([...files, ...newFiles]);
      } else {
        setInternalFiles((prev) => [...prev, ...newFiles]);
      }
    },
    [allowAttachments, enableFileUpload, files, maxFiles, onFilesChange, validateFileSize]
  );

  // Handle drag and drop
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!allowAttachments && !enableFileUpload) return;
    setIsDragging(true);
  }, [allowAttachments, enableFileUpload]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set dragging to false if we're leaving the drop zone entirely
    if (dropZoneRef.current && !dropZoneRef.current.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (!allowAttachments && !enableFileUpload) return;

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length === 0) return;

    const validFiles: File[] = [];
    for (const file of droppedFiles) {
      const isImage = file.type.startsWith('image/');
      const isDocument = isDocumentFile(file);

      // Accept images if vision is enabled
      if (isImage && allowAttachments && !isDocument) {
        validFiles.push(file);
      }
      // Accept documents if file upload is enabled
      else if (isDocument && enableFileUpload) {
        validFiles.push(file);
      }
    }

    if (validFiles.length === 0) return;

    const remainingSlots = maxFiles - files.length;
    const filesToAdd = validFiles.slice(0, remainingSlots).filter(validateFileSize);
    if (filesToAdd.length === 0) return;
    setFileError(null);

    const newFiles: ChatInputFile[] = filesToAdd.map((file, index) => ({
      id: `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 9)}`,
      name: file.name,
      size: file.size,
      type: file.type,
      file,
      previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
      isDocument: isDocumentFile(file),
    }));

    if (onFilesChange) {
      onFilesChange([...files, ...newFiles]);
    } else {
      setInternalFiles((prev) => [...prev, ...newFiles]);
    }
  }, [allowAttachments, enableFileUpload, files, maxFiles, onFilesChange, validateFileSize]);

  const canSubmit = (value.trim().length > 0 || files.length > 0) && !disabled && !isLoading && !isUploading;
  const showStop = isStreaming && onStop;
  
  // Show attachment button if either vision or file upload is enabled
  const showAttachments = allowAttachments || enableFileUpload;
  
  // Build accepted file types based on enabled features
  const buildAcceptedTypes = () => {
    const types: string[] = [];
    if (allowAttachments) {
      types.push('image/*');
    }
    if (enableFileUpload) {
      // Use both extensions and MIME types for better browser compatibility
      const extensions = fileUploadConfig?.allowed_extensions || DOCUMENT_EXTENSIONS;
      types.push(...extensions);
      types.push(...DOCUMENT_MIME_TYPES);
    }
    return types.length > 0 ? types.join(',') : acceptedFileTypes;
  };
  const effectiveAcceptedTypes = buildAcceptedTypes();

  // Separate image and document files for different display styles
  // Images: has previewUrl and is image type (not marked as document)
  const imageFiles = files.filter(f => f.previewUrl && f.type.startsWith('image/') && !f.isDocument);
  // Documents: everything else (no preview, or marked as document, or non-image type)
  const documentFiles = files.filter(f => !f.previewUrl || f.isDocument || !f.type.startsWith('image/'));

  return (
    <div 
      ref={dropZoneRef}
      className={cn('relative mx-auto max-w-3xl px-4', className)}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && showAttachments && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-primary bg-primary/5 backdrop-blur-sm">
          <p className="text-sm font-medium text-primary">{t('dropFiles')}</p>
        </div>
      )}

      {/* File Attachments Preview */}
      {files.length > 0 && (
        <div className="mb-2 space-y-1.5">
          {/* Image Previews - Grid layout */}
          {imageFiles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {imageFiles.map((file) => (
                <ImagePreview key={file.id} file={file} onRemove={removeFile} />
              ))}
            </div>
          )}
          {/* Document Previews - Compact list */}
          {documentFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {documentFiles.map((file) => (
                <DocumentPreview key={file.id} file={file} onRemove={removeFile} />
              ))}
            </div>
          )}
        </div>
      )}
      {fileError && (
        <p className="mb-2 text-xs text-destructive">{fileError}</p>
      )}

      {/* Input Area - OpenAI Style */}
      <div className={cn(
        'flex items-end gap-1 border bg-background shadow-sm pl-1 pr-1.5 py-1',
        isMultiline ? 'rounded-2xl' : 'rounded-full',
        isDragging && 'opacity-50'
      )}>
        {/* Attachment Button */}
        {showAttachments && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept={effectiveAcceptedTypes}
              multiple
              className="hidden"
              onChange={handleFileSelect}
              disabled={disabled || files.length >= maxFiles}
            />
            <Tooltip>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    className={cn(
                      'flex h-9 w-9 items-center justify-center rounded-full hover:bg-muted transition-colors',
                      (disabled || files.length >= maxFiles) && 'opacity-50 cursor-not-allowed'
                    )}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={disabled || files.length >= maxFiles}
                  >
                    <Plus className="h-5 w-5" />
                  </button>
                }
              />
              <TooltipContent>
                {files.length >= maxFiles
                  ? t('maxFilesReached', { max: maxFiles })
                  : t('attachFile')}
              </TooltipContent>
            </Tooltip>
          </>
        )}

        {/* Text Input */}
        <div className="flex-1 min-w-0">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            onCompositionStart={handleCompositionStart}
            onCompositionEnd={handleCompositionEnd}
            placeholder={placeholder ?? t('placeholder')}
            disabled={disabled}
            className={cn(
              'min-h-9 max-h-32 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 py-2 px-2',
              'placeholder:text-muted-foreground/60'
            )}
          />
        </div>

        {/* Submit/Stop Button */}
        {showStop ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-foreground text-background hover:bg-foreground/90 transition-colors"
                  onClick={onStop}
                >
                  <StopCircle className="h-5 w-5" />
                </button>
              }
            />
            <TooltipContent>{t('stop')}</TooltipContent>
          </Tooltip>
        ) : (
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  className={cn(
                    'flex h-9 w-9 items-center justify-center rounded-full transition-colors',
                    canSubmit
                      ? 'bg-foreground text-background hover:bg-foreground/90'
                      : 'bg-muted text-muted-foreground cursor-not-allowed'
                  )}
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ArrowUp className="h-5 w-5" />
                  )}
                </button>
              }
            />
            <TooltipContent>{t('send')}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

interface FilePreviewProps {
  file: ChatInputFile;
  onRemove: (id: string) => void;
}

// Image preview with thumbnail
function ImagePreview({ file, onRemove }: FilePreviewProps) {
  const isUploading = file.isUploading;
  const progress = file.uploadProgress ?? 0;

  return (
    <div className="relative group">
      <div className="w-16 h-16 rounded-lg overflow-hidden border relative">
        <img
          src={file.previewUrl}
          alt={file.name}
          className={cn(
            "w-full h-full object-cover transition-opacity",
            isUploading && "opacity-50"
          )}
        />
        {/* Upload Progress Overlay */}
        {isUploading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/30">
            <div className="w-10 h-10 relative">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle
                  cx="18"
                  cy="18"
                  r="15"
                  fill="none"
                  className="stroke-muted-foreground/30"
                  strokeWidth="3"
                />
                <circle
                  cx="18"
                  cy="18"
                  r="15"
                  fill="none"
                  className="stroke-primary"
                  strokeWidth="3"
                  strokeDasharray={`${progress * 0.94} 100`}
                  strokeLinecap="round"
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-xs font-medium">
                {Math.round(progress)}%
              </span>
            </div>
          </div>
        )}
      </div>
      {/* Remove Button */}
      {!isUploading && (
        <button
          type="button"
          onClick={() => onRemove(file.id)}
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

// Compact document preview
function DocumentPreview({ file, onRemove }: FilePreviewProps) {
  const isUploading = file.isUploading;
  const progress = file.uploadProgress ?? 0;

  // Format file size
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  return (
    <div className="relative group inline-flex items-center gap-1.5 px-2 py-1 rounded-md border bg-muted/50 text-xs overflow-hidden">
      {/* Progress background */}
      {isUploading && (
        <div 
          className="absolute left-0 top-0 h-full bg-primary/15 transition-all duration-200"
          style={{ width: `${progress}%` }}
        />
      )}
      <FileIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0 z-10" />
      <span className="truncate max-w-24 z-10">{file.name}</span>
      <span className="text-muted-foreground z-10">
        {isUploading ? `${Math.round(progress)}%` : formatSize(file.size)}
      </span>
      {/* Remove Button */}
      {!isUploading && (
        <button
          type="button"
          onClick={() => onRemove(file.id)}
          className="ml-0.5 p-0.5 rounded hover:bg-muted z-10"
        >
          <X className="h-3 w-3 text-muted-foreground" />
        </button>
      )}
    </div>
  );
}
