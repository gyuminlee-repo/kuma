/**
 * KvList — key-value list for Inspector panels.
 * Matches mockup CSS `.kv` pattern: 92px label / value 2-col grid.
 *
 * [source: v5-strategy.md §5 panel.kv]
 */

export type KvRow = {
  k: string;
  v: string;
};

type KvListProps = {
  rows: KvRow[];
  mono?: boolean;
};

export function KvList({ rows, mono = false }: KvListProps) {
  return (
    <dl className="grid gap-y-2" style={{ gridTemplateColumns: "92px 1fr" }}>
      {rows.map(({ k, v }) => (
        <div key={k} className="contents">
          <dt className="truncate text-[12px] font-medium text-muted-foreground">
            {k}
          </dt>
          <dd
            className={`min-w-0 break-all text-[12px] text-foreground ${mono ? "font-mono" : ""}`}
          >
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}
