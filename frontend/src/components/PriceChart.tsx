import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Row {
  date: string;
  close: number;
  volume: number;
  vwap?: number | null;
}

export default function PriceChart({ rows }: { rows: Row[] }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#26303f" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: "#8b98a8", fontSize: 11 }}
          tickFormatter={(d: string) => d.slice(5)}
          minTickGap={24}
        />
        <YAxis
          yAxisId="price"
          orientation="right"
          tick={{ fill: "#8b98a8", fontSize: 11 }}
          domain={["auto", "auto"]}
        />
        <YAxis yAxisId="vol" hide domain={[0, "dataMax * 4"]} />
        <Tooltip
          contentStyle={{ background: "#141b24", border: "1px solid #26303f", borderRadius: 8 }}
          labelStyle={{ color: "#c8d2df" }}
        />
        <Bar yAxisId="vol" dataKey="volume" fill="#2c3849" name="volume" />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="close"
          stroke="#4da3ff"
          dot={false}
          strokeWidth={2}
          name="close"
        />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="vwap"
          stroke="#f5a623"
          dot={false}
          strokeDasharray="4 4"
          strokeWidth={1.4}
          name="vwap"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}