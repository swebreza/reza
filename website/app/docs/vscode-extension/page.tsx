import { Metadata } from 'next'
import DocPage from '@/components/DocPage'

export const metadata: Metadata = { title: 'VS Code Extension' }

const STATES = [
  { state: 'Locked', color: '#ff4c4c', desc: 'File is actively locked by the current AI session (pulsing red ring)' },
  { state: 'Hot', color: '#f97316', desc: 'File was modified in the current session (orange fill)' },
  { state: 'Blast', color: '#a78bfa', desc: 'File is in the blast radius of hot files — likely impacted' },
  { state: 'Cold', color: '#4b5563', desc: 'No session activity — dim gray' },
]

const COMMANDS = [
  { cmd: 'Reza: Show Code Graph', key: undefined, desc: 'Open the interactive force-directed graph in a sidebar panel' },
  { cmd: 'Reza: Show Blast Radius', key: undefined, desc: 'Compute impact radius of the currently open file' },
  { cmd: 'Reza: Build / Refresh Graph', key: undefined, desc: 'Run reza graph build in the integrated terminal' },
  { cmd: 'Reza: Refresh Graph View', key: undefined, desc: 'Re-query the graph without reopening the panel' },
]

const SESSIONS_FEATURES = [
  <>Imported sessions list — Cursor, Codex, Claude, manual (after <code className="text-teal-DEFAULT text-xs">reza sync-*</code>)</>,
  <>Filter by source tool; Highlight vs Subgraph only on the graph</>,
  <>Sync buttons run <code className="text-teal-DEFAULT text-xs">reza sync-cursor</code> / <code className="text-teal-DEFAULT text-xs">reza sync-codex</code> in a terminal</>,
  <>Pack runs <code className="text-teal-DEFAULT text-xs">reza session load {'<id>'}</code> with <code className="text-teal-DEFAULT text-xs">--copy</code> for handoff</>,
]

