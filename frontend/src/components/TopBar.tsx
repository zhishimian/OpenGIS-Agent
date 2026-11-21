import { useEffect, useState } from "react";
import { FolderOpen, Plus, Settings } from "lucide-react";
import { api } from "../api/client";
import { useStudioStore } from "../store/useStudioStore";


export function TopBar({ folderOpen, setFolderOpen }: { folderOpen: boolean; setFolderOpen: (value: boolean) => void }) {
  const {
    isTauri,
    projectDir,
    sessions,
    activeSessionId,
    usage,
    env,
    switchProject,
    selectSession,
    createNewSession,
    setSettingsOpen,
    setToast,
  } = useStudioStore();


  const [folderInput, setFolderInput] = useState(projectDir);
  const [newSessPromptOpen, setNewSessPromptOpen] = useState(false);
  const [newSessName, setNewSessName] = useState("");

  useEffect(() => { if (folderOpen) setFolderInput(projectDir); }, [folderOpen, projectDir]);

  const handleOpenFolder = async () => {
    if (isTauri) {
      const picked = await api.pickNativeFolder();
      if (picked) {
        try {
          await switchProject(picked);
        } catch (err: any) {
          setToast(err?.message || "切换目录失败");
        }
      }
      return;
    }
    setFolderInput(projectDir);
    setFolderOpen(true);
  };

  const handleSubmitFolder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderInput.trim()) return;
    try {
      await switchProject(folderInput.trim());
      setFolderOpen(false);
    } catch (err: any) {
      setToast(err?.message || "目录无效");
    }
  };

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createNewSession(newSessName.trim() || undefined);
      setNewSessName("");
      setNewSessPromptOpen(false);
    } catch (err: any) {
      setToast(err?.message || "新建会话失败");
    }
  };

  const hitPct = (usage.cache_hit_ratio * 100).toFixed(1);

  return (
    <header className="studio-header">
      <div className="studio-brand"><img src="/pixel-earth.png" alt="" width={28} height={28} className="size-7 object-contain [image-rendering:pixelated]" /><strong>OpenGIS <span>Studio</span></strong></div>
      <button className="project-button" title={projectDir} onClick={handleOpenFolder}>
        <FolderOpen size={16}/><span>{projectDir.split(/[\\/]/).filter(Boolean).pop() || projectDir || "选择工作目录"}</span>
      </button>
      <div className="session-controls">
        <select aria-label="分析会话" value={activeSessionId} onChange={(e) => void selectSession(e.target.value)}>
          {sessions.map((session) => <option key={session.session_id} value={session.session_id}>
            {/^[0-9a-f]{12}$/.test(session.session_id) ? session.title || `新会话 · ${session.session_id.slice(-4)}` : session.session_id}
            {session.waiting ? " · 待确认" : session.busy ? " · 运行中" : ""}
          </option>)}
        </select>
        <button title="新建会话" aria-label="新建会话" onClick={() => setNewSessPromptOpen(true)}><Plus size={16}/></button>
      </div>
      <details className="session-details">
        <summary>会话详情</summary>
        <div><strong>当前会话</strong><p>{activeSessionId}</p><p>{projectDir}</p>
          <p>费用 ¥{usage.estimated_cny.toFixed(2)} · 缓存 {hitPct}%</p>
          <p>输入 {usage.prompt_tokens} · 缓存 {usage.cached_tokens} · 输出 {usage.completion_tokens}</p>
        </div>
      </details>
      <button className="studio-settings" aria-label="工作台设置" title={env?.credentials.model || "模型与偏好设置"} onClick={() => setSettingsOpen(true)}>
        <Settings size={16}/><span>设置</span>
      </button>
      {folderOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <form onSubmit={handleSubmitFolder} className="bg-white text-slate-900 rounded-lg shadow-xl w-full max-w-md p-4 space-y-3">
            <h3 className="font-semibold text-sm">切换工作文件夹</h3>
            <input
              type="text"
              value={folderInput}
              onChange={(e) => setFolderInput(e.target.value)}
              className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-sm font-mono focus:outline-none focus:border-sky-500"
              placeholder="输入绝对路径，如 D:/gis_project"
            />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setFolderOpen(false)} className="px-3 py-1.5 text-xs rounded border border-slate-300">
                取消
              </button>
              <button type="submit" className="px-3 py-1.5 text-xs rounded bg-sky-600 text-white hover:bg-sky-500">
                确定切换
              </button>
            </div>
          </form>
        </div>
      )}

      {newSessPromptOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <form onSubmit={handleCreateSession} className="bg-white text-slate-900 rounded-lg shadow-xl w-full max-w-sm p-4 space-y-3">
            <h3 className="font-semibold text-sm">新建分析会话</h3>
            <input
              type="text"
              value={newSessName}
              onChange={(e) => setNewSessName(e.target.value)}
              className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-sm focus:outline-none focus:border-sky-500"
              placeholder="留空自动生成，如 jiangsu_flow"
            />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setNewSessPromptOpen(false)} className="px-3 py-1.5 text-xs rounded border border-slate-300">
                取消
              </button>
              <button type="submit" className="px-3 py-1.5 text-xs rounded bg-sky-600 text-white hover:bg-sky-500">
                创建
              </button>
            </div>
          </form>
        </div>
      )}
    </header>
  );
}
