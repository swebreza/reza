import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'
import Link from 'next/link'
import { ToolLogo, type ToolKey } from '@/components/ToolLogo'

export const metadata: Metadata = { title: 'Integrations' }

const TOOLS = [
  { name: 'Claude Code', href: '/docs/integrations/claude-code', icon: 'claude' as ToolKey, desc: 'Native skill + auto Stop hook — zero tokens', badge: 'Best integration' },
  { name: 'Cursor', href: '/docs/integrations/cursor', icon: 'cursor' as ToolKey, desc: '.cursorrules auto-injects context at session start' },
  { name: 'Codex', href: '/docs/integrations/codex', icon: 'codex' as ToolKey, desc: 'System prompt injection via shell alias' },
  { name: 'Aider', href: '/docs/integrations/aider', icon: 'aider' as ToolKey, desc: '--read flag or .aider.conf.yml for auto-context' },
  { name: 'Kilocode', href: '/docs/integrations/kilocode', icon: 'kilocode' as ToolKey, desc: 'Global rules file, activates on every project' },
  { name: 'GitHub Copilot', href: '/docs/integrations/copilot', icon: 'copilot' as ToolKey, desc: 'copilot-instructions.md + @file in Copilot Chat' },
  { name: 'Continue.dev', href: '/docs/integrations/continue', icon: 'continue' as ToolKey, desc: '@file reference or config.json auto-include' },
  { name: 'Codeium / Windsurf', href: '/docs/integrations/codeium', icon: 'codeium' as ToolKey, desc: 'Open context file in editor for Codeium to read' },
  { name: 'VS Code Extension', href: '/docs/vscode-extension', icon: 'vscode' as ToolKey, desc: 'Interactive graph UI + sessions browser for scoped context' },
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
            className="group relative p-5 rounded-2xl border border-[#1e2730] hover:border-teal-DEFAULT/40 bg-[#0d1117] transition-all hover:-translate-y-0.5 hover:shadow-[0_16px_40px_-24px_rgba(16,185,129,0.55)]"
          >
            <div className="flex items-start gap-4">
              <span className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[#263141] bg-[#101720]">
                <ToolLogo tool={tool.icon} />
              </span>
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
