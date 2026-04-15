import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Parallel Agents' }

export default async function ParallelAgentsPage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, 'Parallel Agents', ['## Cross-Tool Threads', '## How It Works'])
  const content = await renderMdx(section)

  return (
    <DocPage
      title="Parallel Agents"
      description="Run Claude + Cursor simultaneously on the same repo. reza prevents silent overwrites with file locks and conflict detection."
    >
      {content}
    </DocPage>
  )
}
