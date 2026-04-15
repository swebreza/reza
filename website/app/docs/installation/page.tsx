import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Installation' }

export default async function InstallationPage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, '## Installation', ['## Per-Project Setup', '## Integrations', '## Measured'])
  const perProject = extractSection(raw, 'Per-Project Setup', ['## Supported Languages', '## Configuration', '## Real-World'])
  const combined = `${section}\n\n${perProject}`
  const content = await renderMdx(combined)

  return (
    <DocPage
      title="Installation"
      description="Install reza via npm, pip, or run from source. Works on macOS, Linux, and Windows."
    >
      {content}
    </DocPage>
  )
}
