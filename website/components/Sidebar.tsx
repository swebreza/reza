'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { NAV_TREE, NavGroup } from '@/lib/nav'
import clsx from 'clsx'

function NavSection({ group }: { group: NavGroup }) {
  const pathname = usePathname()
  const isActive = group.items.some((i) => pathname === i.href)
  const [open, setOpen] = useState(isActive || group.defaultOpen !== false)

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1.5 mb-1 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-600 hover:text-slate-400 transition-colors"
      >
        <span>{group.label}</span>
        {open
          ? <ChevronDown size={12} />
          : <ChevronRight size={12} />}
      </button>
      {open && (
        <ul className="space-y-0.5">
          {group.items.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={clsx(
                  'sidebar-link',
                  usePathname() === item.href && 'active'
                )}
              >
                {item.icon && <span className="text-base leading-none">{item.icon}</span>}
                <span>{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Need to use a wrapper because usePathname can't be called in the map above inside the component scope
function SidebarLink({ href, label, icon }: { href: string; label: string; icon?: string }) {
  const pathname = usePathname()
  return (
    <Link
      href={href}
      className={clsx('sidebar-link', pathname === href && 'active')}
    >
      {icon && <span className="text-base leading-none">{icon}</span>}
      <span>{label}</span>
    </Link>
  )
}

export default function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto py-6 pr-4 border-r border-[#1e2730] dark:border-[#1e2730] hidden lg:block">
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
    <div className="mb-5">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1 mb-1 text-[11px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-600 hover:text-slate-300 transition-colors"
      >
        <span>{group.label}</span>
        <span className="text-slate-600">
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
