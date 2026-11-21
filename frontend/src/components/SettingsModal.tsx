import { useEffect, useRef, useState } from "react";
import { CheckCircle2, KeyRound, X } from "lucide-react";
import { api } from "../api/client";
import { useStudioStore } from "../store/useStudioStore";

import type { EnvInfo, StudioPreferences } from "../types/studio";
import { PreferenceQuestions, initialPreferences } from "./PreferenceQuestions";

export function SettingsModal() {
  const { settingsOpen, env } = useStudioStore();
  return settingsOpen && env ? <SettingsForm initialEnv={env} /> : null;
}

function SettingsForm({ initialEnv: env }: { initialEnv: EnvInfo }) {
  const { setSettingsOpen, refreshWorkspace, setToast, isTauri, setBasemap, setExecutionPolicy } = useStudioStore();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  const firstVisit = !env.preferences;
  const [step, setStep] = useState(0);
  const [preferences, setPreferences] = useState<StudioPreferences>(env.preferences ?? initialPreferences);
  const [provider, setProvider] = useState(env.credentials.provider);
  const [model, setModel] = useState(env.credentials.model);
  const [baseUrl, setBaseUrl] = useState(env.credentials.base_url);
  const [apiKey, setApiKey] = useState("");
  const [qgisDir, setQgisDir] = useState(env.qgis_dir ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const sameCredential = provider === env.credentials.provider && baseUrl.trim() === env.credentials.base_url && env.credentials.configured;
  const titles = ["连接 AI 模型", "选择地图样式", "设置工作习惯"];

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    setError("");
    setSaving(true);
    try {
      if (apiKey.trim() || provider !== env.credentials.provider || model !== env.credentials.model || baseUrl !== env.credentials.base_url) {
        await api.saveCredentials({
          provider,
          model,
          base_url: baseUrl,
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        });
      }
      if (qgisDir.trim() !== (env.qgis_dir ?? "")) await api.saveQgis(qgisDir.trim() || null);
      await api.savePreferences(preferences);
      setBasemap(preferences.basemap);
      setExecutionPolicy(preferences.execution_policy);
      await refreshWorkspace();
      setToast("已保存工作台偏好");
      setSettingsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <dialog ref={dialog} aria-labelledby="setup-title" onCancel={e => {
      e.preventDefault();
      if (!saving) setSettingsOpen(false);
    }} className="m-auto w-[min(36rem,94vw)] bg-transparent backdrop:bg-black/50">
      <form onSubmit={handleSave} className="bg-white rounded-xl shadow-2xl w-full max-w-xl border border-slate-200 max-h-[92dvh] overflow-y-auto">
        <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-sm text-slate-800">
            <KeyRound className="w-4 h-4 text-sky-600" />
            <span>{firstVisit ? "欢迎使用 OpenGIS Studio" : "工作台设置"}</span>
          </div>
          <button type="button" disabled={saving} aria-label="关闭设置" onClick={() => setSettingsOpen(false)} className="text-slate-400 hover:text-slate-700 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 pt-4">
          <div className="flex gap-1" aria-hidden="true">{titles.map((t, i) => <span key={t} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-sky-600" : "bg-slate-200"}`} />)}</div>
          <p className="mt-4 text-xs text-slate-500">第 {step + 1} 步，共 3 步</p>
          <h2 id="setup-title" className="mt-1 text-xl font-semibold">{titles[step]}</h2>
        </div>
        {step === 0 ? <div className="p-5 space-y-3.5 text-sm">
          <p className="text-xs text-slate-600">使用 GPT 时请选择 OpenAI。也可以先体验地图，稍后在设置中填写密钥。</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">服务商</label>
              <select
                aria-label="服务商" value={provider}
                onChange={(e) => {
                  const p = e.target.value;
                  setProvider(p);
                  setApiKey("");
                  if (p === "deepseek") {
                    setBaseUrl("https://api.deepseek.com");
                    setModel("deepseek-flash");
                  } else if (p === "openai") {
                    setBaseUrl("https://api.openai.com/v1");
                    setModel("gpt-4.1");
                  } else {
                    setModel("");
                    setBaseUrl("");
                  }
                }}
                className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs"
              >
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="compatible">OpenAI 兼容接口</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">模型 ID</label>
              <input
                required aria-label="模型 ID" value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">API Base URL</label>
            <input
              type="url" required aria-label="API Base URL" value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-600">API Key</label>
              {sameCredential && (
                <span className="text-[11px] text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  已配置 ({env.credentials.source})
                </span>
              )}
            </div>
            <input
              aria-label="API Key" type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={sameCredential ? "留空保持现有密钥不变，输入则覆盖保存" : "sk-..."}
              className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono"
            />
          </div>

          <details className="pt-2 border-t border-slate-100">
            <summary className="cursor-pointer text-xs text-slate-500 mb-2">QGIS 与运行环境（可选）</summary>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-600">桌面 QGIS 安装路径（可选增强，不装也可使用开源空间栈）</label>
              {isTauri && (
                <button
                  type="button"
                  onClick={async () => {
                    const p = await api.pickNativeFolder();
                    if (p) setQgisDir(p);
                  }}
                  className="text-[11px] text-sky-600 hover:underline cursor-pointer"
                >
                  浏览目录
                </button>
              )}
            </div>
            <input
              value={qgisDir}
              onChange={(e) => setQgisDir(e.target.value)}
              placeholder="例如 E:/exe/qgis（留空仅使用内置开源空间栈）"
              className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono"
            />
            {env?.detected_qgis_dirs && env.detected_qgis_dirs.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {env.detected_qgis_dirs.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setQgisDir(d)}
                    className="text-[11px] px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 cursor-pointer"
                  >
                    检测到：{d}
                  </button>
                ))}
              </div>
            )}

          {env?.python && (
            <div className="text-[11px] text-slate-500 bg-slate-50 rounded p-2 font-mono truncate" title={env.python.executable}>
              Python {env.python.version} · {Object.keys(env.python.packages || {}).length} 空间核心库已就绪
            </div>
          )}
          </details>
        </div> : <PreferenceQuestions step={step} value={preferences} onChange={setPreferences} />}
        {error && <p role="alert" className="px-5 pb-3 text-sm text-red-700">{error}</p>}

        <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
          <button type="button" disabled={saving} onClick={() => step ? setStep(step - 1) : setSettingsOpen(false)} className="px-3 py-1.5 text-xs rounded border border-slate-300">
            {step ? "上一步" : "稍后设置"}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-3.5 py-1.5 text-xs rounded bg-sky-600 hover:bg-sky-500 text-white font-medium disabled:opacity-50 cursor-pointer"
          >
            {saving ? "正在保存…" : step < 2 ? "下一步" : firstVisit ? "保存并进入工作台" : "保存设置"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
