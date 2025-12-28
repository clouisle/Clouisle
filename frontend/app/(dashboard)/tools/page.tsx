import { Header } from '@/components/layout/header'
import { ToolsClient } from './_components'

export default function ToolsPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
        <ToolsClient />
      </div>
    </div>
  )
}
