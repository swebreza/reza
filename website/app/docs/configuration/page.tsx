import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Configuration' }

export default async function ConfigurationPage() {
  const raw = readContent('README.md')
  const config = extractSection(raw, '## Configuration', ['## Real-World', '## Contributing'])
  const langs = extractSection(raw, 'Supported Languages', ['## Configuration'])
  const content = await renderMdx(`${langs}\n\n${config}`)

  return (
    <DocPage
      title="Configuration"
      description="reza works with zero configuration. Advanced options for custom ignore patterns, git hooks, and more."
    >
      {content}
    </DocPage>
  )
}
