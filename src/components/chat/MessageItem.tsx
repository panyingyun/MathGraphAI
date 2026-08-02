import { AlertCircle, Bot, CheckCircle2 } from "lucide-react";
import { InlineMath } from "react-katex";
import type { Message } from "../../types/chat";
import { PromptSuggestions, suggestionKindFromError } from "./PromptSuggestions";

function withMath(content: string) {
  const parts = content.split(/(y\s*=\s*[a-zA-Z0-9^*+\-/().]+)/g);
  return parts.map((part, index) => /^y\s*=/.test(part) ? (
    <span className="inline-formula" key={`${part}-${index}`}><InlineMath math={part.replace(/\*/g, "\\cdot ")} /></span>
  ) : part);
}

function formatErrorContent(content: string) {
  return content.split("\n").map((line, index) => (
    <span key={`${index}-${line}`}>
      {index > 0 && <br />}
      {withMath(line)}
    </span>
  ));
}

export function MessageItem({
  message,
  onSelectPrompt,
}: {
  message: Message;
  onSelectPrompt?: (prompt: string) => void;
}) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  const showSuggestions = Boolean(isError && onSelectPrompt);
  const suggestionKind = suggestionKindFromError(message.structuredResult?.error, message.content);

  return (
    <article className={`message ${isUser ? "user-message" : "assistant-message"} ${isError ? "message-error" : ""}`}>
      {!isUser && <div className="assistant-avatar">{isError ? <AlertCircle size={16} /> : <Bot size={16} />}</div>}
      <div className="message-content">
        {!isUser && (
          <div className="message-author">
            MathGraph AI
            {message.decisionProvider && (
              <span className={`provider-badge provider-${message.decisionProvider}`}>
                {message.decisionProvider === "deepseek" ? "DeepSeek" : "Local"}
              </span>
            )}
          </div>
        )}
        <div className="message-bubble">{isError ? formatErrorContent(message.content) : withMath(message.content)}</div>
        {showSuggestions && (
          <div className="error-suggestions">
            <div className="error-suggestions-label">点选一条合法示例继续</div>
            <PromptSuggestions
              kind={suggestionKind}
              compact
              onSelect={onSelectPrompt!}
            />
          </div>
        )}
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
