export type Market = "japan" | "us" | "china";
export type Currency = "JPY" | "USD" | "CNY";
export type ManualAssetType = "cash" | "deposit" | "fund";

export type Position = {
  id: number;
  code: string;
  name: string;
  market: Market;
  currency: Currency;
  current_price: number;
  quantity: number;
  cost: number;
  average_cost: number;
  market_value: number;
  profit: number;
  profit_rate: number;
  realized_profit: number;
  value_jpy: number;
  position_rate: number;
  tags: string[];
  rule: { stop_loss: number | null; take_profit: number | null; position_limit: number | null };
};

export type Portfolio = {
  positions: Position[];
  total_stock_jpy: number;
  rates: { usd_jpy: number; cny_jpy: number; updated_at: string; source: string };
};

export type AssetRow = {
  id: number | string;
  name: string;
  secondary: string;
  asset_type: "stock" | ManualAssetType;
  currency: Currency;
  balance: number;
  source: "auto" | "manual";
  linked: boolean;
};

export type AssetSummary = {
  rows: AssetRow[];
  breakdown: Record<Currency, { stock: number; cash: number; deposit: number; fund: number }>;
  currency_totals: Record<Currency, number>;
  converted_jpy: Record<Currency, number>;
  total_jpy: number;
  total_cny: number;
  rates: Portfolio["rates"];
};

export type TagAnalysis = { name: string; value_jpy: number; rate: number; stocks: Array<{ id: number; code: string; name: string; position_rate: number }> };
export type AnalysisData = Portfolio & { tags: TagAnalysis[] };
export type HistoryPoint = { date: string; total_jpy: number };
export type Reminder = { id: string; status: "active" | "upcoming"; kind: string; title: string; headline: string; detail: string };
export type EventItem = { id: number; stock_id: number | null; stock: string | null; event_type: string; title: string; event_date: string; remind_days: number; source: string; confirmed: boolean; note: string | null };
