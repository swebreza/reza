'use client'

import Link from 'next/link'
import Image from 'next/image'
import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Github, Copy, Check, ExternalLink, ChevronRight } from 'lucide-react'
import Navbar from '@/components/Navbar'

// ── Stat counter ─────────────────────────────────────────────────────────────
function useCounter(target: number, duration = 2000, start = false) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!start) return
    let startTime: number
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setCount(Math.floor(eased * target))
      if (progress < 1) requestAnimationFrame(step)
      else setCount(target)
    }
    requestAnimationFrame(step)
  }, [start, target, duration])
  return count
}

function StatCard({ value, suffix = '%', label, delay = 0 }: {
  value: number; suffix?: string; label: string; delay?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const count = useCounter(value, 1800, visible)

  useEffect(() => {
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold: 0.3 }
    )
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className="text-center"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="font-syne font-800 text-6xl md:text-7xl gradient-text leading-none mb-2">
        {count}{suffix}
      </div>
      <div className="text-sm text-slate-400 dark:text-slate-500 leading-snug max-w-[120px] mx-auto">
        {label}
      </div>
    </div>
  )
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      className="ml-auto flex-shrink-0 p-1.5 rounded-md text-slate-400 hover:text-teal transition-colors"
      aria-label="Copy"
    >
      {copied ? <Check size={14} className="text-teal-DEFAULT" /> : <Copy size={14} />}
    </button>
  )
}

// ── Integration card ──────────────────────────────────────────────────────────
const INTEGRATIONS = [
  { name: 'Claude Code', href: '/docs/integrations/claude-code', color: '#e8501a', emoji: '🟠', desc: 'Native skill + Stop hook' },
  { name: 'Cursor', href: '/docs/integrations/cursor', color: '#9b59b6', emoji: '🟣', desc: '.cursorrules auto-inject' },
  { name: 'Codex', href: '/docs/integrations/codex', color: '#3b82f6', emoji: '🔵', desc: 'System prompt injection' },
  { name: 'Aider', href: '/docs/integrations/aider', color: '#22c55e', emoji: '🟢', desc: '--read .reza/CONTEXT.md' },
  { name: 'Kilocode', href: '/docs/integrations/kilocode', color: '#f59e0b', emoji: '🟡', desc: 'Rules file global setup' },
  { name: 'Copilot', href: '/docs/integrations/copilot', color: '#6366f1', emoji: '🔷', desc: 'copilot-instructions.md' },
  { name: 'Continue', href: '/docs/integrations/continue', color: '#06b6d4', emoji: '🩵', desc: '@file + config.json' },
  { name: 'Codeium', href: '/docs/integrations/codeium', color: '#10b981', emoji: '💚', desc: 'Open context in editor' },
]

// ── Steps ─────────────────────────────────────────────────────────────────────
const STEPS = [
  {
    num: '01',
    title: 'reza init',
    desc: 'Indexes all your files, extracts purposes from docstrings, detects framework. Done in seconds.',
    cmd: 'reza init',
  },
  {
    num: '02',
    title: 'reza session start',
    desc: 'Links any AI tool to the current session. Sessions track progress across context limits and tool switches.',
    cmd: 'reza session start --llm claude',
  },
  {
    num: '03',
    title: 'reza session handoff',
    desc: 'Full conversation history ready to paste into any tool. Switches Claude → Cursor → Codex seamlessly.',
    cmd: 'reza session handoff --budget 8000',
  },
]

// ── Token savings table ───────────────────────────────────────────────────────
const SAVINGS = [
  { scenario: 'Task orientation (find relevant files)', without: '~18,000', with: '~4,900', pct: '73%' },
  { scenario: 'Cross-LLM handoff', without: '~10,000', with: '~1,250', pct: '88%' },
  { scenario: 'Find a specific file', without: '~7,200', with: '~450', pct: '94%' },
]

