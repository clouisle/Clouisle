import type { Block } from '@blocknote/core'

/** Future host-provided integrations; no remote backend is connected today. */
export interface ColslandEditorIntegrations {
  comments?: React.ComponentType<{ documentId: string; blocks: readonly Block[] }>
  databaseView?: React.ComponentType<{ documentId: string }>
  collaboration?: React.ComponentType<{ documentId: string }>
}

export const defaultEditorIntegrations: ColslandEditorIntegrations = {}
