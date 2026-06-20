import { Metadata } from 'next'
import type { ReactNode } from 'react'
import DocPage from '@/components/DocPage'

export const metadata: Metadata = { title: 'VS Code Extension' }

const STATES = [
  { state: 'Locked', color: '#ef4444', desc: 'File is actively locked by the current AI session.' },
  { state: 'Hot', color: '#f97316', desc: 'File was modified in the current session.' },
  { state: 'Blast', color: '#a78bfa', desc: 'File is likely impacted by currently active files.' },
  { state: 'Cold', color: '#4b5563', desc: 'No session activity.' },
]

const COMMANDS = [
  { cmd: 'Reza: Show Code Graph', desc: 'Open the interactive graph in a sidebar panel.' },
  { cmd: 'Reza: Show Blast Radius', desc: 'Compute impact radius of the currently open file.' },
  { cmd: 'Reza: Build / Refresh Graph', desc: 'Run reza graph build in the integrated terminal.' },
  { cmd: 'Reza: Refresh Graph View', desc: 'Re-query the graph without reopening the panel.' },
]

const SESSIONS_FEATURES = [
  <>Imported sessions list from Cursor, Codex, Claude, and manual drops.</>,
  <>Filter by source tool, highlight touched files, or isolate a subgraph.</>,
  <>Sync buttons run <code className="text-teal-DEFAULT text-xs">reza sync-cursor</code> and <code className="text-teal-DEFAULT text-xs">reza sync-codex</code>.</>,
  <>Pack runs <code className="text-teal-DEFAULT text-xs">reza session load {'<id>'} --copy</code> for handoff.</>,
]

function Heading({ children }: { children: ReactNode }) {
  return <h2 className="mb-4 text-2xl font-bold text-white">{children}</h2>
}

export default function VsCodeExtensionPage() {
  return (
    <DocPage
      title="VS Code Extension"
      description="Visualize Reza graph and session context directly inside VS Code."
      badge="New"
    >
      <section className="mb-10">
        <Heading>Installation</Heading>
        <p className="mb-4 text-slate-400">
          The extension lives in <code>extensions/reza-vscode/</code> in the Reza repository.
          Build and install it manually while it awaits Marketplace publishing.
        </p>
        <div className="space-y-2 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5 font-mono text-sm">
          <div><span className="text-slate-600"># Build the extension</span></div>
          <div><span className="text-teal-DEFAULT">cd</span> <span className="text-slate-300">extensions/reza-vscode</span></div>
          <div><span className="text-teal-DEFAULT">npm install</span></div>
          <div><span className="text-teal-DEFAULT">npm run build</span></div>
          <div className="pt-2"><span className="text-slate-600"># Package and install</span></div>
          <div><span className="text-teal-DEFAULT">npx vsce package</span></div>
          <div><span className="text-teal-DEFAULT">code --install-extension</span> <span className="text-slate-300">reza-vscode-0.3.0.vsix</span></div>
        </div>
      </section>

      <section className="mb-10">
        <Heading>Activation</Heading>
        <p className="text-slate-400">
          The extension activates automatically when a <code>.reza/context.db</code> file is detected in the workspace root.
        </p>
      </section>

      <section className="mb-10">
        <Heading>Commands</Heading>
        <div className="space-y-3">
          {COMMANDS.map((c) => (
            <div key={c.cmd} className="flex flex-col gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex-row sm:items-center">
              <code className="flex-shrink-0 font-mono text-sm text-teal-DEFAULT">{c.cmd}</code>
              <span className="text-sm text-slate-500 sm:ml-4">{c.desc}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-10">
        <Heading>Sessions</Heading>
        <p className="mb-4 text-slate-400">
          The graph sidebar includes a Sessions strip above the live session card. Imported chats can highlight files and nodes or narrow the graph to one session.
        </p>
        <ul className="space-y-2 text-sm text-slate-400">
          {SESSIONS_FEATURES.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-1 text-teal-DEFAULT">-</span>
              <span className="flex-1">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mb-10">
        <Heading>Graph View</Heading>
        <p className="mb-6 text-slate-400">
          The graph is a D3 v7 force-directed visualization of classes, functions, imports, calls, and inheritance.
        </p>

        <div className="mb-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
            <h3 className="mb-3 text-base font-semibold text-white">Node States</h3>
            <div className="space-y-2">
              {STATES.map((s) => (
                <div key={s.state} className="flex items-start gap-3">
                  <span className="mt-1.5 h-3 w-3 flex-shrink-0 rounded-full" style={{ background: s.color }} />
                  <div>
                    <span className="text-sm font-semibold text-white">{s.state}</span>
                    <span className="ml-2 text-xs text-slate-500">{s.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4">
            <h3 className="mb-3 text-base font-semibold text-white">Edge Types</h3>
            <div className="space-y-2 text-sm">
              {[
                { kind: 'CALLS', color: '#3b82f6' },
                { kind: 'IMPORTS_FROM', color: '#22c55e' },
                { kind: 'INHERITS', color: '#a78bfa' },
                { kind: 'TESTED_BY', color: '#f59e0b' },
                { kind: 'CONTAINS', color: '#4b5563' },
              ].map((e) => (
                <div key={e.kind} className="flex items-center gap-3">
                  <span className="h-0.5 w-5 flex-shrink-0 rounded" style={{ background: e.color }} />
                  <code className="text-xs" style={{ color: e.color }}>{e.kind}</code>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mb-10">
        <Heading>Live Updates</Heading>
        <p className="text-slate-400">
          The extension watches <code>.reza/context.db</code> for changes and falls back to a configurable poll interval, defaulting to 3 seconds.
        </p>
      </section>

      <section>
        <Heading>Configuration</Heading>
        <div className="overflow-hidden rounded-lg border border-[var(--border)] text-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
                <th className="px-4 py-3 text-left text-xs uppercase tracking-widest text-slate-400">Setting</th>
                <th className="px-4 py-3 text-left text-xs uppercase tracking-widest text-slate-400">Default</th>
                <th className="px-4 py-3 text-left text-xs uppercase tracking-widest text-slate-400">Description</th>
              </tr>
            </thead>
            <tbody>
              {[
                { key: 'reza.rezaPath', def: '"reza"', desc: 'Path to the Reza CLI executable' },
                { key: 'reza.nodeLimit', def: '800', desc: 'Max nodes to show, or 0 for no limit' },
                { key: 'reza.defaultNodeKinds', def: '"Class,Function,Test"', desc: 'Node kinds shown by default' },
                { key: 'reza.refreshIntervalMs', def: '3000', desc: 'Session poll interval in ms' },
              ].map((row) => (
                <tr key={row.key} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-4 py-3 font-mono text-xs text-teal-DEFAULT">{row.key}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{row.def}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{row.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </DocPage>
  )
}