export default function VsCodeExtensionPage() {
  return (
    <DocPage
      title="VS Code Extension"
      description="Visualize your reza code graph directly inside VS Code. See which files are active, locked, or in the blast radius of the current AI session — in real time."
      badge="New"
    >
      {/* Install */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Installation</h2>
        <p className="text-slate-400 mb-4">
          The extension lives in <code>extensions/reza-vscode/</code> in the reza repository.
          Build and install it manually while it awaits Marketplace publishing.
        </p>
        <div className="bg-[#0d1117] border border-[#1e2730] rounded-xl p-5 font-mono text-sm space-y-2">
          <div><span className="text-slate-600"># Build the extension</span></div>
          <div><span className="text-teal-DEFAULT">cd</span> <span className="text-slate-300">extensions/reza-vscode</span></div>
          <div><span className="text-teal-DEFAULT">npm install</span></div>
          <div><span className="text-teal-DEFAULT">npm run build</span></div>
          <div className="pt-2"><span className="text-slate-600"># Package and install</span></div>
          <div><span className="text-teal-DEFAULT">npx vsce package</span></div>
          <div><span className="text-teal-DEFAULT">code --install-extension</span> <span className="text-slate-300">reza-vscode-0.3.0.vsix</span></div>
        </div>
        <p className="text-slate-500 text-sm mt-3">
          Requires the <strong className="text-white">reza CLI</strong> to be installed and <code>reza graph build</code> to have been run in your project.
        </p>
      </section>

      {/* Activation */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Activation</h2>
        <p className="text-slate-400">
          The extension activates automatically when a <code>.reza/context.db</code> file is detected in the workspace root.
          Zero overhead in projects without reza.
        </p>
      </section>

      {/* Commands */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-6">Commands</h2>
        <div className="space-y-3">
          {COMMANDS.map((c) => (
            <div key={c.cmd} className="flex flex-col sm:flex-row sm:items-center gap-2 p-4 rounded-xl bg-[#0d1117] border border-[#1e2730]">
              <code className="text-teal-DEFAULT text-sm font-mono flex-shrink-0">{c.cmd}</code>
              <span className="text-slate-500 text-sm sm:ml-4">{c.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Sessions browser */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Sessions (cross-tool)</h2>
        <p className="text-slate-400 mb-4">
          The graph sidebar includes a <strong className="text-white">Sessions</strong> strip above the live session card.
          After you run <code className="text-teal-DEFAULT text-xs">reza sync-cursor</code> or{' '}
          <code className="text-teal-DEFAULT text-xs">reza sync-codex</code> in a project, past chats appear here.
          Selecting a session either <em>highlights</em> the files and nodes it touched on the full graph, or shows a{' '}
          <em>subgraph only</em> — your choice via the mode toggle.
        </p>
        <ul className="space-y-2 text-slate-400 text-sm">
          {SESSIONS_FEATURES.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-1 text-teal-DEFAULT">→</span>
              <span className="flex-1">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Graph view */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Graph View</h2>
        <p className="text-slate-400 mb-6">
          The graph is a D3 v7 force-directed visualization of your codebase — nodes are classes and functions,
          edges are calls, imports, and inheritance. Everything is wired to your session state.
        </p>

        <div className="grid sm:grid-cols-2 gap-4 mb-8">
          <div>
            <h3 className="font-syne font-600 text-white text-base mb-3">Node States</h3>
            <div className="space-y-2">
              {STATES.map((s) => (
                <div key={s.state} className="flex items-start gap-3">
                  <span className="mt-1.5 w-3 h-3 rounded-full flex-shrink-0" style={{ background: s.color }} />
                  <div>
                    <span className="text-sm font-semibold text-white">{s.state}</span>
                    <span className="text-xs text-slate-500 ml-2">{s.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="font-syne font-600 text-white text-base mb-3">Edge Types</h3>
            <div className="space-y-2 text-sm">
              {[
                { kind: 'CALLS', color: '#3b82f6' },
                { kind: 'IMPORTS_FROM', color: '#22c55e' },
                { kind: 'INHERITS', color: '#a78bfa' },
                { kind: 'TESTED_BY', color: '#f59e0b' },
                { kind: 'CONTAINS', color: '#4b5563' },
              ].map((e) => (
                <div key={e.kind} className="flex items-center gap-3">
                  <span className="w-5 h-0.5 rounded flex-shrink-0" style={{ background: e.color }} />
                  <code className="text-xs" style={{ color: e.color }}>{e.kind}</code>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Interactivity */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Interactivity</h2>
        <ul className="space-y-3 text-slate-400">
          {[
            'Click any node → opens that file at the correct line in VS Code',
            'Drag nodes to rearrange the layout',
            'Search box → highlights matching nodes, dims everything else',
            'Filter chips → toggle node kinds (Class / Function / Test / File) and edge types',
            'Session card → live locked files, hot files, blast radius, and active tool',
            'Sessions strip → browse imported Cursor/Codex chats and scope the graph',
            'Smooth color transitions (500ms) when session state updates — no simulation restart',
          ].map((item) => (
            <li key={item} className="flex items-start gap-3">
              <span className="mt-1 text-teal-DEFAULT">→</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Live updates */}
      <section className="mb-10">
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Live Session Updates</h2>
        <p className="text-slate-400 mb-4">
          The extension watches <code>.reza/context.db</code> for changes using VS Code&apos;s
          <code>FileSystemWatcher</code>. When reza writes a new session turn, lock, or file change,
          the graph re-queries session state and smoothly transitions node colors — without restarting the force simulation.
        </p>
        <p className="text-slate-400">
          A configurable poll interval (default 3 seconds) serves as a fallback alongside the file watcher.
        </p>
      </section>

      {/* Config */}
      <section>
        <h2 className="font-syne font-700 text-2xl text-white mb-4">Configuration</h2>
        <div className="rounded-xl border border-[#1e2730] overflow-hidden text-sm">
          <table className="w-full">
            <thead>
              <tr className="bg-[#131920] border-b border-[#1e2730]">
                <th className="text-left px-4 py-3 font-syne text-xs uppercase tracking-widest text-slate-400">Setting</th>
                <th className="text-left px-4 py-3 font-syne text-xs uppercase tracking-widest text-slate-400">Default</th>
                <th className="text-left px-4 py-3 font-syne text-xs uppercase tracking-widest text-slate-400">Description</th>
              </tr>
            </thead>
            <tbody>
              {[
                { key: 'reza.rezaPath', def: '"reza"', desc: 'Path to the reza CLI executable' },
                { key: 'reza.nodeLimit', def: '800', desc: 'Max nodes to show (0 = no limit)' },
                { key: 'reza.defaultNodeKinds', def: '"Class,Function,Test"', desc: 'Node kinds shown by default' },
                { key: 'reza.refreshIntervalMs', def: '3000', desc: 'Session poll interval in ms' },
              ].map((row) => (
                <tr key={row.key} className="border-b border-[#1e2730] last:border-0">
                  <td className="px-4 py-3 font-mono text-teal-DEFAULT text-xs">{row.key}</td>
                  <td className="px-4 py-3 font-mono text-slate-500 text-xs">{row.def}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{row.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </DocPage>
  )
}
