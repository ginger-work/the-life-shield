"use client";

interface ScoreGaugeProps {
  score: number;
  bureau: string;
  pulledAt?: string;
  size?: number;
}

export function ScoreGauge({ score, bureau, pulledAt, size = 120 }: ScoreGaugeProps) {
  const MIN = 300;
  const MAX = 850;
  const pct = Math.max(0, Math.min(1, (score - MIN) / (MAX - MIN)));

  // Semicircle: 180 degrees
  const radius = (size - 20) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = Math.PI * radius;

  // Arc offset for gauge fill
  const strokeDasharray = circumference;
  const strokeDashoffset = circumference * (1 - pct);

  // Color based on score
  let strokeColor = "#dc2626"; // red
  let labelColor = "text-red-600";
  let label = "Poor";
  if (score >= 750) { strokeColor = "#16a34a"; labelColor = "text-green-600"; label = "Excellent"; }
  else if (score >= 700) { strokeColor = "#0d7a6e"; labelColor = "text-teal-600"; label = "Good"; }
  else if (score >= 650) { strokeColor = "#d97706"; labelColor = "text-yellow-600"; label = "Fair"; }
  else if (score >= 580) { strokeColor = "#f97316"; labelColor = "text-orange-500"; label = "Building"; }

  // SVG arc path for semicircle (left to right, bottom to bottom)
  const startX = cx - radius;
  const startY = cy;
  const endX = cx + radius;
  const endY = cy;

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 10} viewBox={`0 0 ${size} ${size / 2 + 10}`}>
        {/* Background track */}
        <path
          d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Score arc */}
        <path
          d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
          fill="none"
          stroke={strokeColor}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={strokeDasharray}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
        />
        {/* Score text */}
        <text
          x={cx}
          y={cy - 5}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="22"
          fontWeight="bold"
          fill="#1a2744"
        >
          {score || "—"}
        </text>
      </svg>

      <div className="text-center -mt-1">
        <p className={`text-xs font-semibold ${labelColor}`}>{label}</p>
        <p className="text-sm font-medium text-[#1a2744] capitalize mt-1">{bureau}</p>
        {pulledAt && (
          <p className="text-xs text-gray-400 mt-0.5">
            {new Date(pulledAt).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  );
}
