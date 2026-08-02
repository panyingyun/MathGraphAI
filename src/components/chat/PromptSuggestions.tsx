import { ChartNoAxesColumnIncreasing, DraftingCompass, Trash2, Waves } from "lucide-react";

export type SuggestionKind = "default" | "parse" | "unsupported" | "goal" | "remove";

type Suggestion = {
  icon: typeof ChartNoAxesColumnIncreasing;
  text: string;
  prompt: string;
};

const SUGGESTIONS: Record<SuggestionKind, Suggestion[]> = {
  default: [
    { icon: ChartNoAxesColumnIncreasing, text: "画一条抛物线", prompt: "帮我画 y = x^2，并解释它的图像特征" },
    { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
    { icon: DraftingCompass, text: "绘制 y = 2x + 1", prompt: "绘制 y = 2*x + 1" },
  ],
  parse: [
    { icon: ChartNoAxesColumnIncreasing, text: "画抛物线", prompt: "画 y = x^2" },
    { icon: Waves, text: "画正弦", prompt: "画 y = sin(x)" },
    { icon: DraftingCompass, text: "画直线", prompt: "画 y = 2*x + 1" },
  ],
  unsupported: [
    { icon: ChartNoAxesColumnIncreasing, text: "画抛物线并解释", prompt: "帮我画 y = x^2，并解释它的图像特征" },
    { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
    { icon: DraftingCompass, text: "绘制直线", prompt: "绘制 y = 2*x + 1" },
  ],
  goal: [
    { icon: ChartNoAxesColumnIncreasing, text: "画一条抛物线", prompt: "帮我画 y = x^2，并解释它的图像特征" },
    { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
    { icon: DraftingCompass, text: "绘制 y = 2x + 1", prompt: "绘制 y = 2*x + 1" },
  ],
  remove: [
    { icon: ChartNoAxesColumnIncreasing, text: "先画一条曲线", prompt: "画 y = x^2" },
    { icon: Trash2, text: "按表达式删除", prompt: "删除 y = x^2" },
    { icon: Trash2, text: "删除最后一条", prompt: "去掉最后一条曲线" },
  ],
};

export function suggestionKindFromError(
  errorCode?: string | null,
  content?: string | null,
): SuggestionKind {
  const code = (errorCode || "").toLowerCase();
  const text = content || "";
  if (code === "unsupported_request") return "unsupported";
  if (code === "expression_error" || code === "invalid_arguments" || text.includes("解析失败")) {
    return "parse";
  }
  if ((code === "goal_not_satisfied" || code === "decision_error") && /删除|移除|去掉/.test(text)) {
    return "remove";
  }
  if (code === "decision_error" || text.includes("无法理解") || text.includes("没能理解")) {
    return "default";
  }
  if (code === "goal_not_satisfied") {
    return "goal";
  }
  return "default";
}

export function PromptSuggestions({
  onSelect,
  kind = "default",
  compact = false,
}: {
  onSelect: (prompt: string) => void;
  kind?: SuggestionKind;
  compact?: boolean;
}) {
  const items = SUGGESTIONS[kind] ?? SUGGESTIONS.default;
  return (
    <div className={`prompt-suggestions ${compact ? "compact" : ""}`}>
      {items.map(({ icon: Icon, text, prompt }) => (
        <button key={`${kind}-${text}`} type="button" onClick={() => onSelect(prompt)}>
          <span><Icon size={16} /></span>{text}
        </button>
      ))}
    </div>
  );
}
