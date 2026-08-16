import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { PieLabelRenderProps } from "recharts";
import { api } from "../api";
import Modal from "../components/Modal";
import type { AssetRow, AssetSummary, Currency, ManualAssetType } from "../types";

const currencies: Currency[] = ["JPY", "USD", "CNY"];
const purple = ["#6f4bb3", "#9d7ad6", "#d7ccf0", "#b278eb"];
const currencyColors: Record<Currency, string> = { JPY: "#ff7417", USD: "#1eb85f", CNY: "#f84444" };
const typeLabel: Record<string, string> = { stock: "股票", cash: "现金", deposit: "定存", fund: "基金" };
const format = (value: number, currency: Currency) => `${value.toLocaleString(currency === "JPY" ? "ja-JP" : currency === "USD" ? "en-US" : "zh-CN", { maximumFractionDigits: currency === "JPY" ? 0 : 2 })} ${currency}`;
const percent = (value: number, total: number) => total > 0 ? Math.round(value / total * 100) : 0;
const renderPieLabel = ({ x, y, name, percent: share, textAnchor, payload }: PieLabelRenderProps) => {
  if (!share) return null;
  return <text x={x} y={y} textAnchor={textAnchor} dominantBaseline="central" fill={payload?.color ?? "#6f4bb3"} fontSize={10} fontWeight={800}>{name} {Math.round(share * 100)}%</text>;
};

