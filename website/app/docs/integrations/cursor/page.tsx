import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Cursor Integration' }

export default async function CursorPage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, '### Cursor', ['### Kilocode', '### Aider', '### GitHub'])
  const content = await renderMdx(section)
  return (
    <DocPage title="Cursor" description="Copy .cursorrules into your project or globally. Cursor will prompt reza queries automatically at session start.">
      {content}
    </DocPage>
  )
}
