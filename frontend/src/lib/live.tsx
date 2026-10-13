import { createContext, useContext, useRef, useState, ReactNode } from "react";
import { LiveEvent, useLiveUpdates } from "./useLiveUpdates";

interface LiveState {
  connected: boolean;
  lastEvent: LiveEvent | null;
  /** bump-increment that pages watch to know "something changed, refetch" */
  revision: number;
  notice: string | null;
}

const Ctx = createContext<LiveState>({
  connected: false,
  lastEvent: null,
  revision: 0,
  notice: null,
});

export function LiveProvider({ children }: { children: ReactNode }) {
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const { connected } = useLiveUpdates((e) => {
    setLastEvent(e);
    setRevision((r) => r + 1);
    if (e.type === "crawl_finished") {
      setNotice(`Crawl finished for ${e.portal} (${e.items_new} new)`);
    } else if (e.type === "market_finished") {
      setNotice(`Market data updated (${(e as any).status})`);
    } else if (e.type === "retag_finished") {
      setNotice(`Re-tagged ${(e as any).articles_processed} articles`);
    } else if (e.type === "alert_created") {
      setNotice(`Alert: ${(e as any).message}`);
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setNotice(null), 6000);
  });

  return (
    <Ctx.Provider value={{ connected, lastEvent, revision, notice }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLive() {
  return useContext(Ctx);
}