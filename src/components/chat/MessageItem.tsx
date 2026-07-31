import { AlertCircle, Bot, CheckCircle2 } from "lucide-react";
import { InlineMath } from "react-katex";
import type { Message } from "../../types/chat";

function withMath(content: string) {
  const parts = content.split(/(y\s*=\s*[a-zA-Z0-9^*+\-/().]+)/g);
  return parts.map((part, index) => /^y\s*=/.test(part) ? (
    <span className="inline-formula" key={`${part}-${index}`}><InlineMath math={part.replace(/\*/g, "\\cdot ")} /></span>
  ) : part);
}

export function MessageItem({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  return (
    <article className={`message ${isUser ? "user-message" : "assistant-message"} ${isError ? "message-error" : ""}`}>
      {!isUser && <div className="assistant-avatar">{isError ? <AlertCircle size={16} /> : <Bot size={16} />}</div>}
      <div className="message-content">
        {!isUser && <div className="message-author">MathGraph AI</div>}
        <div className="message-bubble">{withMath(message.content)}</div>
        {!isUser && message.structuredResult?.analysis && (
          <div className="analysis-card">
            <div className="analysis-title"><CheckCircle2 size={15} />图像特征</div>
            {message.structuredResult.analysis.functionType && <div><span>函数类型</span><strong>{message.structuredResult.analysis.functionType}</strong></div>}
            {message.structuredResult.analysis.symmetry && <div><span>对称性</span><strong>{message.structuredResult.analysis.symmetry}</strong></div>}
            {message.structuredResult.analysis.monotonicity?.map((item) => <div key={item}><span>单调性</span><strong>{item}</strong></div>)}
          </div>
        )}
      </div>
    </article>
  );
}
