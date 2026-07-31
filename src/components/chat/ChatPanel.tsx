import { useEffect, useRef, useState } from "react";
import { FunctionSquare, MoreHorizontal } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { AgentProgress } from "./AgentProgress";
import { ChatInput } from "./ChatInput";
import { MessageItem } from "./MessageItem";
import { PromptSuggestions } from "./PromptSuggestions";

export function ChatPanel() {
  const session = useAppStore((state) => state.currentSession);
  const loading = useAppStore((state) => state.isLLMLoading);
  const error = useAppStore((state) => state.error);
  const agentSteps = useAppStore((state) => state.agentSteps);
  const clearError = useAppStore((state) => state.clearError);
  const showToast = useAppStore((state) => state.showToast);
  const [preset, setPreset] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length, loading]);

  return (
    <section className="chat-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">AI 对话</span><h1>{session?.title ?? "新会话"}</h1></div>
        <button className="icon-button" aria-label="更多操作" onClick={() => showToast("会话标题会根据首次绘图自动生成")}><MoreHorizontal size={19} /></button>
      </div>
      <div className={`message-list ${!session?.messages.length ? "empty" : ""}`}>
        {!session?.messages.length ? (
          <div className="chat-empty-state">
            <div className="function-orb"><FunctionSquare size={34} /></div>
            <h2>你想绘制什么数学图像？</h2>
            <p>用自然语言描述，或直接输入一个关于 x 的方程。</p>
            <PromptSuggestions onSelect={setPreset} />
          </div>
        ) : (
          <>
            <div className="day-chip">今天</div>
            {session.messages.map((message) => <MessageItem message={message} key={message.id} />)}
            {!loading && agentSteps.length > 0 && <AgentProgress steps={agentSteps} />}
            {loading && (
              <div className="message assistant-message">
                <div className="assistant-avatar"><FunctionSquare size={16} /></div>
                <div className="message-content"><div className="message-author">MathGraph AI</div><div className="typing"><i /><i /><i /><span>正在执行 Agent 步骤</span></div></div>
              </div>
            )}
          </>
        )}
        <div ref={endRef} />
      </div>
      {error && <div className="inline-error" role="alert"><span>{error}</span><button onClick={clearError}>关闭</button></div>}
      <ChatInput preset={preset} onPresetUsed={() => setPreset("")} />
    </section>
  );
}
