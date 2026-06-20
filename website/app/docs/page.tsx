import { Metadata } from 'next'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Introduction' }

export default async function DocsIntroPage() {
  const raw = readContent('README.md')
  const problemSection = extractSection(raw, 'The Problem', ['The Solution', 'Quick Start'])
  const solutionSection = extractSection(raw, 'The Solution', ['Quick Start', 'Install as'])
  const combined = `${problemSection}\n\n${solutionSection}`
  const content = await renderMdx(combined)

  return (
    <DocPage
      title="Introduction"
      description="reza is a local-first Universal LLM Context Database for coding agents."
    >
      {content}

      <div className="not-prose mt-16 grid gap-4 border-t border-[var(--border)] pt-8 sm:grid-cols-2">
        <Link
          href="/docs/quick-start"
          className="group flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5 transition-colors hover:border-teal-DEFAULT/40"
        >
          <div>
            <div className="mb-1 text-xs font-semibold text-teal-DEFAULT">Next</div>
            <div className="font-sans font-semibold text-white">Quick Start</div>
            <div className="mt-0.5 text-xs text-slate-500">Up and running in 2 minutes</div>
          </div>
          <ArrowRight size={16} className="text-slate-600 transition-colors group-hover:text-teal-DEFAULT" />
        </Link>
        <Link
          href="/docs/how-it-works"
          className="group flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5 transition-colors hover:border-teal-DEFAULT/40"
        >
          <div>
            <div className="mb-1 text-xs font-semibold text-slate-500">Concept</div>
            <div className="font-sans font-semibold text-white">How It Works</div>
            <div className="mt-0.5 text-xs text-slate-500">Database schema and sync mechanisms</div>
          </div>
          <ArrowRight size={16} className="text-slate-600 transition-colors group-hover:text-teal-DEFAULT" />
        </Link>
      </div>
    </DocPage>
  )
}
