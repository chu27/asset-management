import { FormEvent, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { AnalysisData, HistoryPoint, Market, Position } from "../types";

type Tab = "stocks" | "history" | "review";
const marketInfo: Record<Market, string> = { japan: "日股", us: "美股", china: "科创" };
const ranges = [["1m", "1个月"], ["3m", "3个月"], ["6m", "6个月"], ["ytd", "今年"], ["1y", "1年"], ["3y", "3年"], ["5y", "5年"], ["all", "全部"]];

function RuleEditor({ position, onSaved }: { position: Position; onSaved: () => void }) {
  const [tags, setTags] = useState(position.tags.join("、"));
  const [stop, setStop] = useState(position.rule.stop_loss?.toString() ?? "");
  const [profit, setProfit] = useState(position.rule.take_profit?.toString() ?? "");
  const [limit, setLimit] = useState(position.rule.position_limit?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const percentage = (value: string, kind: "stop" | "profit") => { const price = Number(value); if (!price) return "输入后立即计算"; const diff = (price - position.average_cost) / position.average_cost * 100; return kind === "stop" ? `止损幅度 ${Math.abs(diff).toFixed(1)}%` : `止盈幅度 ${diff.toFixed(1)}%`; };
  const save = async () => { setSaving(true); try { await Promise.all([api(`/api/stocks/${position.id}/tags`, { method: "PUT", body: JSON.stringify({ tags: tags.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) }) }), api(`/api/stocks/${position.id}/rule`, { method: "PUT", body: JSON.stringify({ stop_loss: stop ? Number(stop) : null, take_profit: profit ? Number(profit) : null, position_limit: limit ? Number(limit) : null }) })]); onSaved(); } finally { setSaving(false); } };
  return <tr><td><strong>{position.code}</strong><small className="block">{position.name}</small></td><td>{position.current_price.toLocaleString()}</td><td>{position.average_cost.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td><td><input className="table-input tags-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="AI、Mag7" /></td><td><input className="table-input" type="number" value={stop} onChange={(e) => setStop(e.target.value)} placeholder="价格" /><small className="calc stop">{percentage(stop, "stop")}</small></td><td><input className="table-input" type="number" value={profit} onChange={(e) => setProfit(e.target.value)} placeholder="价格" /><small className="calc take">{percentage(profit, "profit")}</small></td><td><input className="table-input limit-input" type="number" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="%" /></td><td><button className="mini-save" onClick={save} disabled={saving}>{saving ? "保存中" : "保存"}</button></td></tr>;
}

export default function AnalysisView() {
  const [tab, setTab] = useState<Tab>("stocks");
  const [data, setData] = useState<AnalysisData | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [range, setRange] = useState("1y");
  const [message, setMessage] = useState("");
  const [periodType, setPeriodType] = useState<"month" | "year">("month");
  const [periodKey, setPeriodKey] = useState(new Date().toISOString().slice(0, 7));
  const [review, setReview] = useState({ good: "", improve: "", plan: "", other: "", sell_count: 0, sales: [] as Array<{ id: number; stock: string; trade_date: string; reason: string; note: string }> });
  const load = async () => setData(await api<AnalysisData>("/api/analysis"));
  useEffect(() => { load().catch((error) => setMessage(error.message)); }, []);
  useEffect(() => { if (tab === "history") api<HistoryPoint[]>(`/api/history?range=${range}`).then(setHistory).catch((error) => setMessage(error.message)); }, [tab, range]);
  useEffect(() => { if (tab === "review") api<typeof review>(`/api/reviews/${periodType}/${periodKey}`).then(setReview).catch((error) => setMessage(error.message)); }, [tab, periodType, periodKey]);
  const grouped = useMemo(() => ({ japan: data?.positions.filter((item) => item.market === "japan") ?? [], us: data?.positions.filter((item) => item.market === "us") ?? [], china: data?.positions.filter((item) => item.market === "china") ?? [] }), [data]);

  async function saveReview(event: FormEvent) { event.preventDefault(); try { await api(`/api/reviews/${periodType}/${periodKey}`, { method: "PUT", body: JSON.stringify({ good: review.good, improve: review.improve, plan: review.plan, other: review.other }) }); setMessage("投资复盘已保存"); } catch (error) { setMessage((error as Error).message); } }
  if (!data) return <div className="loading">正在读取分析数据……</div>;
  return <>
    <section className="page-intro"><div><span>STOCK ANALYSIS</span><h1>📊 股票分析</h1></div></section>
    {message && <div className="notice">{message}</div>}
    <nav className="subtabs"><button className={tab === "stocks" ? "active" : ""} onClick={() => setTab("stocks")}>股票与Tag</button><button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>历史变化</button><button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>投资复盘</button></nav>
    {tab === "stocks" && <div className="stack">{(Object.keys(marketInfo) as Market[]).map((market) => <section className="card" key={market}><div className="card-heading"><div><h2>{marketInfo[market]}</h2><p>{grouped[market].length} 只持仓</p></div></div><div className="table-wrap"><table className="analysis-table"><thead><tr><th>股票代码和名称</th><th>当前价格</th><th>持仓单价</th><th>Tag</th><th>止损点</th><th>止盈点</th><th>仓位上限</th><th /></tr></thead><tbody>{grouped[market].map((position) => <RuleEditor position={position} onSaved={async () => { setMessage(`${position.code} 设置已保存`); await load(); }} key={`${position.id}-${position.tags.join()}-${position.rule.stop_loss}-${position.rule.take_profit}`} />)}</tbody></table></div></section>)}<section className="card tag-chart-card"><div className="card-heading"><div><h2>按板块显示</h2></div></div><div className="tag-chart"><ResponsiveContainer><BarChart data={data.tags} layout="vertical" margin={{ left: 20, right: 30 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" unit="%" /><YAxis type="category" dataKey="name" width={90} /><Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} /><Bar dataKey="rate" fill="#6f4bb3" radius={[0, 8, 8, 0]} /></BarChart></ResponsiveContainer></div></section></div>}
    {tab === "history" && <section className="card history-card"><div className="card-heading"><div><h2>股票资产历史变化</h2><p>只统计股票资产，每周一个数据点</p></div><strong>¥{Math.round(data.total_stock_jpy).toLocaleString("ja-JP")}</strong></div><div className="range-row">{ranges.map(([key, label]) => <button className={range === key ? "active" : ""} onClick={() => setRange(key)} key={key}>{label}</button>)}</div><div className="history-chart"><ResponsiveContainer><LineChart data={history}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" minTickGap={30} /><YAxis tickFormatter={(value) => `¥${Math.round(value / 10000)}万`} width={70} /><Tooltip formatter={(value) => `¥${Math.round(Number(value)).toLocaleString("ja-JP")}`} /><Line dataKey="total_jpy" stroke="#6f4bb3" strokeWidth={3} dot={history.length < 30} /></LineChart></ResponsiveContainer></div><p className="footnote">买入或卖出股票也会改变总市值，因此曲线上升不完全等于投资收益。</p></section>}
    {tab === "review" && <section className="card review-card"><div className="card-heading"><div><h2>投资复盘</h2><p>系统汇总卖出记录，你填写判断与计划</p></div><div className="review-switch"><button className={periodType === "month" ? "active" : ""} onClick={() => { setPeriodType("month"); setPeriodKey(new Date().toISOString().slice(0, 7)); }}>月度</button><button className={periodType === "year" ? "active" : ""} onClick={() => { setPeriodType("year"); setPeriodKey(new Date().getFullYear().toString()); }}>年度</button></div></div><div className="review-summary"><label>复盘期间<input value={periodKey} onChange={(e) => setPeriodKey(e.target.value)} /></label><article><span>卖出次数</span><strong>{review.sell_count}</strong></article></div><div className="review-grid"><div><h3>本期卖出记录</h3>{review.sales.length ? review.sales.map((sale) => <article className="sale-card" key={sale.id}><strong>{sale.stock}</strong><span>{sale.trade_date}</span><p>卖出原因：{sale.reason || "未填写"}</p><p>{sale.note}</p></article>) : <p className="empty">本期没有卖出记录</p>}</div><form className="review-form" onSubmit={saveReview}><label>做得好的地方<textarea value={review.good} onChange={(e) => setReview({ ...review, good: e.target.value })} /></label><label>需要改进的地方<textarea value={review.improve} onChange={(e) => setReview({ ...review, improve: e.target.value })} /></label><label>下一阶段计划<textarea value={review.plan} onChange={(e) => setReview({ ...review, plan: e.target.value })} /></label><label>其他总结<textarea value={review.other} onChange={(e) => setReview({ ...review, other: e.target.value })} /></label><button className="btn primary">保存复盘</button></form></div></section>}
  </>;
}
