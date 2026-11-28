/** An error written for people. String(e) gives the message alone, without "Error:". */
export class ApiError extends Error {
  constructor(message: string, readonly path: string, readonly status: number | null) { super(message); }
  toString() { return this.message; }
}
const OFFLINE = "Cannot reach the CandleIsGreen server. Start it with make demo in a terminal, then refresh this page.";

export async function getJSON<T>(path: string): Promise<T> {
  let r: Response;
  try { r = await fetch(path); } catch { throw new ApiError(OFFLINE, path, null); }
  if (r.status === 502 || r.status === 503 || r.status === 504) throw new ApiError(OFFLINE, path, r.status);
  if (!r.ok) throw new ApiError(`This section could not be loaded (server error ${r.status}). Refresh to try again.`, path, r.status);
  return r.json() as Promise<T>;
}

export async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
}

export type Status = {
  mode: string; venue: string; now: string;
  feed: { status: string; last_run: string | null; job: string | null };
  risk_service: { status: string; kill_switch: boolean | null }; api: string;
};
export type Position = { instrument_id: string; symbol: string; quantity: number; price: number | null; market_value: number | null; weight: number | null; price_source: string };
export type Overview = {
  venue: string; account_value: number; cash: number; todays_change: number; todays_change_pct: number | null;
  risk_in_use: { invested_pct: number; largest_position_pct: number; position_limit_pct: number; cluster_limit_pct: number };
  equity_curve: { time: string; value: number }[]; positions: Position[];
  alerts: { symbol: string; event: string; detail: string; time: string }[];
};
export type OrderRow = { proposal_id: string; symbol: string; side: string; quantity: number; signal_strength: number | null; model: string; status: string; reason: string; session_date: string };
export type Execution = {
  venue: string; session_date: string | null; kill_switch: boolean | null;
  approval_queue: OrderRow[]; orders: OrderRow[];
  fills: { fill_id: string; instrument_id: string; symbol: string; side: string; quantity: number; price: number; filled_at: string; slippage_bps: number | null; venue: string }[];
  reconciliation: { status: string; reason: string };
  execution_quality: { window: string; fills: number; mean_bps: number; interval_95: number[] | null }[];
  execution_quality_note: string;
};
