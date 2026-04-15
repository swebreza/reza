'use client'

import { useState } from 'react'
import { Copy, Check } from 'lucide-react'

interface Props {
  children: React.ReactNode
  lang?: string
}

export default function CodeBlock({ children, lang }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    const el = document.createElement('div')
    el.innerHTML = typeof children === 'string' ? children : ''
    const text = el.textContent ?? ''
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative group">
      {lang && (
        <span className="absolute top-3 left-4 text-[10px] font-mono font-medium text-slate-600 uppercase tracking-widest z-10">
          {lang}
        </span>
      )}
      <button
        onClick={handleCopy}
        className="absolute top-3 right-3 p-1.5 rounded-md bg-[#1e2730] opacity-0 group-hover:opacity-100 transition-all text-slate-400 hover:text-teal-DEFAULT hover:bg-[#1e2730] z-10"
        aria-label="Copy code"
      >
        {copied ? <Check size={13} className="text-teal-DEFAULT" /> : <Copy size={13} />}
      </button>
      {children}
    </div>
  )
}
