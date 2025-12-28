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
import { cn } from '@/lib/utils';

export interface ChatInputFile {
  id: string;
  name: string;
  size: number;
  type: string;
  file: File;
  previewUrl?: string;
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
  allowAttachments?: boolean;
  acceptedFileTypes?: string;
  maxFiles?: number;
  className?: string;
  minRows?: number;
  maxRows?: number;
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
  acceptedFileTypes = 'image/*,.pdf,.doc,.docx,.txt,.md',
  maxFiles = 5,
  className,
}: ChatInputProps) {
  const t = useTranslations('chat.input');
  const [internalValue, setInternalValue] = useState('');
  const [files, setFiles] = useState<ChatInputFile[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Support both controlled and uncontrolled mode
  const value = controlledValue ?? internalValue;
  const onChange = onControlledChange ?? setInternalValue;

  // Check if input is multiline (has newlines or is long enough to wrap)
  const isMultiline = value.includes('\n') || value.length > 60;

  const handleSubmit = useCallback(() => {
    const trimmedValue = value.trim();
    if (!trimmedValue && files.length === 0) return;
    if (disabled || isLoading) return;

    onSubmit?.(trimmedValue, files.length > 0 ? files : undefined);
    onChange('');
    setFiles([]);

    // Clean up file preview URLs
    files.forEach((f) => {
      if (f.previewUrl) {
        URL.revokeObjectURL(f.previewUrl);
      }
    });
  }, [value, files, disabled, isLoading, onSubmit, onChange]);

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
      const filesToAdd = selectedFiles.slice(0, remainingSlots);

      const newFiles: ChatInputFile[] = filesToAdd.map((file) => ({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        name: file.name,
        size: file.size,
        type: file.type,
        file,
        previewUrl: file.type.startsWith('image/')
          ? URL.createObjectURL(file)
          : undefined,
      }));

      setFiles((prev) => [...prev, ...newFiles]);

      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [files.length, maxFiles]
  );

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => {
      const file = prev.find((f) => f.id === fileId);
      if (file?.previewUrl) {
        URL.revokeObjectURL(file.previewUrl);
      }
      return prev.filter((f) => f.id !== fileId);
    });
  }, []);

  // Handle paste event for images
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!allowAttachments) return;

      const items = e.clipboardData?.items;
      if (!items) return;

      const imageFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) {
            imageFiles.push(file);
          }
        }
      }

      if (imageFiles.length === 0) return;

      // Prevent default paste behavior for images
      e.preventDefault();

      const remainingSlots = maxFiles - files.length;
      const filesToAdd = imageFiles.slice(0, remainingSlots);

      const newFiles: ChatInputFile[] = filesToAdd.map((file, index) => ({
        id: `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 9)}`,
        name: file.name || `pasted-image-${Date.now()}.png`,
        size: file.size,
        type: file.type,
        file,
        previewUrl: URL.createObjectURL(file),
      }));

      setFiles((prev) => [...prev, ...newFiles]);
    },
    [allowAttachments, files.length, maxFiles]
  );

  const canSubmit = (value.trim().length > 0 || files.length > 0) && !disabled && !isLoading;
  const showStop = isStreaming && onStop;

  return (
    <div className={cn('relative mx-auto max-w-3xl px-4', className)}>
      {/* File Attachments Preview */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {files.map((file) => (
            <FilePreview key={file.id} file={file} onRemove={removeFile} />
          ))}
        </div>
      )}

      {/* Input Area - OpenAI Style */}
      <div className={cn(
        'flex items-end gap-1 border bg-background shadow-sm pl-1 pr-1.5 py-1',
        isMultiline ? 'rounded-2xl' : 'rounded-full'
      )}>
        {/* Attachment Button */}
        {allowAttachments && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept={acceptedFileTypes}
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
            rows={1}
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

function FilePreview({ file, onRemove }: FilePreviewProps) {
  const isImage = file.type.startsWith('image/');

  return (
    <div className="relative group">
      {isImage && file.previewUrl ? (
        <div className="w-16 h-16 rounded-lg overflow-hidden border">
          <img
            src={file.previewUrl}
            alt={file.name}
            className="w-full h-full object-cover"
          />
        </div>
      ) : (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-muted/50">
          <FileIcon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm truncate max-w-30">{file.name}</span>
        </div>
      )}

      {/* Remove Button */}
      <button
        type="button"
        onClick={() => onRemove(file.id)}
        className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
