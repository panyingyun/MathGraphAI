import { ChartNoAxesColumnIncreasing, DraftingCompass, Waves } from "lucide-react";

const suggestions = [
  { icon: ChartNoAxesColumnIncreasing, text: "画一条抛物线", prompt: "帮我画 y = x^2，并解释它的图像特征" },
  { icon: Waves, text: "比较正弦与余弦", prompt: "比较 y = sin(x) 和 y = cos(x)" },
  { icon: DraftingCompass, text: "绘制 y = 2x + 1", prompt: "绘制 y = 2*x + 1" },
];

export function PromptSuggestions({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="prompt-suggestions">
      {suggestions.map(({ icon: Icon, text, prompt }) => (
        <button key={text} onClick={() => onSelect(prompt)}>
          <span><Icon size={16} /></span>{text}
        </button>
      ))}
    </div>
  );
}
