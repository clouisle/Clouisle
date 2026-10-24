import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'

import { RunInspector } from './_components/run-inspector'

export default async function ObservabilityRunDetailPage({
  params,
}: {
  params: Promise<{ source: string; runId: string }>
}) {
  const { source, runId } = await params

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <main className="flex-1 overflow-auto bg-muted/20 p-4 md:p-6">
          <div className="mx-auto max-w-[1600px]">
            <RunInspector source={source} runId={runId} />
          </div>
        </main>
      </div>
    </RoutePermissionGuard>
  )
}
