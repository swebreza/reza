import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Sessions & Threads' }

export default async function SessionsPage() {
  const raw = readContent('README.md')
  const crossTool = extractSection(raw, 'Cross-Tool Threads', ['## How It Works', '## Installation'])
  const content = await renderMdx(crossTool)

  return (
    <DocPage
      title="Sessions & Threads"
      description="reza tracks work across tools, context limits, and time. Every AI session is linked into a unified thread."
    >
      {content}
    </DocPage>
  )
}
