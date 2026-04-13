"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: "📊" },
  { label: "Credit Report", href: "/credit", icon: "📄" },
  { label: "Disputes", href: "/disputes", icon: "⚖️" },
  { label: "Tim Shaw", href: "/chat", icon: "💬" },
  { label: "Appointments", href: "/appointments", icon: "📅" },
  { label: "Documents", href: "/documents", icon: "📁" },
  { label: "Billing", href: "/billing", icon: "💳" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-[#1a2744] min-h-screen flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-[#2a3a5e]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#c4922a] rounded-lg flex items-center justify-center text-white font-bold text-xl">
            🛡️
          </div>
          <div>
            <h1 className="text-white font-bold text-base leading-tight">The Life Shield</h1>
            <p className="text-[#8899bb] text-xs">Credit Repair Portal</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                isActive
                  ? "bg-[#c4922a] text-white font-semibold"
                  : "text-[#8899bb] hover:bg-[#2a3a5e] hover:text-white"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span className="text-sm">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Tim Shaw status */}
      <div className="p-4 border-t border-[#2a3a5e]">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 bg-[#0d7a6e] rounded-full flex items-center justify-center text-white font-bold">
              TS
            </div>
            <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-400 rounded-full border-2 border-[#1a2744]" />
          </div>
          <div>
            <p className="text-white text-sm font-medium">Tim Shaw</p>
            <p className="text-green-400 text-xs">Online · AI Agent</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
