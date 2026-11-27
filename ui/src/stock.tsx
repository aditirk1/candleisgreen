// Clicking a ticker anywhere opens the stock panel. Screens call useStock().open(symbol).
import { createContext, useContext } from "react";

export const StockContext = createContext<{ open: (symbol: string) => void }>({ open: () => {} });
export const useStock = () => useContext(StockContext);

export function Ticker({ symbol }: { symbol: string }) {
  const { open } = useStock();
  return <button className="ticker" onClick={(e) => { e.stopPropagation(); open(symbol); }} title={`Explain ${symbol}`}>{symbol}</button>;
}
