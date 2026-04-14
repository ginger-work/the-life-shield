"use client";

interface HeaderProps {
  title: string;
  scores?: Record<string, { score: number }>;
}

export function Header({ title, scores }: HeaderProps) {
  const bureaus = ["equifax", "experian", "transunion"];

  function getScoreColor(score: number) {
    if (score >= 750) return "text-green-600";
    if (score >= 700) return "text-teal-600";
    if (score >= 650) return "text-yellow-600";
    if (score >= 580) return "text-orange-600";
    return "text-red-600";
  }

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-20">
      <h1 className="text-lg font-semibold text-[#111827] tracking-tight">{title}</h1>

      <div className="flex items-center gap-6">
        {/* Mini score badges */}
        {scores && (
          <div className="flex gap-3">
            {bureaus.map((bureau) => {
              const data = scores[bureau];
              if (!data) return null;
              return (
                <div key={bureau} className="text-center">
                  <div className={`font-bold text-sm ${getScoreColor(data.score)}`}>
                    {data.score}
                  </div>
                  <div className="text-xs text-gray-400 capitalize">{bureau.slice(0, 3)}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* Notification bell */}
        <button className="relative p-2 text-gray-500 hover:text-[#1a2744] transition-colors">
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        </button>

        {/* Profile */}
        <div className="w-9 h-9 bg-[#1a2744] rounded-full flex items-center justify-center text-white font-semibold text-sm cursor-pointer">
          D
        </div>
      </div>
    </header>
  );
}
