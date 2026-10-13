import { useState } from "react";
import { can } from "../lib/auth";
import { useAuth } from "../lib/auth";

interface Props {
  articles: any[];
  companies: any[];
  currentCompanyId?: number;
  onCorrect: (articleId: number, companyId: number, action: "add" | "remove") => void;
}

export default function NewsFeed({ articles, companies, currentCompanyId, onCorrect }: Props) {
  const { role } = useAuth();
  const editable = can(role, "analyst");
  const [open, setOpen] = useState<number | null>(null);

  if (!articles.length) return <p className="muted">No tagged articles for this company yet.</p>;

  return (
    <div className="news-feed">
      {articles.map((a) => {
        const tags = a.tags || [];
        const taggedHere = currentCompanyId && tags.some((t: any) => t.company_id === currentCompanyId);
        return (
          <div className="news-item" key={a.id}>
            <div className="row between">
              <a href={a.url} target="_blank" rel="noreferrer" className="news-title">
                {a.title}
              </a>
              <span className="muted small">{a.source}</span>
            </div>
            <p className="muted small">{a.excerpt?.slice(0, 220)}</p>
            <div className="row tags">
              {tags.map((t: any) => {
                const co = companies.find((c) => c.id === t.company_id);
                return (
                  <span key={t.company_id} className={"tag " + (t.corrected ? "manual" : "")}>
                    {co?.symbol ?? "?"}
                    <em>{t.confidence.toFixed(2)}</em>
                    {t.corrected && <em>·edited</em>}
                  </span>
                );
              })}
              <span className="muted small">
                {new Date(a.published_at).toLocaleString()}
              </span>
            </div>

            {editable && (
              <div className="correct-wrap">
                <button className="ghost small" onClick={() => setOpen(open === a.id ? null : a.id)}>
                  {open === a.id ? "cancel" : "correct tags"}
                </button>
                {open === a.id && (
                  <div className="correct-panel">
                    <select
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) onCorrect(a.id, Number(e.target.value), "add");
                      }}
                    >
                      <option value="">add company…</option>
                      {companies
                        .filter((c) => !tags.some((t: any) => t.company_id === c.id))
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.symbol}
                          </option>
                        ))}
                    </select>
                    {taggedHere && (
                      <button
                        className="ghost small"
                        onClick={() => onCorrect(a.id, currentCompanyId!, "remove")}
                      >
                        remove {companies.find((c) => c.id === currentCompanyId)?.symbol} tag
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}