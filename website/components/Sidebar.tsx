'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { NAV_TREE, NavGroup } from '@/lib/nav'
import { ToolLogo, type ToolKey } from '@/components/ToolLogo'
import clsx from 'clsx'

function SidebarLink({ href, label, icon }: { href: string; label: string; icon?: ToolKey }) {
  const pathname = usePathname()
  return (
    <Link
      href={href}
      className={clsx('sidebar-link', pathname === href && 'active')}
    >
      {icon && <ToolLogo tool={icon} />}
      <span>{label}</span>
    </Link>
  )
}

export default function Sidebar() {
  return (
    <aside className="w-72 flex-shrink-0 sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto py-6 pr-5 border-r border-[#273142] hidden lg:block">
      <nav>
        {NAV_TREE.map((group) => (
          <SidebarGroup key={group.label} group={group} />
        ))}
      </nav>
    </aside>
  )
}

function SidebarGroup({ group }: { group: NavGroup }) {
  const pathname = usePathname()
  const isGroupActive = group.items.some((i) => pathname === i.href || pathname?.startsWith(i.href + '/'))
  const [open, setOpen] = useState(isGroupActive || group.defaultOpen !== false)

  return (
    <div className="mb-6">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1 mb-2 text-[11px] font-bold uppercase tracking-widest text-slate-400 hover:text-slate-100 transition-colors"
      >
        <span>{group.label}</span>
        <span className="text-slate-500">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
      </button>
      {open && (
        <ul className="space-y-0.5">
          {group.items.map((item) => (
            <li key={item.href}>
              <SidebarLink href={item.href} label={item.label} icon={item.icon} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
