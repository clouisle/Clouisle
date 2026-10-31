"use client"

import {
  ArrowRight,
  CheckIcon,
  ChevronLeft,
  ChevronRightIcon,
  CircleMinus,
  CirclePlusIcon,
  Download,
  Ellipsis,
  FileDiff,
  LoaderCircle,
  MessageSquare,
  Moon,
  PanelLeft,
  RotateCw,
  Search,
  Upload,
  type LucideIcon,
} from "lucide-react"

/**
 * Extend UI registry components resolve icons through a multi-library
 * placeholder. Clouisle ships Lucide only, so this maps the Lucide names used
 * by the vendored viewers and ignores the other library props.
 */
const LUCIDE_ICONS = {
  ArrowRight,
  CheckIcon,
  ChevronLeft,
  ChevronRightIcon,
  CircleMinus,
  CirclePlusIcon,
  Download,
  Ellipsis,
  FileDiff,
  LoaderCircle,
  MessageSquare,
  Moon,
  PanelLeft,
  RotateCw,
  Search,
  Upload,
} satisfies Record<string, LucideIcon>

type LucideIconName = keyof typeof LUCIDE_ICONS

type IconPlaceholderProps = React.ComponentProps<"svg"> & {
  lucide: string
  tabler?: string
  hugeicons?: string
  phosphor?: string
  remixicon?: string
}

export function IconPlaceholder({
  lucide,
  tabler,
  hugeicons,
  phosphor,
  remixicon,
  ...props
}: IconPlaceholderProps) {
  // Other icon-library names are accepted for registry compatibility; Clouisle ships Lucide only.
  void [tabler, hugeicons, phosphor, remixicon]
  const Icon = LUCIDE_ICONS[lucide as LucideIconName]

  if (!Icon) {
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[IconPlaceholder] Unknown Lucide icon: ${lucide}`)
    }
    return null
  }

  return <Icon {...props} />
}
