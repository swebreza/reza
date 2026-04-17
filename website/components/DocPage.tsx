import { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  children: ReactNode
  badge?: string
}

export default function DocPage({ title, description, children, badge }: Props) {
  return (
    <article className="max-w-3xl">
      {/* Page header */}
      <header className="mb-10 border-b border-[#1e2730] pb-8">
        {badge && (
          <span className="inline-block mb-3 px-3 py-1 rounded-full text-xs font-semibold border border-teal-DEFAULT/30 bg-teal-DEFAULT/10 text-teal-DEFAULT">
            {badge}
          </span>
        )}
        <h1 className="font-syne font-800 text-4xl md:text-5xl tracking-tight text-white mb-3">{title}</h1>
        {description && (
          <p className="text-slate-400 text-lg leading-8">{description}</p>
        )}
      </header>

      {/* MDX content */}
      <div className="
        prose prose-invert max-w-none text-[17px] leading-8
        prose-headings:font-syne prose-headings:tracking-tight prose-headings:font-700
        prose-h2:text-[1.75rem] prose-h2:mt-14 prose-h2:mb-5 prose-h2:text-white prose-h2:scroll-mt-24
        prose-h3:text-[1.35rem] prose-h3:mt-10 prose-h3:mb-4 prose-h3:text-white
        prose-h4:text-lg prose-h4:mt-8 prose-h4:mb-3 prose-h4:text-slate-200
        prose-p:my-6 prose-p:text-slate-300 prose-p:leading-8
        prose-ul:my-6 prose-ol:my-6 prose-li:my-2 prose-li:text-slate-300
        prose-strong:text-white prose-strong:font-600
        prose-a:text-teal-DEFAULT prose-a:underline prose-a:underline-offset-4 hover:prose-a:text-sky-brand prose-a:transition-colors
        prose-blockquote:my-8 prose-blockquote:border-slate-600 prose-blockquote:bg-slate-900/40
        prose-blockquote:not-italic prose-blockquote:rounded-r-lg prose-blockquote:px-5 prose-blockquote:py-3 prose-blockquote:text-slate-300
        prose-code:text-teal-DEFAULT prose-code:bg-teal-DEFAULT/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md
        prose-code:before:content-none prose-code:after:content-none
        prose-pre:my-8 prose-pre:bg-[#0d1117] prose-pre:border prose-pre:border-[#273142] prose-pre:rounded-xl prose-pre:px-5 prose-pre:py-4
        prose-table:my-8 prose-table:text-sm prose-th:text-slate-200 prose-th:font-600
        prose-td:text-slate-300 prose-tr:border-[#273142]
        prose-hr:my-10 prose-hr:border-[#273142]
      ">
        {children}
      </div>
    </article>
  )
}
