import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

export const metadata: Metadata = { title: 'Quick Start' }

export default async function QuickStartPage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, 'Quick Start', ['Install as an AI CLI Skill', 'Integrations'])
  const content = await renderMdx(section)

  return (
    <DocPage
      title="Quick Start"
      description="Get reza running in your project in under 2 minutes."
      badge="2 min setup"
    >
      {content}

      <div className="mt-16 pt-8 border-t border-[#1e2730] not-prose">
        <Link href="/docs/integrations"
          className="group flex items-center justify-between p-5 rounded-xl border border-[#1e2730] hover:border-teal-DEFAULT/40 bg-[#0d1117] transition-colors max-w-sm">
          <div>
            <div className="text-xs text-teal-DEFAULT font-semibold mb-1">Next</div>
            <div className="font-syne font-600 text-white">Connect your AI tool</div>
            <div className="text-xs text-slate-500 mt-0.5">Claude, Cursor, Aider, and more</div>
          </div>
          <ArrowRight size={16} className="text-slate-600 group-hover:text-teal-DEFAULT transition-colors" />
        </Link>
      </div>
    </DocPage>
  )
}
