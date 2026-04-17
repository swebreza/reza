'use client'

import { useEffect, useState } from 'react'
import clsx from 'clsx'

interface Heading {
  id: string
  text: string
  level: number
}

export default function TableOfContents() {
  const [headings, setHeadings] = useState<Heading[]>([])
  const [active, setActive] = useState<string>('')

  useEffect(() => {
    const els = document.querySelectorAll('article h2, article h3')
    const found: Heading[] = Array.from(els).map((el) => ({
      id: el.id,
      text: el.textContent ?? '',
      level: parseInt(el.tagName[1]),
    }))
    setHeadings(found)

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActive(entry.target.id)
        })
      },
      { rootMargin: '-64px 0px -60% 0px', threshold: 0 }
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  if (headings.length === 0) return null

  return (
    <nav className="w-64 flex-shrink-0 sticky top-20 h-[calc(100vh-5rem)] overflow-y-auto py-4 pl-4 hidden 2xl:block">
      <div className="rounded-xl border border-[#273142] bg-[#0f1623] p-3">
      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-3 px-2">
        On this page
      </p>
      <ul className="space-y-1">
        {headings.map((h) => (
          <li key={h.id}>
            <a
              href={`#${h.id}`}
              className={clsx(
                'block text-xs py-1 transition-colors rounded-md',
                h.level === 3 ? 'pl-6 pr-3' : 'px-3',
                active === h.id
                  ? 'text-teal-DEFAULT font-medium'
                  : 'text-slate-500 hover:text-slate-100'
              )}
            >
              {h.text}
            </a>
          </li>
        ))}
      </ul>
      </div>
    </nav>
  )
}
