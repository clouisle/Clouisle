'use client'

import { useTranslations } from 'next-intl'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox'
import { PRESET_TOOL_CATEGORIES, isPresetToolCategory, type ToolCategory } from '@/lib/api'

interface ToolCategoryInputProps {
  id?: string
  value: ToolCategory
  onChange: (value: ToolCategory) => void
  className?: string
  inputClassName?: string
}

export function ToolCategoryInput({
  id = 'category',
  value,
  onChange,
  className,
  inputClassName,
}: ToolCategoryInputProps) {
  const t = useTranslations('tools')
  const tCommon = useTranslations('common')
  const getCategoryLabel = (category: string) =>
    isPresetToolCategory(category) ? t(`categories.${category}`) : category
  const categories = isPresetToolCategory(value)
    ? PRESET_TOOL_CATEGORIES
    : [value, ...PRESET_TOOL_CATEGORIES]

  return (
    <div className={className}>
      <Combobox
        items={categories}
        value={value}
        inputValue={getCategoryLabel(value)}
        itemToStringLabel={getCategoryLabel}
        onValueChange={(nextValue) => {
          if (typeof nextValue === 'string') {
            onChange(nextValue)
          }
        }}
        onInputValueChange={(nextValue, eventDetails) => {
          if (eventDetails.reason === 'input-change') {
            onChange(nextValue)
          }
        }}
      >
        <ComboboxInput id={id} className={inputClassName} />
        <ComboboxContent>
          <ComboboxEmpty>{tCommon('noResults')}</ComboboxEmpty>
          <ComboboxList>
            {(category) => (
              <ComboboxItem key={category} value={category}>
                {getCategoryLabel(category)}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}
