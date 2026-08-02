import { Activity, CircleDot, MoveUpRight } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

export function GraphAnalysisPanel() {
  const analysis = useAppStore((state) => state.currentSession?.graphState.analysis);
  if (!analysis) return <div className="analysis-empty">请求“解释这个图像”，AI 分析会显示在这里。</div>;
  return (
    <div className="graph-analysis">
      {analysis.functionType && <div><Activity size={17} /><span>函数类型<small>{analysis.functionType}</small></span></div>}
      {analysis.symmetry && <div><CircleDot size={17} /><span>对称性<small>{analysis.symmetry}</small></span></div>}
      {analysis.monotonicity?.map((item) => <div key={item}><MoveUpRight size={17} /><span>单调性<small>{item}</small></span></div>)}
      {analysis.description && <p>{analysis.description}</p>}
    </div>
  );
}
