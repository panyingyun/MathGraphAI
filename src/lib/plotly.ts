/** 缓存 Plotly 动态导入，避免首屏同步拉入 ~7MB 包。 */

export type PlotlyApi = {
  newPlot: (
    root: HTMLElement,
    data: unknown,
    layout?: unknown,
    config?: unknown,
  ) => Promise<unknown> | unknown;
  purge: (root: HTMLElement) => void;
  downloadImage: (
    root: HTMLElement,
    options: {
      format?: string;
      filename?: string;
      width?: number;
      height?: number;
      scale?: number;
    },
  ) => Promise<unknown> | unknown;
};

let plotlyPromise: Promise<PlotlyApi> | null = null;

export function loadPlotly(): Promise<PlotlyApi> {
  if (!plotlyPromise) {
    plotlyPromise = import("plotly.js-dist-min").then((mod) => {
      const api = (mod as { default?: PlotlyApi }).default ?? (mod as unknown as PlotlyApi);
      return api;
    });
  }
  return plotlyPromise;
}

export function prefetchPlotly(): void {
  void loadPlotly();
}
