import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Kilocode Integration' }

export default async function KilocodePage() {
  const raw = readContent('integrations/kilocode.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="Kilocode" description="Copy the reza rules file globally or per-project. Kilocode will load context on every session automatically.">
      {content}
    </DocPage>
  )
}
