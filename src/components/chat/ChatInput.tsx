import { FormEvent, KeyboardEvent, useEffect, useState } from "react";
import { Eraser, FunctionSquare, Send } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

export function ChatInput({ preset, onPresetUsed }: { preset?: string; onPresetUsed?: () => void }) {
  const [value, setValue] = useState(preset ?? "");
  const sendMessage = useAppStore((state) => state.sendMessage);
  const loading = useAppStore((state) => state.isLLMLoading);

  useEffect(() => {
    if (preset) setValue(preset);
  }, [preset]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!value.trim() || loading) return;
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

  return (
    <form className="chat-input-wrap" onSubmit={submit}>
      <div className="chat-input">
        <button type="button" className="input-tool" aria-label="公式输入"><FunctionSquare size={18} /></button>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={loading}
          placeholder="输入方程式或描述，例如：画 y = x²…"
          aria-label="绘图需求"
        />
        {value && <button type="button" className="input-tool" aria-label="清空" onClick={() => setValue("")}><Eraser size={17} /></button>}
        <button type="submit" className="send-button" disabled={!value.trim() || loading} aria-label="发送"><Send size={18} /></button>
      </div>
      <p>Enter 发送 · Shift + Enter 换行 · MathGraph AI 可能出错，请核对关键结果</p>
    </form>
  );
}
