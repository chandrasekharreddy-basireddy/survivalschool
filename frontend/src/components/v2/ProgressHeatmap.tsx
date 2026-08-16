"use client";

export function ProgressHeatmap({ values }: { values: number[] }) {
  const cells = Array.from({ length: 35 }, (_, index) => values[index] ?? 0);
  return (
    <div className="grid grid-flow-col grid-rows-7 gap-1" role="img" aria-label="35 day activity heatmap">
      {cells.map((value, index) => {
        const opacity = 0.12 + Math.min(1, Math.max(0, value / 4)) * 0.72;
        return <span key={index} title={`${value} activities`} className="h-3 w-3 border border-brand-500/20 bg-brand-500" style={{ opacity }} />;
      })}
    </div>
  );
}