// ─────────────────────────────────────────────────────────────────────────────
export default function HomePage() {
  const heroRef = useRef<HTMLDivElement>(null)

  return (
    <div className="min-h-screen bg-[#0b0f16] dark:bg-[#0b0f16] text-white">
      <Navbar />

      {/* ── HERO ── */}
      <section
        ref={heroRef}
        className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 noise-bg overflow-hidden"
      >
        {/* Gradient orbs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-teal-DEFAULT/5 blur-[120px]" />
          <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-indigo-brand/5 blur-[100px]" />
        </div>

        <div className="relative z-10 max-w-4xl mx-auto flex flex-col items-center">
          {/* Version badge */}
          <a
            href="/docs/changelog"
            className="mb-8 inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium border border-teal-DEFAULT/30 bg-teal-DEFAULT/10 text-teal-DEFAULT hover:bg-teal-DEFAULT/15 transition-colors"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-teal-DEFAULT animate-pulse-slow" />
            v0.5.0 — Cursor + Codex session import
            <ChevronRight size={12} />
          </a>

          {/* Logo + title */}
          <div className="flex items-center gap-5 mb-6">
            <Image
              src="/logo.png"
              alt="reza"
              width={72}
              height={72}
              className="rounded-2xl shadow-2xl shadow-teal-DEFAULT/20"
            />
            <h1 className="font-syne font-800 text-7xl md:text-8xl tracking-tight text-white">
              reza
            </h1>
          </div>

          <h2 className="font-syne font-700 text-3xl md:text-5xl leading-tight tracking-tight mb-6">
            Universal LLM{' '}
            <span className="gradient-text">Context Database</span>
          </h2>

          <p className="text-lg md:text-xl text-slate-400 max-w-2xl leading-relaxed mb-10">
            Give any AI coding tool instant awareness of your project.
            Index once, never re-explain again. Works with Claude, Cursor, Codex, Aider, and more.
          </p>

          {/* Install commands */}
          <div className="flex flex-col sm:flex-row gap-3 mb-10 w-full max-w-xl">
            <div className="flex items-center gap-3 flex-1 px-4 py-3 rounded-xl bg-[#0d1117] border border-[#1e2730] font-mono text-sm">
              <span className="text-teal-DEFAULT select-none">$</span>
              <span className="text-slate-300 flex-1">npm install -g @swebreza/reza</span>
              <CopyButton text="npm install -g @swebreza/reza" />
            </div>
            <div className="flex items-center gap-3 flex-1 px-4 py-3 rounded-xl bg-[#0d1117] border border-[#1e2730] font-mono text-sm">
              <span className="text-teal-DEFAULT select-none">$</span>
              <span className="text-slate-300 flex-1">pip install reza</span>
              <CopyButton text="pip install reza" />
            </div>
          </div>

          {/* CTAs */}
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/docs"
              className="group flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-sm text-white"
              style={{ background: 'linear-gradient(135deg, #00d4aa, #38b2f8, #7c5cfc)' }}
            >
              Get Started
              <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <a
              href="https://github.com/swebreza/reza"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-sm text-slate-300 border border-[#1e2730] hover:border-teal-DEFAULT/50 hover:text-white transition-colors"
            >
              <Github size={16} />
              View on GitHub
              <ExternalLink size={12} />
            </a>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-slate-600 text-xs">
          <div className="w-px h-12 bg-gradient-to-b from-transparent to-teal-DEFAULT/40" />
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="py-24 px-6 border-y border-[#1e2730] bg-[#0d1117]">
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-semibold tracking-widest uppercase text-slate-500 mb-14">
            Measured on a real 1,710-file monorepo (Django + 2× FastAPI + 4× React)
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-12">
            <StatCard value={73} label="token reduction per session" delay={0} />
            <StatCard value={94} label="fewer tokens on file lookup" delay={100} />
            <StatCard value={88} label="savings on cross-LLM handoff" delay={200} />
            <StatCard value={8} suffix="+" label="AI tool integrations" delay={300} />
          </div>
          <p className="text-center text-slate-500 text-sm mt-14">
            At 500 sessions/month on Claude Sonnet: <span className="text-white font-semibold">~$14/month saved</span> in API costs.
            More importantly: <span className="text-teal-DEFAULT font-semibold">58+ hours of developer wait time returned.</span>
          </p>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-teal-DEFAULT text-xs font-semibold tracking-widest uppercase mb-3">How it works</p>
            <h2 className="font-syne font-700 text-4xl md:text-5xl tracking-tight text-white">
              Three commands.<br />
              <span className="gradient-text">Zero re-explaining.</span>
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {STEPS.map((step, i) => (
              <div
                key={step.num}
                className="relative p-6 rounded-2xl bg-[#0d1117] border border-[#1e2730] hover:border-teal-DEFAULT/30 transition-colors group"
              >
                {/* Gradient left border accent */}
                <div
                  className="absolute left-0 top-6 bottom-6 w-0.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: 'linear-gradient(180deg, #00d4aa, #7c5cfc)' }}
                />
                <div className="font-syne font-800 text-5xl gradient-text opacity-30 mb-4 leading-none">
                  {step.num}
                </div>
                <h3 className="font-syne font-700 text-lg text-white mb-2">{step.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed mb-4">{step.desc}</p>
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#131920] border border-[#1e2730] font-mono text-xs text-teal-DEFAULT">
                  <span className="text-slate-600">$</span>
                  {step.cmd}
                </div>
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-3 z-10 text-slate-700">
                    <ChevronRight size={20} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── INTEGRATIONS ── */}
      <section className="py-24 px-6 bg-[#0d1117] border-y border-[#1e2730]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-teal-DEFAULT text-xs font-semibold tracking-widest uppercase mb-3">Integrations</p>
            <h2 className="font-syne font-700 text-4xl md:text-5xl tracking-tight text-white">
              Works with every<br />
              <span className="gradient-text">AI coding tool</span>
            </h2>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {INTEGRATIONS.map((tool) => (
              <Link
                key={tool.name}
                href={tool.href}
                className="group relative p-5 rounded-2xl bg-[#131920] border border-[#1e2730] hover:border-transparent transition-all hover:-translate-y-0.5 hover:shadow-lg"
                style={{ '--tool-color': tool.color } as React.CSSProperties}
              >
                {/* Gradient border on hover */}
                <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: 'linear-gradient(135deg, #00d4aa, #38b2f8, #7c5cfc)', padding: '1px' }}>
                  <div className="w-full h-full rounded-2xl bg-[#131920]" />
                </div>
                <div className="relative z-10">
                  <div className="text-2xl mb-3">{tool.emoji}</div>
                  <div className="font-syne font-600 text-sm text-white mb-1">{tool.name}</div>
                  <div className="text-xs text-slate-500">{tool.desc}</div>
                </div>
              </Link>
            ))}
          </div>

          <p className="text-center text-slate-500 text-sm mt-10">
            Any tool can also use the universal{' '}
            <code className="text-teal-DEFAULT">reza export</code> workflow — paste context into any LLM.
          </p>
        </div>
      </section>

      {/* ── TOKEN SAVINGS TABLE ── */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-teal-DEFAULT text-xs font-semibold tracking-widest uppercase mb-3">Token savings</p>
            <h2 className="font-syne font-700 text-4xl tracking-tight text-white">
              Real numbers, real savings
            </h2>
          </div>

          <div className="rounded-2xl border border-[#1e2730] overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#131920] border-b border-[#1e2730]">
                  <th className="text-left px-6 py-4 font-syne font-600 text-xs uppercase tracking-widest text-slate-400">Scenario</th>
                  <th className="text-right px-4 py-4 font-syne font-600 text-xs uppercase tracking-widest text-slate-400">Without</th>
                  <th className="text-right px-4 py-4 font-syne font-600 text-xs uppercase tracking-widest text-slate-400">With reza</th>
                  <th className="text-right px-6 py-4 font-syne font-600 text-xs uppercase tracking-widest text-slate-400">Saved</th>
                </tr>
              </thead>
              <tbody>
                {SAVINGS.map((row, i) => (
                  <tr key={i} className="border-b border-[#1e2730] last:border-0 hover:bg-[#131920]/50 transition-colors">
                    <td className="px-6 py-4 text-slate-300">{row.scenario}</td>
                    <td className="px-4 py-4 text-right text-slate-500 font-mono text-xs">{row.without}</td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-teal-DEFAULT">{row.with}</td>
                    <td className="px-6 py-4 text-right">
                      <span className="font-syne font-700 gradient-text text-base">{row.pct}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24 px-6 border-t border-[#1e2730]">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="font-syne font-700 text-4xl md:text-5xl tracking-tight text-white mb-6">
            Ready to stop<br />
            <span className="gradient-text">re-explaining everything?</span>
          </h2>
          <p className="text-slate-400 mb-10 text-lg">
            Index your project once. Every AI tool you use will instantly know what you&apos;re building.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/docs/quick-start"
              className="group flex items-center gap-2 px-8 py-4 rounded-xl font-semibold text-white transition-all hover:shadow-lg hover:shadow-teal-DEFAULT/20"
              style={{ background: 'linear-gradient(135deg, #00d4aa, #38b2f8, #7c5cfc)' }}
            >
              Quick Start
              <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="/docs"
              className="px-8 py-4 rounded-xl font-semibold text-slate-300 border border-[#1e2730] hover:border-teal-DEFAULT/50 hover:text-white transition-colors"
            >
              Read the Docs
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-[#1e2730] py-10 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Image src="/logo.png" alt="reza" width={28} height={28} className="rounded-lg" />
            <span className="font-syne font-600 text-white">reza</span>
            <span className="text-slate-600 text-sm">·</span>
            <span className="text-slate-500 text-sm">MIT License</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-slate-500">
            <Link href="/docs" className="hover:text-teal-DEFAULT transition-colors">Docs</Link>
            <Link href="/docs/changelog" className="hover:text-teal-DEFAULT transition-colors">Changelog</Link>
            <a href="https://github.com/swebreza/reza" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-teal-DEFAULT transition-colors">
              <Github size={14} />
              GitHub
            </a>
            <a
              href="https://linkedin.com/in/suwebreza"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-teal-DEFAULT transition-colors"
            >
              Built by Suweb Reza
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
