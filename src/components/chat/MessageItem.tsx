import { Bot, CheckCircle2 } from "lucide-react";
import { InlineMath } from "react-katex";
import type { Message } from "../../types/chat";
import { PromptSuggestions, suggestionKindFromError } from "./PromptSuggestions";

function withMath(content: string) {
  const parts = content.split(/(y\s*=\s*[a-zA-Z0-9^*+\-/().]+)/g);
  return parts.map((part, index) => /^y\s*=/.test(part) ? (
    <span className="inline-formula" key={`${part}-${index}`}><InlineMath math={part.replace(/\*/g, "\\cdot ")} /></span>
  ) : part);
}

/** 气泡只保留说明句；「你可以试试」列表改由下方按钮展示。 */
function guideLead(content: string) {
  const lead = content.split(/\n\s*你可以试试[：:]/)[0].trim();
  return lead || content;
}

function formatMultiline(content: string) {
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
  const noopGuideText = message.content.includes("本轮未执行可验证的图像操作");
  // 引导态：失败回复，或成功但未做任何可验证图操作（旧路径/模型空 final）
  const treatAsGuide = !isUser && (message.status === "error" || noopGuideText);
  const showSuggestions = Boolean(treatAsGuide && onSelectPrompt);
  const suggestionKind = suggestionKindFromError(message.structuredResult?.error, message.content);
  const bubbleText = treatAsGuide
    ? (noopGuideText && message.status !== "error"
      ? "没能理解这次请求。用自然语言描述，或直接输入一个关于 x 的方程。"
      : guideLead(message.content))
    : message.content;

  return (
    <article className={`message ${isUser ? "user-message" : "assistant-message"}${treatAsGuide ? " message-guide" : ""}`}>
      {!isUser && (
        <div className="assistant-avatar">
          <Bot size={16} />
        </div>
      )}
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
        <div className="message-bubble">{treatAsGuide ? formatMultiline(bubbleText) : withMath(bubbleText)}</div>
        {showSuggestions && (
          <div className="guide-suggestions">
            <PromptSuggestions kind={suggestionKind} onSelect={onSelectPrompt!} />
          </div>
        )}
        {!isUser && !treatAsGuide && message.structuredResult?.analysis && (
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
