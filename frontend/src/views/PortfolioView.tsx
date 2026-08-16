import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Modal from "../components/Modal";
import type { AssetSummary, Market, Portfolio, Position } from "../types";

const marketInfo: Record<Market, { label: string; short: string }> = {
  japan: { label: "日股", short: "JP" }, us: { label: "美股", short: "US" }, china: { label: "科创", short: "TECH" },
};

const money = (value: number, market: Market) => value.toLocaleString(market === "japan" ? "ja-JP" : market === "us" ? "en-US" : "zh-CN", { maximumFractionDigits: market === "japan" ? 0 : 2 });
const currentPrice = (value: number, market: Market) => value.toLocaleString(market === "japan" ? "ja-JP" : market === "us" ? "en-US" : "zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

type Transaction = {
  id: number;
  stock_id: number;
  code: string;
  name: string;
  market: Market;
  kind: "buy" | "sell";
  trade_date: string;
  quantity: number;
  price: number;
  fee: number;
  tax: number;
  cash_asset_id: number | null;
  sell_reason: string | null;
  note: string | null;
};

type MarketPreviewItem = {
  stock_id: number;
  code: string;
  name: string;
  market: Market;
  symbol: string;
  current_price: number;
  suggested_price: number | null;
  status: "ready" | "failed";
  draft_price: string;
};

export default function PortfolioView() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [assets, setAssets] = useState<AssetSummary | null>(null);
  const [message, setMessage] = useState("");
  const [modal, setModal] = useState<"buy" | "sell" | "price" | "edit" | "market" | null>(null);
  const [selected, setSelected] = useState<Position | null>(null);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [buyMarket, setBuyMarket] = useState<Market>("japan");
  const [sellMarket, setSellMarket] = useState<Market>("japan");
  const [editMarket, setEditMarket] = useState<Market>("japan");
  const [editCashId, setEditCashId] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [transactionDate, setTransactionDate] = useState("");
  const [transactionMarket, setTransactionMarket] = useState<"all" | Market>("all");
  const [marketPreview, setMarketPreview] = useState<MarketPreviewItem[]>([]);

  const load = async () => {
    const [portfolio, assetData, history] = await Promise.all([api<Portfolio>("/api/portfolio"), api<AssetSummary>("/api/assets"), api<Transaction[]>("/api/transactions")]);
    setData(portfolio); setAssets(assetData); setTransactions(history);
  };
  useEffect(() => { load().catch((error) => setMessage(error.message)); }, []);

  const grouped = useMemo(() => ({ japan: data?.positions.filter((item) => item.market === "japan") ?? [], us: data?.positions.filter((item) => item.market === "us") ?? [], china: data?.positions.filter((item) => item.market === "china") ?? [] }), [data]);
  const filteredTransactions = useMemo(() => transactions.filter((item) => {
    const dateMatches = !transactionDate || String(item.trade_date) === transactionDate;
    const marketMatches = transactionMarket === "all" || item.market === transactionMarket;
    return dateMatches && marketMatches;
  }), [transactions, transactionDate, transactionMarket]);
  const cashAccounts = (market: Market) => assets?.rows.filter((item) => item.source === "manual" && item.asset_type === "cash" && item.linked && item.currency === (market === "japan" ? "JPY" : market === "us" ? "USD" : "CNY")) ?? [];

  async function submitBuy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await api("/api/transactions/buy", { method: "POST", body: JSON.stringify({ trade_date: form.get("date"), market: form.get("market"), code: form.get("code"), name: form.get("name"), quantity: Number(form.get("quantity")), price: Number(form.get("price")), fee: Number(form.get("fee")), cash_asset_id: form.get("cash") ? Number(form.get("cash")) : null, note: form.get("note") }) });
      setModal(null); setMessage("买入记录已保存"); await load();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function submitSell(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await api("/api/transactions/sell", { method: "POST", body: JSON.stringify({ trade_date: form.get("date"), stock_id: Number(form.get("stock")), quantity: Number(form.get("quantity")), price: Number(form.get("price")), fee: Number(form.get("fee")), tax: Number(form.get("tax")), cash_asset_id: form.get("cash") ? Number(form.get("cash")) : null, sell_reason: form.get("reason"), note: form.get("note") }) });
      setModal(null); setMessage("卖出记录已保存"); await load();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function submitPrice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return; const form = new FormData(event.currentTarget);
    try { await api(`/api/stocks/${selected.id}/price`, { method: "PATCH", body: JSON.stringify({ current_price: Number(form.get("price")) }) }); setModal(null); setMessage("当前价格已更新"); await load(); } catch (error) { setMessage((error as Error).message); }
  }

  async function submitTransactionEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingTransaction) return;
    const form = new FormData(event.currentTarget);
    try {
      await api(`/api/transactions/${editingTransaction.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          trade_date: form.get("date"),
          market: form.get("market"),
          code: form.get("code"),
          name: form.get("name"),
          quantity: Number(form.get("quantity")),
          price: Number(form.get("price")),
          fee: Number(form.get("fee")),
          tax: editingTransaction.kind === "sell" ? Number(form.get("tax")) : 0,
          cash_asset_id: form.get("cash") ? Number(form.get("cash")) : null,
          sell_reason: editingTransaction.kind === "sell" ? form.get("reason") : null,
          note: editingTransaction.kind === "buy" ? form.get("note") : null,
        }),
      });
      setModal(null); setEditingTransaction(null); setMessage("交易记录已修改"); await load();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function refreshMarket() {
    setMessage("正在从 yfinance 查询行情，尚未修改任何价格……");
    try {
      const result = await api<{ items: Omit<MarketPreviewItem, "draft_price">[] }>("/api/market/preview", { method: "POST" });
      setMarketPreview(result.items.map((item) => ({ ...item, draft_price: (item.suggested_price ?? item.current_price).toFixed(2) })));
      setMessage("");
      setModal("market");
    } catch (error) { setMessage((error as Error).message); }
  }

  async function confirmMarketPrices() {
    const prices = marketPreview
      .map((item) => ({ stock_id: item.stock_id, price: Number(item.draft_price) }))
      .filter((item) => Number.isFinite(item.price) && item.price > 0);
    if (!prices.length) { setMessage("请至少填写一个有效价格"); return; }
    try {
      const result = await api<{ count: number }>("/api/market/confirm", { method: "POST", body: JSON.stringify({ prices }) });
      setModal(null); setMessage(`已确认更新 ${result.count} 只股票`); await load();
    } catch (error) { setMessage((error as Error).message); }
  }

  if (!data) return <div className="loading">正在读取持仓……</div>;
  return <>
    <section className="page-intro portfolio-actions-only"><div className="intro-actions"><button className="btn secondary" onClick={refreshMarket}>更新行情</button><button className="btn secondary" onClick={() => setModal("sell")}>记录卖出</button><button className="btn primary" onClick={() => setModal("buy")}>＋ 记录买入</button></div></section>
    {message && <div className="notice">{message}</div>}
    <div className="stack">{(Object.keys(marketInfo) as Market[]).map((market) => <section className="card market-card" key={market}><div className="card-heading"><b className={`market-badge ${market}`}>{marketInfo[market].short}</b><div><h2>{marketInfo[market].label}</h2><p>{grouped[market].length} 只持仓</p></div></div><div className="table-wrap"><table><thead><tr><th>股票代码和名称</th><th>当前价格</th><th>持股数量</th><th>持仓成本</th><th>当前市值</th><th>盈亏</th></tr></thead><tbody>{grouped[market].map((position) => <tr key={position.id}><td><button className="stock-link" onClick={() => { setSelected(position); setModal("price"); }}><strong>{position.code}</strong>{position.name && <span>{position.name}</span>}</button></td><td>{currentPrice(position.current_price, market)}</td><td>{position.quantity.toLocaleString()} 股</td><td>{money(position.cost, market)}</td><td>{money(position.market_value, market)}</td><td><span className={`profit ${position.profit >= 0 ? "up" : "down"}`}>{position.profit >= 0 ? "+" : ""}{money(position.profit, market)}（{position.profit >= 0 ? "+" : ""}{position.profit_rate.toFixed(2)}%）</span></td></tr>)}</tbody></table></div></section>)}</div>
    <details className="card transaction-card"><summary>交易记录（{transactions.length}）</summary><div className="transaction-filters"><label>按日期查找<input type="date" value={transactionDate} onChange={(event) => setTransactionDate(event.target.value)} /></label><label>按市场查找<select value={transactionMarket} onChange={(event) => setTransactionMarket(event.target.value as "all" | Market)}><option value="all">全部市场</option><option value="japan">日股</option><option value="us">美股</option><option value="china">科创</option></select></label><button className="btn secondary" type="button" onClick={() => { setTransactionDate(""); setTransactionMarket("all"); }}>清除筛选</button><span>显示 {filteredTransactions.length} / {transactions.length} 条</span></div><div className="table-wrap"><table><thead><tr><th>日期</th><th>股票</th><th>类型</th><th>数量</th><th>单价</th><th>备注</th><th /></tr></thead><tbody>{filteredTransactions.map((item) => <tr key={item.id}><td>{item.trade_date}</td><td>{item.code}{item.name ? ` ${item.name}` : ""}</td><td>{item.kind === "buy" ? "买入" : "卖出"}</td><td>{item.quantity.toLocaleString()}</td><td>{item.price.toLocaleString()}</td><td>{item.kind === "buy" ? item.note ?? "—" : item.sell_reason ?? "—"}</td><td><div className="row-actions"><button onClick={() => { setEditingTransaction(item); setEditMarket(item.market); setEditCashId(item.cash_asset_id ? String(item.cash_asset_id) : ""); setModal("edit"); }}>修改</button><button className="text-danger" onClick={async () => { if (!confirm("确认删除这条交易记录？")) return; try { await api(`/api/transactions/${item.id}`, { method: "DELETE" }); await load(); } catch (error) { setMessage((error as Error).message); } }}>删除</button></div></td></tr>)}{filteredTransactions.length === 0 && <tr><td colSpan={7} className="empty-cell">没有符合条件的交易记录</td></tr>}</tbody></table></div></details>
    {modal === "buy" && <Modal title="记录买入" subtitle="股票代码必填，股票名称选填；手续费默认0" onClose={() => setModal(null)}><form className="form-grid" onSubmit={submitBuy}><label>交易日期<input name="date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label><label>市场<select name="market" value={buyMarket} onChange={(event) => setBuyMarket(event.target.value as Market)}><option value="japan">日本</option><option value="us">美国</option><option value="china">科创</option></select></label><label>股票代码（必填）<input name="code" required /></label><label>股票名称（选填）<input name="name" /></label><label>买入数量<input name="quantity" type="number" step="any" min="0" required /></label><label>买入单价<input name="price" type="number" step="any" min="0" required /></label><label>手续费<input name="fee" type="number" step="any" min="0" defaultValue="0" /></label><label>关联现金账户<select name="cash"><option value="">不关联</option>{cashAccounts(buyMarket).map((item) => <option value={item.id} key={item.id}>{item.name} · {item.currency}</option>)}</select></label><label className="full">备注（买入原因）<textarea name="note" /></label><div className="form-actions full"><button type="button" className="btn secondary" onClick={() => setModal(null)}>取消</button><button className="btn primary">保存买入</button></div></form></Modal>}
    {modal === "sell" && <Modal title="记录卖出" subtitle="先选择市场，再从仍有持仓的股票中选择" onClose={() => setModal(null)}><form className="form-grid" onSubmit={submitSell}><label>市场<select value={sellMarket} onChange={(e) => setSellMarket(e.target.value as Market)}><option value="japan">日本</option><option value="us">美国</option><option value="china">科创</option></select></label><label>股票<select name="stock" required>{grouped[sellMarket].map((item) => <option value={item.id} key={item.id}>{item.code} {item.name}（{item.quantity}股）</option>)}</select></label><label>交易日期<input name="date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label><label>卖出数量<input name="quantity" type="number" step="any" min="0" required /></label><label>卖出单价<input name="price" type="number" step="any" min="0" required /></label><label>手续费<input name="fee" type="number" step="any" min="0" defaultValue="0" /></label><label>税费<input name="tax" type="number" step="any" min="0" defaultValue="0" /></label><label>到账现金账户<select name="cash"><option value="">不关联</option>{cashAccounts(sellMarket).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="full">备注（卖出原因）<select name="reason"><option>达到目标价</option><option>触发止损</option><option>基本面发生变化</option><option>仓位过高</option><option>调整资产配置</option><option>临时需要现金</option><option>情绪化卖出</option><option>其他</option></select></label><div className="form-actions full"><button type="button" className="btn secondary" onClick={() => setModal(null)}>取消</button><button className="btn primary">保存卖出</button></div></form></Modal>}
    {modal === "price" && selected && <Modal title={`${selected.code} ${selected.name}`} subtitle="更新后会同步持仓、资产和提醒" onClose={() => setModal(null)}><form className="form-grid" onSubmit={submitPrice}><label className="full">当前价格<input name="price" type="number" step="any" min="0" defaultValue={selected.current_price} required /></label><div className="form-actions full"><button type="button" className="btn secondary" onClick={() => setModal(null)}>取消</button><button className="btn primary">更新价格</button></div></form></Modal>}
    {modal === "edit" && editingTransaction && <Modal title={`修改${editingTransaction.kind === "buy" ? "买入" : "卖出"}记录`} subtitle="修改后会同步重新计算原股票和新股票的持仓" onClose={() => setModal(null)}><form className="form-grid" onSubmit={submitTransactionEdit}><label>交易日期<input name="date" type="date" defaultValue={editingTransaction.trade_date} required /></label><label>交易类型<input value={editingTransaction.kind === "buy" ? "买入" : "卖出"} disabled /></label><label>市场<select name="market" value={editMarket} onChange={(event) => { setEditMarket(event.target.value as Market); setEditCashId(""); }}><option value="japan">日本</option><option value="us">美国</option><option value="china">科创</option></select></label><label>股票代码（必填）<input name="code" defaultValue={editingTransaction.code} required /></label><label className="full">股票名称（选填）<input name="name" defaultValue={editingTransaction.name} /></label><label>数量<input name="quantity" type="number" step="any" min="0" defaultValue={editingTransaction.quantity} required /></label><label>单价<input name="price" type="number" step="any" min="0" defaultValue={editingTransaction.price} required /></label><label>手续费<input name="fee" type="number" step="any" min="0" defaultValue={editingTransaction.fee} /></label>{editingTransaction.kind === "sell" && <label>税费<input name="tax" type="number" step="any" min="0" defaultValue={editingTransaction.tax} /></label>}<label className="full">关联现金账户<select name="cash" value={editCashId} onChange={(event) => setEditCashId(event.target.value)}><option value="">不关联</option>{cashAccounts(editMarket).map((item) => <option value={item.id} key={item.id}>{item.name} · {item.currency}</option>)}</select></label>{editingTransaction.kind === "buy" ? <label className="full">备注（买入原因）<textarea name="note" defaultValue={editingTransaction.note ?? ""} /></label> : <label className="full">备注（卖出原因）<input name="reason" defaultValue={editingTransaction.sell_reason ?? ""} required /></label>}<div className="form-actions full"><button type="button" className="btn secondary" onClick={() => setModal(null)}>取消</button><button className="btn primary">保存修改</button></div></form></Modal>}
    {modal === "market" && <Modal title="确认更新行情" subtitle="以下价格尚未保存；你可以先修改，再一键确认" onClose={() => setModal(null)}><div className="market-preview"><div className="table-wrap"><table><thead><tr><th>股票</th><th>当前价格</th><th>准备更新为</th><th>获取状态</th></tr></thead><tbody>{marketPreview.map((item, index) => <tr key={item.stock_id}><td><strong>{item.code}</strong>{item.name && <span className="block">{item.name}</span>}</td><td>{currentPrice(item.current_price, item.market)}</td><td><input type="number" step="any" min="0" value={item.draft_price} onChange={(event) => setMarketPreview((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, draft_price: event.target.value } : row))} /></td><td><span className={`source ${item.status === "ready" ? "auto" : "manual"}`}>{item.status === "ready" ? "已取得" : `${item.symbol} 未取得，保留原值`}</span></td></tr>)}</tbody></table></div><div className="market-preview-actions"><small>未取得行情时默认保留原价格，所有价格仍可手动修改</small><div><button type="button" className="btn secondary" onClick={() => setModal(null)}>取消</button><button type="button" className="btn primary" onClick={confirmMarketPrices}>一键确认更新</button></div></div></div></Modal>}
  </>;
}
