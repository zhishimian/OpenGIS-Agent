import { useEffect, useState } from "react";
import { Code2, Image as ImageIcon, Loader2, MessagesSquare, Map as MapIcon, X } from "lucide-react";
import { ChatPanel } from "./components/ChatPanel";
import { CodeEvidencePanel } from "./components/CodeEvidencePanel";
import { FigureWorkbench } from "./components/FigureWorkbench";
import { MapCanvas } from "./components/MapCanvas";
import { SettingsModal } from "./components/SettingsModal";
import { TopBar } from "./components/TopBar";
import { useStudioStore } from "./store/useStudioStore";

export default function App() {
  const { ready, initError, activeTab, setActiveTab, figures, toast, setToast, bootstrap } = useStudioStore();

  const [figurePath, setFigurePath] = useState<string | undefined>();
  const [chatWidth, setChatWidth] = useState(360);
  const resizeChat = (width: number) => setChatWidth(Math.max(280, Math.min(520, width)));
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const [folderOpen, setFolderOpen] = useState(false);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  if (!ready) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 gap-3">
        {initError ? (
          <div className="max-w-md text-center space-y-2 p-6 bg-slate-800 rounded-xl border border-rose-500/40">
            <div className="text-rose-400 font-semibold">无法启动 OpenGIS Studio</div>
            <div className="text-xs text-slate-300">{initError}</div>
            <button onClick={() => void bootstrap()} className="mt-2 px-4 py-1.5 rounded bg-sky-600 text-xs font-medium cursor-pointer">
              重试连接
            </button>
          </div>
        ) : (
          <>
            <Loader2 className="w-7 h-7 animate-spin text-sky-400" />
            <span className="text-xs text-slate-300">正在连接本地空间引擎与会话状态机…</span>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="studio-shell" style={{ "--chat-width": `min(${chatWidth}px, 52vw)` } as React.CSSProperties} data-mobile-chat={mobileChat} data-collapsed={chatCollapsed}>
      <TopBar folderOpen={folderOpen} setFolderOpen={setFolderOpen} />
      <nav className="studio-nav" aria-label="工作区视图">
        <button className="chat-switch" aria-expanded={!chatCollapsed} onClick={() => setChatCollapsed(!chatCollapsed)}>
          <MessagesSquare size={16} />{chatCollapsed ? "展开对话" : "分析对话"}
          <span aria-hidden="true">{chatCollapsed ? "›" : "‹"}</span>
        </button>
        <button className="mobile-switch" aria-pressed={mobileChat} onClick={() => setMobileChat(true)}>
          <MessagesSquare size={16} />对话
        </button>
        {([
          { tab: "map", label: "地图", Icon: MapIcon },
          { tab: "figures", label: "成图", Icon: ImageIcon },
          { tab: "code", label: "代码与证据", Icon: Code2 },
        ] as const).map(({ tab, label, Icon }) => (
          <button key={tab} data-work-view aria-pressed={activeTab === tab}
            onClick={() => { setActiveTab(tab); setMobileChat(false); }}>
            <Icon size={16} />{label}{tab === "figures" && figures.length > 0 && <small>{figures.length}</small>}
          </button>
        ))}
      </nav>
      <main className="studio-body">
        <aside className="studio-chat">
          <ChatPanel onOpenResult={(path) => { setFigurePath(path); setMobileChat(false); }} />
          <div className="chat-divider" role="separator" tabIndex={0} aria-label="对话栏宽度"
            aria-orientation="vertical" aria-valuenow={chatWidth} aria-valuemin={280} aria-valuemax={520}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                event.preventDefault();
                resizeChat(chatWidth + (event.key === "ArrowLeft" ? -16 : 16));
              }
            }}
            onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
            onPointerMove={(event) => {
              if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeChat(event.clientX);
            }}
          />
        </aside>
        <section className="studio-work">
          <div className={activeTab === "map" ? "h-full" : "hidden"}>
            <MapCanvas onSwitchFolder={() => setFolderOpen(true)} />
          </div>
          {activeTab === "figures" && <FigureWorkbench selectedPath={figurePath} onSelect={setFigurePath} />}
          {activeTab === "code" && <CodeEvidencePanel />}
        </section>
      </main>
      <SettingsModal />

      {toast && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-slate-900 text-white text-xs px-4 py-2 rounded-full shadow-lg flex items-center gap-2">
          <span>{toast}</span>
          <button onClick={() => setToast(null)} className="text-slate-400 hover:text-white cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
