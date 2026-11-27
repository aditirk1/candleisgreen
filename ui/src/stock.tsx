// Clicking a ticker anywhere opens the stock panel. Screens call useStock().open(symbol).
import { createContext, ReactNode, useContext } from "react";
import { useMode } from "./theme";

export const StockContext = createContext<{ open: (symbol: string) => void }>({ open: () => {} });
export const useStock = () => useContext(StockContext);

export function Ticker({ symbol }: { symbol: string }) {
  const { open } = useStock();
  return <button className="ticker" onClick={(e) => { e.stopPropagation(); open(symbol); }} title={`Explain ${symbol}`}>{symbol}</button>;
}

/** Technical details: identifiers, config paths and versions. Shown only in Advanced mode, always labeled. */
export function Tech({ children, summary = "Technical details" }: { children: ReactNode; summary?: string }) {
  const mode = useMode();
  if (mode !== "advanced") return null;
  return <details className="tech"><summary>{summary}</summary><div className="tech-body">{children}</div></details>;
}
