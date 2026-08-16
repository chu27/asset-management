import { FormEvent, lazy, Suspense, useState } from "react";
import Modal from "./components/Modal";

const PortfolioView = lazy(() => import("./views/PortfolioView"));
const AssetsView = lazy(() => import("./views/AssetsView"));
const AnalysisView = lazy(() => import("./views/AnalysisView"));
const RemindersView = lazy(() => import("./views/RemindersView"));

type View = "portfolio" | "assets" | "analysis" | "reminders";
type BrandSettings = { icon: string; title: string; slogan: string };

const defaultBrand: BrandSettings = {
  icon: "钱",
  title: "资产管理",
  slogan: "来钱，来钱，来钱",
};

function loadBrand(): BrandSettings {
  try {
    const saved = localStorage.getItem("asset-manager-brand");
    return saved ? { ...defaultBrand, ...JSON.parse(saved) } : defaultBrand;
  } catch {
    return defaultBrand;
  }
}

export default function App() {
  const [view, setView] = useState<View>("assets");
  const [brand, setBrand] = useState<BrandSettings>(loadBrand);
  const [editingBrand, setEditingBrand] = useState(false);

  const saveBrand = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextBrand = {
      icon: String(form.get("icon") || defaultBrand.icon).trim().slice(0, 2),
      title: String(form.get("title") || defaultBrand.title).trim(),
      slogan: String(form.get("slogan") || defaultBrand.slogan).trim(),
    };
    setBrand(nextBrand);
    localStorage.setItem("asset-manager-brand", JSON.stringify(nextBrand));
    setEditingBrand(false);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand brand-editable" type="button" onClick={() => setEditingBrand(true)} title="点击编辑名称">
          <span>{brand.icon}</span>
          <div><strong>{brand.title}</strong><small>{brand.slogan}</small></div>
          <i aria-hidden="true">✎</i>
        </button>
        <nav>{([["assets", "资产总览"], ["portfolio", "持仓"], ["analysis", "分析"], ["reminders", "通知中心"]] as Array<[View, string]>).map(([key, label]) => <button className={view === key ? "active" : ""} onClick={() => setView(key)} key={key}>{label}</button>)}</nav>
      </header>
      <div className="page-content"><Suspense fallback={<div className="loading">正在打开页面……</div>}>{view === "portfolio" ? <PortfolioView /> : view === "assets" ? <AssetsView /> : view === "analysis" ? <AnalysisView /> : <RemindersView />}</Suspense></div>
      <footer><span>数据保存在本机 SQLite 数据库</span><span>行情来自 yfinance · 汇率来自 Frankfurter</span></footer>
      {editingBrand && <Modal title="编辑顶部名称" subtitle="保存后刷新页面也会保留" onClose={() => setEditingBrand(false)}><form className="form-grid" onSubmit={saveBrand}><label>图标文字<input name="icon" defaultValue={brand.icon} maxLength={2} required /></label><label>软件名称<input name="title" defaultValue={brand.title} required /></label><label className="full">标语<input name="slogan" defaultValue={brand.slogan} required /></label><div className="form-actions full"><button type="button" className="btn secondary" onClick={() => setEditingBrand(false)}>取消</button><button className="btn primary">保存修改</button></div></form></Modal>}
    </main>
  );
}
