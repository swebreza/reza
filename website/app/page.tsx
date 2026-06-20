'use client'

import Link from 'next/link'
import Image from 'next/image'
import { useState } from 'react'
import { ArrowRight, Check, Copy, Database, Github, Search, ShieldCheck, TerminalSquare } from 'lucide-react'
import Navbar from '@/components/Navbar'
import { ToolLogo, type ToolKey } from '@/components/ToolLogo'

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1600)
      }}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-400 hover:text-white hover:bg-white/5"
      aria-label="Copy command"
    >
      {copied ? <Check size={15} className="text-teal-DEFAULT" /> : <Copy size={15} />}
    </button>
  )
}

function Command({ value }: { value: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2.5 font-mono text-sm">
      <span className="text-teal-DEFAULT">$</span>
      <span className="min-w-0 flex-1 truncate text-slate-200">{value}</span>
      <CopyButton text={value} />
    </div>
  )
}

const integrations: Array<{ name: string; href: string; icon: ToolKey; status: string }> = [
  { name: 'Codex', href: '/docs/integrations/codex', icon: 'codex', status: 'local rollout sync' },
  { name: 'Cursor', href: '/docs/integrations/cursor', icon: 'cursor', status: 'agent transcript sync' },
  { name: 'Claude Code', href: '/docs/integrations/claude-code', icon: 'claude', status: 'hook and JSONL flow' },
  { name: 'Aider', href: '/docs/integrations/aider', icon: 'aider', status: 'history file sync' },
  { name: 'VS Code', href: '/docs/vscode-extension', icon: 'vscode', status: 'extension surface' },
  { name: 'Copilot', href: '/docs/integrations/copilot', icon: 'copilot', status: 'drop-zone fallback' },
  { name: 'Continue', href: '/docs/integrations/continue', icon: 'continue', status: 'export fallback' },
  { name: 'Kilocode', href: '/docs/integrations/kilocode', icon: 'kilocode', status: 'rules and drops' },
]

const planes = [
  { icon: Database, title: 'Capture', text: 'Adapters import local transcripts, handoffs, and history files without network sniffing.' },
  { icon: Search, title: 'Retrieve', text: 'Search turns, files, sessions, and threads with source-backed snippets.' },
  { icon: ShieldCheck, title: 'Govern', text: 'Local SQLite, redaction before indexing, exclusions, and audit-friendly source metadata.' },
]

const checks = [
  ['Project DB', '.reza/context.db stores files, sessions, turns, FTS, sources, checkpoints, and threads.'],
  ['Global registry', '~/.reza/registry.db routes cross-project status, handoff, and search.'],
  ['Always-on mode', 'reza watch polls adapters, ingests .reza/handoffs/, and reports adapter failures.'],
  ['Agent access', 'Any editor can call reza context current, reza session search, or reza global search.'],
]

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-white">
      <Navbar />

      <main className="pt-16">
        <section className="border-b border-[var(--border)] px-6 py-16 md:py-20">
          <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
            <div>
              <Link
                href="/docs/changelog"
                className="mb-6 inline-flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-teal-DEFAULT/50 hover:text-white"
              >
                <TerminalSquare size={14} className="text-teal-DEFAULT" />
                v0.5.0 local transcript memory
              </Link>

              <div className="mb-6 flex items-center gap-4">
                <Image src="/logo.png" alt="reza" width={56} height={56} priority className="rounded-lg" />
                <h1 className="font-sans text-5xl font-extrabold tracking-normal md:text-6xl">reza</h1>
              </div>

              <h2 className="max-w-3xl text-3xl font-bold leading-tight tracking-normal text-white md:text-5xl">
                Local-first memory for every AI coding agent on this PC.
              </h2>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-400">
                Capture project context, chat turns, handoffs, and cross-tool threads into searchable SQLite so Codex,
                Claude, Cursor, VS Code, Aider, and future tools can retrieve the same working context.
              </p>

              <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-2">
                <Command value="pip install reza" />
                <Command value="reza install-hooks" />
                <Command value="reza sync-all" />
                <Command value="reza context current --budget 8000" />
              </div>

              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  href="/docs/quick-start"
                  className="inline-flex items-center gap-2 rounded-lg bg-teal-DEFAULT px-5 py-3 text-sm font-bold text-slate-950 hover:bg-teal-300"
                >
                  Quick Start
                  <ArrowRight size={16} />
                </Link>
                <a
                  href="https://github.com/swebreza/reza"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-5 py-3 text-sm font-bold text-slate-300 hover:border-teal-DEFAULT/50 hover:text-white"
                >
                  <Github size={16} />
                  GitHub
                </a>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Local status model</p>
                <h3 className="mt-1 text-xl font-bold text-white">One memory layer, many agents</h3>
                </div>
                <Database size={22} className="text-teal-DEFAULT" />
              </div>
              <div className="space-y-3">
                {checks.map(([name, text]) => (
                  <div key={name} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
                    <div className="text-sm font-bold text-white">{name}</div>
                    <p className="mt-1 text-sm leading-6 text-slate-400">{text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-[var(--border)] px-6 py-14">
          <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-3">
            {planes.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
                <Icon size={20} className="text-teal-DEFAULT" />
                <h3 className="mt-4 text-lg font-bold text-white">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-b border-[var(--border)] px-6 py-14">
          <div className="mx-auto max-w-6xl">
            <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-teal-DEFAULT">Integrations</p>
                <h2 className="mt-2 text-3xl font-bold tracking-normal text-white">Coding agent access</h2>
              </div>
              <Link href="/docs/integrations" className="inline-flex items-center gap-2 text-sm font-bold text-teal-DEFAULT hover:text-teal-300">
                View setup guides
                <ArrowRight size={15} />
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {integrations.map((tool) => (
                <Link
                  key={tool.name}
                  href={tool.href}
                  className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4 hover:border-teal-DEFAULT/50"
                >
                  <span className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)]">
                    <ToolLogo tool={tool.icon} />
                  </span>
                  <div className="text-sm font-bold text-white">{tool.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{tool.status}</div>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 py-14">
          <div className="mx-auto max-w-6xl">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
              <h2 className="text-2xl font-bold text-white">Fast retrieval commands</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                These are the commands other tools should call at session start or when they need prior context.
              </p>
              <div className="mt-5 grid gap-3 lg:grid-cols-2">
                <Command value={'reza session search "auth middleware" --json'} />
                <Command value="reza session handoff --thread thread-abc --budget 8000" />
                <Command value="reza context pack --files src/auth.py tests/test_auth.py --budget 6000" />
                <Command value={'reza global search "stripe webhook"'} />
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--border)] px-6 py-8">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Image src="/logo.png" alt="reza" width={28} height={28} className="rounded-md" />
            <span className="font-bold text-white">reza</span>
            <span>MIT License</span>
          </div>
          <div className="flex flex-wrap gap-5">
            <Link href="/docs" className="hover:text-white">Docs</Link>
            <Link href="/docs/changelog" className="hover:text-white">Changelog</Link>
            <a href="https://github.com/swebreza/reza" target="_blank" rel="noopener noreferrer" className="hover:text-white">
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