export default function AssetsView() {
  const [data, setData] = useState<AssetSummary | null>(null);
  const [message, setMessage] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<AssetRow | null>(null);
  const [assetType, setAssetType] = useState<ManualAssetType>("cash");
  const chartRefs = useRef<Partial<Record<Currency, HTMLElement | null>>>({});
  const detailRefs = useRef<Partial<Record<Currency, HTMLElement | null>>>({});
  const load = async () => setData(await api<AssetSummary>("/api/assets"));
  useEffect(() => { load().catch((error) => setMessage(error.message)); }, []);

  async function saveAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try { await api(editing ? `/api/assets/${editing.id}` : "/api/assets", { method: editing ? "PUT" : "POST", body: JSON.stringify({ name: form.get("name"), asset_type: form.get("type"), currency: form.get("currency"), balance: Number(form.get("balance")), linked: form.get("linked") === "yes", note: form.get("note") }) }); setShowAdd(false); setEditing(null); setMessage(editing ? "资产已更新" : "资产已添加"); await load(); } catch (error) { setMessage((error as Error).message); }
  }

  async function refreshRates() {
    setMessage("正在通过 Frankfurter 更新汇率……");
    try { await api("/api/rates/refresh", { method: "POST" }); setMessage("汇率已更新"); await load(); } catch (error) { setMessage((error as Error).message); await load(); }
  }
  const openCurrencyDetail = (currency: Currency) => detailRefs.current[currency]?.scrollIntoView({ behavior: "smooth", block: "start" });
  const openCurrencyChart = (currency: Currency) => chartRefs.current[currency]?.scrollIntoView({ behavior: "smooth", block: "center" });
  const openCurrencyDetailByKey = (event: KeyboardEvent<HTMLElement>, currency: Currency) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openCurrencyDetail(currency); }
  };
  const openCurrencyChartByKey = (event: KeyboardEvent<HTMLElement>, currency: Currency) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openCurrencyChart(currency); }
  };
  if (!data) return <div className="loading">正在读取资产……</div>;

  const allCurrencyData = currencies.map((currency) => ({ name: currency, value: data.converted_jpy[currency] }));
  return <>
    <section className="page-intro portfolio-actions-only"><div className="intro-actions"><button className="btn secondary" onClick={refreshRates}>刷新汇率</button><button className="btn primary" onClick={() => { setAssetType("cash"); setShowAdd(true); }}>＋ 添加资产</button></div></section>
    {message && <div className="notice">{message}</div>}
    <section className="card total-panel"><div className="card-heading"><div><h2>全部资产</h2><p>自动折算</p></div></div><div className="total-grid"><article><span>折合日元</span><strong>¥{Math.round(data.total_jpy).toLocaleString("ja-JP")}</strong></article><article><span>折合人民币</span><strong>¥{data.total_cny.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</strong></article></div><small className="rate-line">汇率来源：{data.rates.source} · 1 USD = {data.rates.usd_jpy.toFixed(2)} JPY · 1 CNY = {data.rates.cny_jpy.toFixed(2)} JPY · {data.rates.updated_at}</small></section>
    <div className="pie-grid">
      {currencies.map((currency) => {
        const total = data.currency_totals[currency];
        const chart = Object.entries(data.breakdown[currency]).map(([name, value], index) => ({ name: typeLabel[name], value, color: purple[index] })).filter((item) => item.value > 0);
        return <section className="card pie-card currency-jump-card" ref={(element) => { chartRefs.current[currency] = element; }} role="link" tabIndex={0} aria-label={`查看${currency}资产明细`} onClick={() => openCurrencyDetail(currency)} onKeyDown={(event) => openCurrencyDetailByKey(event, currency)} key={currency}><h3>{currency === "JPY" ? "🇯🇵 日元资产构成" : currency === "USD" ? "🇺🇸 美元资产构成" : "🇨🇳 人民币资产构成"}</h3><strong>{format(total, currency)}</strong><small className="jump-hint">点击查看明细 ↓</small><div className="chart-box"><ResponsiveContainer><PieChart><Pie data={chart} dataKey="value" nameKey="name" outerRadius={70} stroke="#fff" label={renderPieLabel} labelLine={{ stroke: "#9d7ad6" }}>{chart.map((item) => <Cell fill={item.color} key={item.name} />)}</Pie><Tooltip formatter={(value) => format(Number(value), currency)} /></PieChart></ResponsiveContainer></div><div className="asset-legend">{chart.map((item) => <div className="asset-legend-row" key={item.name}><span className="legend-name"><i style={{ background: item.color }} />{item.name}</span><span>{format(item.value, currency)} <em>({percent(item.value, total)}%)</em></span></div>)}</div></section>;
      })}
      <section className="card pie-card"><h3>货币占比（折合日元）</h3><strong>¥{Math.round(data.total_jpy).toLocaleString("ja-JP")}</strong><div className="chart-box"><ResponsiveContainer><PieChart><Pie data={allCurrencyData} dataKey="value" nameKey="name" outerRadius={70} stroke="#fff" label={renderPieLabel} labelLine={{ stroke: "#aaa4ad" }}>{allCurrencyData.map((item) => <Cell fill={currencyColors[item.name as Currency]} key={item.name} />)}</Pie><Tooltip formatter={(value) => `¥${Math.round(Number(value)).toLocaleString("ja-JP")}`} /></PieChart></ResponsiveContainer></div><div className="asset-legend">{allCurrencyData.filter((item) => item.value > 0).map((item) => <div className="asset-legend-row" key={item.name}><span className="legend-name"><i style={{ background: currencyColors[item.name as Currency] }} />{item.name}</span><span>¥{Math.round(item.value).toLocaleString("ja-JP")} <em>({percent(item.value, data.total_jpy)}%)</em></span></div>)}</div></section>
    </div>
    <div className="asset-stack">{currencies.map((currency) => <section className="card currency-detail" ref={(element) => { detailRefs.current[currency] = element; }} key={currency}><div className="card-heading currency-detail-heading" role="link" tabIndex={0} aria-label={`返回${currency}资产构成图`} onClick={() => openCurrencyChart(currency)} onKeyDown={(event) => openCurrencyChartByKey(event, currency)}><div><h2>{currency}资产明细</h2></div><div className="detail-heading-total"><small>点击返回图表 ↑</small><strong>{format(data.currency_totals[currency], currency)}</strong></div></div><div className="table-wrap"><table><thead><tr><th>资产名称</th><th>类型</th><th>当前金额</th><th>来源</th><th /></tr></thead><tbody>{data.rows.filter((item) => item.currency === currency).map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small className="block">{item.secondary}</small></td><td>{typeLabel[item.asset_type]}</td><td>{format(item.balance, currency)}</td><td><span className={`source ${item.source}`}>{item.source === "auto" ? "自动同步" : "手动填写"}</span></td><td>{item.source === "manual" && <div className="row-actions"><button onClick={() => { setAssetType(item.asset_type as ManualAssetType); setEditing(item); }}>修改</button><button className="text-danger" onClick={async () => { if (!confirm("确认删除这项资产？")) return; await api(`/api/assets/${item.id}`, { method: "DELETE" }); await load(); }}>删除</button></div>}</td></tr>)}</tbody></table></div></section>)}</div>
    {(showAdd || editing) && <Modal title={editing ? "修改资产" : "添加资产"} subtitle="现金、定存或基金" onClose={() => { setShowAdd(false); setEditing(null); }}><form className="form-grid" onSubmit={saveAsset}><label className="full">资产名称<input name="name" defaultValue={editing?.name ?? ""} required /></label><label>资产类型<select name="type" value={assetType} onChange={(event) => setAssetType(event.target.value as ManualAssetType)}><option value="cash">现金</option><option value="deposit">定存</option><option value="fund">基金</option></select></label><label>币种<select name="currency" defaultValue={editing?.currency ?? "JPY"}><option>JPY</option><option>USD</option><option>CNY</option></select></label><label>当前余额<input name="balance" type="number" step="any" min="0" defaultValue={editing?.balance ?? 0} /></label>{assetType === "cash" ? <label>关联投资记录<select name="linked" defaultValue={editing?.linked ? "yes" : "no"}><option value="no">不关联</option><option value="yes">关联</option></select></label> : <input type="hidden" name="linked" value="no" />}<label className="full">备注<textarea name="note" defaultValue={editing?.secondary ?? ""} /></label><div className="form-actions full"><button type="button" className="btn secondary" onClick={() => { setShowAdd(false); setEditing(null); }}>取消</button><button className="btn primary">{editing ? "保存修改" : "保存资产"}</button></div></form></Modal>}
  </>;
}
