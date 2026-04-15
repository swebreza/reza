import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Codeium / Windsurf Integration' }

export default async function CodeiumPage() {
  const raw = readContent('integrations/codeium.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="Codeium / Windsurf" description="Generate the context file with reza export, then open it in the editor. Codeium reads all open files automatically.">
      {content}
    </DocPage>
  )
}
