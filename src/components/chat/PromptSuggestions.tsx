import {
  ChartNoAxesColumnIncreasing,
  Crosshair,
  DraftingCompass,
  GitBranch,
  Maximize2,
  Palette,
  Sigma,
  Trash2,
  TrendingUp,
  Waves,
} from "lucide-react";

export type SuggestionKind = "default" | "parse" | "unsupported" | "goal" | "remove";

type Suggestion = {
  icon: typeof ChartNoAxesColumnIncreasing;
  text: string;
  prompt: string;
};

/** 空会话与引导场景：3 条入门 + 7 条复合能力示例 */
const DEFAULT_SUGGESTIONS: Suggestion[] = [
  { icon: ChartNoAxesColumnIncreasing, text: "画一条抛物线", prompt: "帮我画 y = x^2，并解释它的图像特征" },
  { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
  { icon: DraftingCompass, text: "绘制 y = 2x + 1", prompt: "绘制 y = 2*x + 1" },
  {
    icon: GitBranch,
    text: "两条曲线求交点",
    prompt: "画 y = x^2 和 y = 2-x，求出交点并放大到交点附近",
  },
  {
    icon: Crosshair,
    text: "抛物线求零点",
    prompt: "画 y = x^2 - 4，标出零点，并把坐标范围设为 -5 到 5",
  },
  {
    icon: TrendingUp,
    text: "三次函数求极值",
    prompt: "画 y = x^3 - 3*x，计算极值点并拟合到这些点附近",
  },
  {
    icon: Maximize2,
    text: "指数函数调视口",
    prompt: "画 y = exp(x)，把坐标范围设为 -3 到 3",
  },
  {
    icon: Palette,
    text: "着色并设定范围",
    prompt: "画 y = x^2，改成红色，并把坐标范围设置为 -5 到 5",
  },
  {
    icon: Sigma,
    text: "正弦叠加比较",
    prompt: "画 y = sin(x) 和 y = 2*sin(x)，比较它们的振幅差异",
  },
  {
    icon: Waves,
    text: "绝对值与抛物线",
    prompt: "画 y = abs(x) 和 y = x^2，求交点并简要解释图像差异",
  },
];

const SUGGESTIONS: Record<SuggestionKind, Suggestion[]> = {
  default: DEFAULT_SUGGESTIONS,
  parse: [
    { icon: ChartNoAxesColumnIncreasing, text: "画抛物线", prompt: "画 y = x^2" },
    { icon: Waves, text: "画正弦", prompt: "画 y = sin(x)" },
    { icon: DraftingCompass, text: "画直线", prompt: "画 y = 2*x + 1" },
    { icon: GitBranch, text: "画两条曲线", prompt: "画 y = x 和 y = x^2" },
    { icon: Maximize2, text: "画指数", prompt: "画 y = exp(x)" },
  ],
  unsupported: DEFAULT_SUGGESTIONS,
  goal: DEFAULT_SUGGESTIONS,
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
