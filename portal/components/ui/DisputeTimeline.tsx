"use client";

const STEPS = [
  { key: "pending_approval", label: "Created" },
  { key: "approved", label: "Approved" },
  { key: "filed", label: "Filed" },
  { key: "investigating", label: "Under Review" },
  { key: "resolved", label: "Resolved" },
];

const STATUS_STEP_MAP: Record<string, number> = {
  pending_approval: 0,
  approved: 1,
  pending_filing: 1,
  filed: 2,
  investigating: 3,
  responded: 3,
  resolved: 4,
  rejected: 0,
  withdrawn: 0,
};

interface DisputeTimelineProps {
  status: string;
}

export function DisputeTimeline({ status }: DisputeTimelineProps) {
  const currentStep = STATUS_STEP_MAP[status] ?? 0;

  return (
    <div className="flex items-center w-full">
      {STEPS.map((step, idx) => {
        const isCompleted = idx <= currentStep;
        const isCurrent = idx === currentStep;

        return (
          <div key={step.key} className="flex-1 flex flex-col items-center">
            {/* Line before (except first) */}
            <div className="flex items-center w-full">
              {idx > 0 && (
                <div
                  className={`flex-1 h-1 ${idx <= currentStep ? "bg-[#c4922a]" : "bg-gray-200"}`}
                />
              )}
              {/* Circle */}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 ${
                  isCompleted
                    ? "bg-[#c4922a] border-[#c4922a] text-white"
                    : "bg-white border-gray-200 text-gray-400"
                } ${isCurrent ? "ring-2 ring-[#c4922a] ring-offset-2" : ""}`}
              >
                {isCompleted ? "✓" : idx + 1}
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-1 ${idx < currentStep ? "bg-[#c4922a]" : "bg-gray-200"}`}
                />
              )}
            </div>
            {/* Label */}
            <span
              className={`text-xs mt-1 text-center ${
                isCurrent ? "text-[#c4922a] font-semibold" : isCompleted ? "text-[#1a2744]" : "text-gray-400"
              }`}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
