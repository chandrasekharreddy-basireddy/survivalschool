"use client";

export function SkillRadar({ values, labels }: { values: number[]; labels: string[] }) {
  const count = Math.max(3, labels.length);
  const center = 50;
  const radius = 36;
  const point = (index: number, value: number) => {
    const angle = -Math.PI / 2 + (index / count) * Math.PI * 2;
    const r = radius * Math.max(0, Math.min(100, value)) / 100;
    return [center + Math.cos(angle) * r, center + Math.sin(angle) * r];
  };
  const outer = Array.from({ length: count }, (_, i) => point(i, 100).join(",")).join(" ");
  const valuePoints = Array.from({ length: count }, (_, i) => point(i, values[i] ?? 0).join(",")).join(" ");
  return (
    <div className="grid gap-4 sm:grid-cols-[220px_1fr] sm:items-center">
      <svg viewBox="0 0 100 100" className="mx-auto h-52 w-52" role="img" aria-label="Skill proficiency radar chart">
        <polygon points={outer} fill="none" stroke="currentColor" strokeWidth="0.6" className="text-ink-700" />
        <polygon points={Array.from({ length: count }, (_, i) => point(i, 66).join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="0.5" className="text-ink-800" />
        <polygon points={valuePoints} fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.3" className="text-brand-500" />
        {labels.map((label, i) => { const [x, y] = point(i, 112); return <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="4" className="fill-fg-subtle">{label.slice(0, 12)}</text>; })}
      </svg>
      <div className="space-y-2">
        {labels.map((label, i) => <div key={label} className="flex items-center justify-between gap-3 text-sm"><span className="truncate text-fg-muted">{label}</span><span className="font-mono text-fg">{Math.round(values[i] ?? 0)}%</span></div>)}
      </div>
    </div>
  );
}
