import { Check, Copy, Eye, EyeOff, Palette, Trash2 } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const COLORS = ["#c15f3c", "#da3437", "#007d55", "#a855f7", "#d9a066"];

export function EquationList() {
  const equations = useAppStore((state) => state.currentSession?.graphState.equations ?? []);
  const updateEquation = useAppStore((state) => state.updateEquation);
  const removeEquation = useAppStore((state) => state.removeEquation);
  const showToast = useAppStore((state) => state.showToast);

  if (!equations.length) return <div className="equation-list-empty">绘制后，方程会显示在这里。</div>;

  return (
    <div className="equation-list">
      {equations.map((equation) => (
        <article className={`equation-row ${!equation.visible ? "muted" : ""}`} key={equation.id}>
          <button className="visibility" onClick={() => void updateEquation(equation.id, { visible: !equation.visible })} aria-label="显示或隐藏">
            {equation.visible ? <Eye size={17} /> : <EyeOff size={17} />}
          </button>
          <div className="color-picker-wrap">
            <input
              type="color"
              value={equation.color}
              aria-label="曲线颜色"
              onChange={(event) => void updateEquation(equation.id, { color: event.target.value })}
            />
            <span style={{ background: equation.color }}><Palette size={11} /></span>
          </div>
          <div className="equation-label"><strong>{equation.label}</strong><small>显函数 · 线宽 {equation.lineWidth}px</small></div>
          <button className="row-action" aria-label="复制公式" onClick={() => { void navigator.clipboard.writeText(equation.expression); showToast("公式已复制"); }}><Copy size={15} /></button>
          <button className="row-action danger" aria-label="删除方程" onClick={() => void removeEquation(equation.id)}><Trash2 size={15} /></button>
          <div className="quick-colors">
            {COLORS.map((color) => <button key={color} style={{ background: color }} onClick={() => void updateEquation(equation.id, { color })}>{equation.color === color && <Check size={9} />}</button>)}
          </div>
        </article>
      ))}
    </div>
  );
}
