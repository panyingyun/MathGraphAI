import { useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpen,
  Calculator,
  ChartNoAxesColumnIncreasing,
  CircleDot,
  Crosshair,
  DraftingCompass,
  Gauge,
  GitBranch,
  Infinity,
  Maximize2,
  Palette,
  Route,
  Scale,
  Sigma,
  SlidersHorizontal,
  Target,
  Trash2,
  TrendingUp,
  Triangle,
  Waves,
  ZoomIn,
} from "lucide-react";

export type SuggestionKind = "default" | "parse" | "unsupported" | "goal" | "remove";
export type GradeLevel = "middle" | "high";

type Suggestion = {
  icon: typeof ChartNoAxesColumnIncreasing;
  text: string;
  prompt: string;
};

/** 初中 10 条经典示例 */
const MIDDLE_SCHOOL_SUGGESTIONS: Suggestion[] = [
  { icon: TrendingUp, text: "正比例函数", prompt: "画 y = 2*x,解释图像为什么是一条过原点的直线" },
  { icon: Crosshair, text: "一次函数求零点", prompt: "画 y = 2*x - 4,标出零点,说明 2x-4=0 的解" },
  { icon: GitBranch, text: "斜率与倾斜程度", prompt: "画 y = x、y = 2*x、y = 0.5*x 三条直线,比较它们的倾斜程度" },
  { icon: Waves, text: "反比例函数", prompt: "画 y = 6/x,观察图像由两支曲线组成,说明 x 为什么不能为 0" },
  { icon: DraftingCompass, text: "绝对值函数", prompt: "画 y = abs(x),说明图像的 V 形特征和对称性" },
  { icon: Maximize2, text: "二次函数顶点", prompt: "画 y = x^2 - 4*x + 3,求出顶点坐标并拟合视口到顶点附近" },
  { icon: Calculator, text: "一元二次方程根", prompt: "画 y = x^2 - 3*x + 2,标出零点,说明它们对应方程 x^2-3x+2=0 的根" },
  { icon: Route, text: "方程组图像解", prompt: "画 y = x + 1 和 y = -x + 3,求交点,说明交点就是这个方程组的解" },
  { icon: Scale, text: "不等式的图像解法", prompt: "画 y = 2*x 和 y = x + 4,比较大小,指出 2x > x+4 的解集" },
  { icon: Gauge, text: "行程问题模型", prompt: "画 y = 60*x,表示匀速行驶的路程与时间关系,解释斜率的意义" },
];

/** 高中 10 条经典示例 */
const HIGH_SCHOOL_SUGGESTIONS: Suggestion[] = [
  { icon: BarChart3, text: "指数函数增减性", prompt: "画 y = 2^x 和 y = 0.5^x,解释底数对增减性的影响" },
  { icon: BookOpen, text: "对数与反函数", prompt: "画 y = 10^x 和 y = log(x),观察它们关于 y = x 对称" },
  { icon: Activity, text: "函数奇偶性", prompt: "画 y = x^3 和 y = x^2,说明奇偶函数图像的对称特征" },
  { icon: Waves, text: "正弦函数", prompt: "画 y = sin(x),把视口设为 x 从 -2π 到 2π,说明周期与振幅" },
  { icon: SlidersHorizontal, text: "图像变换", prompt: "画 y = sin(x)、y = 2*sin(x)、y = sin(2*x),观察振幅与频率变化" },
  { icon: Triangle, text: "正切与渐近线", prompt: "画 y = tan(x),视口 x 从 -3π 到 3π、y 从 -5 到 5,观察渐近线" },
  { icon: CircleDot, text: "正弦余弦交点", prompt: "画 y = sin(x) 和 y = cos(x),求交点并标出" },
  { icon: Infinity, text: "增长比较", prompt: "画 y = 2^x 和 y = x^2,求交点,比较增长速度" },
  { icon: ZoomIn, text: "导数与极值", prompt: "画 y = x^3 - 3*x,求极值点并拟合视口" },
  { icon: Target, text: "零点存在性", prompt: "画 y = x^3 - x - 1,求零点,判断零点所在区间" },
];

/** 错误引导等场景的通用入门建议(不区分学段,单组展示) */
const GENERAL_SUGGESTIONS: Suggestion[] = [
  { icon: ChartNoAxesColumnIncreasing, text: "画一条抛物线", prompt: "帮我画 y = x^2,并解释它的图像特征" },
  { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
  { icon: DraftingCompass, text: "绘制 y = 2x + 1", prompt: "绘制 y = 2*x + 1" },
  {
    icon: GitBranch,
    text: "两条曲线求交点",
    prompt: "画 y = x^2 和 y = 2-x,求出交点并放大到交点附近",
  },
  {
    icon: Crosshair,
    text: "抛物线求零点",
    prompt: "画 y = x^2 - 4,标出零点,并把坐标范围设为 -5 到 5",
  },
  {
    icon: TrendingUp,
    text: "三次函数求极值",
    prompt: "画 y = x^3 - 3*x,计算极值点并拟合到这些点附近",
  },
  {
    icon: Maximize2,
    text: "指数函数调视口",
    prompt: "画 y = exp(x),把坐标范围设为 -3 到 3",
  },
  {
    icon: Palette,
    text: "着色并设定范围",
    prompt: "画 y = x^2,改成红色,并把坐标范围设置为 -5 到 5",
  },
  {
    icon: Sigma,
    text: "正弦叠加比较",
    prompt: "画 y = sin(x) 和 y = 2*sin(x),比较它们的振幅差异",
  },
  {
    icon: Waves,
    text: "绝对值与抛物线",
    prompt: "画 y = abs(x) 和 y = x^2,求交点并简要解释图像差异",
  },
];

const SUGGESTIONS: Record<SuggestionKind, Suggestion[]> = {
  default: [],
  parse: [
    { icon: ChartNoAxesColumnIncreasing, text: "画抛物线", prompt: "画 y = x^2" },
    { icon: Waves, text: "画正弦", prompt: "画 y = sin(x)" },
    { icon: DraftingCompass, text: "画直线", prompt: "画 y = 2*x + 1" },
    { icon: GitBranch, text: "画两条曲线", prompt: "画 y = x 和 y = x^2" },
    { icon: Maximize2, text: "画指数", prompt: "画 y = exp(x)" },
  ],
  unsupported: GENERAL_SUGGESTIONS,
  goal: GENERAL_SUGGESTIONS,
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
  const [grade, setGrade] = useState<GradeLevel>("middle");
  const isDefault = kind === "default";
  const items = isDefault
    ? grade === "middle"
      ? MIDDLE_SCHOOL_SUGGESTIONS
      : HIGH_SCHOOL_SUGGESTIONS
    : (SUGGESTIONS[kind] ?? GENERAL_SUGGESTIONS);
  return (
    <div className={`prompt-suggestions ${compact ? "compact" : ""}`}>
      {isDefault && !compact && (
        <div className="grade-tabs" role="tablist" aria-label="选择学段示例">
          <button
            type="button"
            role="tab"
            aria-selected={grade === "middle"}
            className={grade === "middle" ? "active" : ""}
            onClick={() => setGrade("middle")}
          >
            初中
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={grade === "high"}
            className={grade === "high" ? "active" : ""}
            onClick={() => setGrade("high")}
          >
            高中
          </button>
        </div>
      )}
      {items.map(({ icon: Icon, text, prompt }) => (
        <button key={`${kind}-${grade}-${text}`} type="button" onClick={() => onSelect(prompt)}>
          <span><Icon size={16} /></span>{text}
        </button>
      ))}
    </div>
  );
}
