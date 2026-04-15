import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'CLI Reference' }

export default async function CliReferencePage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, '## CLI Reference', ['## Integrations', '## Parallel Agents', '## Cross-Tool'])
  const content = await renderMdx(section)

  return (
    <DocPage
      title="CLI Reference"
      description="Complete reference for all reza commands — core, sessions, threads, exports, locks, and git hooks."
    >
      {content}
    </DocPage>
  )
}
