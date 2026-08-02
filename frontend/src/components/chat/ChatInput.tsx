import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { Eraser, FunctionSquare, Send, Square } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { PromptSuggestions } from "./PromptSuggestions";

export function ChatInput({ preset, onPresetUsed }: { preset?: string; onPresetUsed?: () => void }) {
  const [value, setValue] = useState(preset ?? "");
  const [showExamples, setShowExamples] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const examplesId = useId();
  const sendMessage = useAppStore((state) => state.sendMessage);
  const cancelMessage = useAppStore((state) => state.cancelMessage);
  const loading = useAppStore((state) => state.isLLMLoading);
  const hydrating = useAppStore((state) => state.isHydratingSession);
  const inputLocked = loading || hydrating;

  useEffect(() => {
    if (preset) setValue(preset);
  }, [preset]);

  useEffect(() => {
    if (!showExamples) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!shellRef.current?.contains(event.target as Node)) setShowExamples(false);
    };
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setShowExamples(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [showExamples]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!value.trim() || inputLocked) return;
    setShowExamples(false);
    void sendMessage(value);
    setValue("");
    onPresetUsed?.();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const pickExample = (prompt: string) => {
    setValue(prompt);
    setShowExamples(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  return (
    <form className="chat-input-wrap" onSubmit={submit}>
      <div className="chat-input-shell" ref={shellRef}>
        {showExamples && (
          <div className="example-popover" id={examplesId} role="dialog" aria-label="推荐示例">
            <div className="example-popover-head">
              <strong>推荐示例</strong>
              <span>点选填入输入框</span>
            </div>
            <PromptSuggestions onSelect={pickExample} />
          </div>
        )}
        <div className="chat-input">
          <button
            type="button"
            className={`input-tool ${showExamples ? "active" : ""}`}
            aria-label="推荐示例"
            aria-expanded={showExamples}
            aria-controls={examplesId}
            onClick={() => setShowExamples((open) => !open)}
          >
            <FunctionSquare size={18} />
          </button>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            disabled={inputLocked}
            placeholder={hydrating ? "正在同步会话…" : "输入方程式或描述，例如：画 y = x²…"}
            aria-label="绘图需求"
          />
          {value && !inputLocked && <button type="button" className="input-tool" aria-label="清空" onClick={() => setValue("")}><Eraser size={17} /></button>}
          {loading ? (
            <button type="button" className="send-button cancel-button" onClick={() => void cancelMessage()} aria-label="取消请求">
              <Square size={16} />
            </button>
          ) : (
            <button type="submit" className="send-button" disabled={!value.trim() || hydrating} aria-label="发送"><Send size={18} /></button>
          )}
        </div>
      </div>
      <p>Enter 发送 · Shift + Enter 换行 · 处理中可取消，取消后不会保存半完成图像</p>
    </form>
  );
}
