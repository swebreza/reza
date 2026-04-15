import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'
import Link from 'next/link'

export const metadata: Metadata = { title: 'Integrations' }

const TOOLS = [
  { name: 'Claude Code', href: '/docs/integrations/claude-code', emoji: '🟠', color: '#e8501a', desc: 'Native skill + auto Stop hook — zero tokens', badge: 'Best integration' },
  { name: 'Cursor', href: '/docs/integrations/cursor', emoji: '🟣', color: '#9b59b6', desc: '.cursorrules auto-injects context at session start' },
  { name: 'Codex', href: '/docs/integrations/codex', emoji: '🔵', color: '#3b82f6', desc: 'System prompt injection via shell alias' },
  { name: 'Aider', href: '/docs/integrations/aider', emoji: '🟢', color: '#22c55e', desc: '--read flag or .aider.conf.yml for auto-context' },
  { name: 'Kilocode', href: '/docs/integrations/kilocode', emoji: '🟡', color: '#f59e0b', desc: 'Global rules file, activates on every project' },
  { name: 'GitHub Copilot', href: '/docs/integrations/copilot', emoji: '🔷', color: '#6366f1', desc: 'copilot-instructions.md + @file in Copilot Chat' },
  { name: 'Continue.dev', href: '/docs/integrations/continue', emoji: '🩵', color: '#06b6d4', desc: '@file reference or config.json auto-include' },
  { name: 'Codeium / Windsurf', href: '/docs/integrations/codeium', emoji: '💚', color: '#10b981', desc: 'Open context file in editor for Codeium to read' },
]

export default async function IntegrationsPage() {
  const raw = readContent('integrations/README.md')
  const content = await renderMdx(raw)

  return (
    <DocPage
      title="Integrations"
      description="reza works with every major AI coding tool. Choose your tool to get a step-by-step guide."
    >
      {/* Tool grid */}
      <div className="not-prose grid sm:grid-cols-2 gap-4 mb-12">
        {TOOLS.map((tool) => (
          <Link
            key={tool.href}
            href={tool.href}
            className="group relative p-5 rounded-xl border border-[#1e2730] hover:border-teal-DEFAULT/40 bg-[#0d1117] transition-all hover:-translate-y-0.5"
          >
            <div className="flex items-start gap-4">
              <span className="text-2xl">{tool.emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-syne font-600 text-white text-sm">{tool.name}</span>
                  {tool.badge && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-teal-DEFAULT/15 text-teal-DEFAULT font-medium">
                      {tool.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">{tool.desc}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Universal workflow from README */}
      {content}
    </DocPage>
  )
}
