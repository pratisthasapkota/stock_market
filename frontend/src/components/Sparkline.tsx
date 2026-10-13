export default function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return <span className="muted">—</span>;
  const w = 96;
  const h = 30;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} className="spark" role="img" aria-label="price trend">
      <polyline
        points={points}
        fill="none"
        stroke={up ? "var(--up)" : "var(--down)"}
        strokeWidth="1.6"
      />
    </svg>
  );
}