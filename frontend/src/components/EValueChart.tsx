import React, { useMemo } from "react";
import { useI18n } from "../i18n";
import type { EValuePoint } from "../types";

interface Props {
  series: EValuePoint[];
  shadowThreshold?: number;
  liveThreshold?: number;
  height?: number;
}

export const EValueChart: React.FC<Props> = ({
  series,
  shadowThreshold = 20,
  liveThreshold = 100,
  height = 220,
}) => {
  const { t } = useI18n();
  const { pathD, areaD, peakVal, maxY, yShadow, yLive, yNull, labels } = useMemo(() => {
    const w = 680;
    const h = height;
    const padL = 48;
    const padR = 16;
    const padT = 18;
    const padB = 28;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;

    if (!series.length) {
      return {
        pathD: "",
        areaD: "",
        peakVal: 1,
        maxY: 25,
        yShadow: padT + innerH * 0.3,
        yLive: padT,
        yNull: padT + innerH,
        labels: [] as Array<{ x: number; text: string }>,
      };
    }

    const vals = series.map((p) => Math.max(0.05, p.evalue));
    const peak = Math.max(...vals, ...series.map((p) => p.peak_evalue));
    const upper = Math.max(peak * 1.15, shadowThreshold * 1.25, 25);

    // Use log10 scaling so 1x, 20x, and 100x are all clearly legible simultaneously
    const logMin = Math.log10(0.25);
    const logMax = Math.log10(Math.max(upper, liveThreshold * 1.1));
    const mapY = (v: number) => {
      const lv = Math.log10(Math.max(0.25, v));
      const ratio = (lv - logMin) / Math.max(0.01, logMax - logMin);
      return padT + innerH * (1 - Math.min(1, Math.max(0, ratio)));
    };
    const mapX = (i: number) =>
      padL + (series.length === 1 ? innerW / 2 : (i / (series.length - 1)) * innerW);

    const pts = series.map((p, i) => [mapX(i), mapY(p.evalue)] as const);
    const d = pts
      .map(([x, y], idx) => `${idx === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ");
    const base = padT + innerH;
    const area = `${d} L${pts[pts.length - 1][0].toFixed(1)},${base.toFixed(1)} L${pts[0][0].toFixed(1)},${base.toFixed(1)} Z`;

    const tickCount = Math.min(5, series.length);
    const lbls: Array<{ x: number; text: string }> = [];
    for (let idxTick = 0; idxTick < tickCount; idxTick++) {
      const idx = Math.round((idxTick / Math.max(1, tickCount - 1)) * (series.length - 1));
      lbls.push({
        x: mapX(idx),
        text: series[idx].date ? series[idx].date!.slice(5) : `#${series[idx].step}`,
      });
    }

    return {
      pathD: d,
      areaD: area,
      peakVal: peak,
      maxY: upper,
      yShadow: mapY(shadowThreshold),
      yLive: mapY(liveThreshold),
      yNull: mapY(1.0),
      labels: lbls,
    };
  }, [series, shadowThreshold, liveThreshold, height]);

  const strokeColor =
    peakVal >= liveThreshold
      ? "#34d399"
      : peakVal >= shadowThreshold
      ? "#38bdf8"
      : "#a1a1aa";

  return (
    <div className="w-full rounded-lg border border-zinc-800 bg-[#09090b] p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
        <span className="font-mono uppercase tracking-wider text-zinc-300">
          {t("chart.title")}
        </span>
        <div className="flex items-center gap-4 font-mono">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
            {t("chart.paper")} ({shadowThreshold}x)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            {t("chart.live")} ({liveThreshold}x)
          </span>
        </div>
      </div>

      {!series.length ? (
        <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
          {t("chart.empty")}
        </div>
      ) : (
        <svg viewBox={`0 0 680 ${height}`} className="w-full overflow-visible">
          <defs>
            <linearGradient id="evFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.22" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Threshold reference lines */}
          <line
            x1="48"
            x2="664"
            y1={yLive}
            y2={yLive}
            stroke="#10b981"
            strokeOpacity="0.45"
            strokeDasharray="4 4"
          />
          <text x="6" y={yLive + 3} className="fill-emerald-400 font-mono text-[10px]">
            {liveThreshold}x
          </text>

          <line
            x1="48"
            x2="664"
            y1={yShadow}
            y2={yShadow}
            stroke="#38bdf8"
            strokeOpacity="0.45"
            strokeDasharray="4 4"
          />
          <text x="6" y={yShadow + 3} className="fill-sky-400 font-mono text-[10px]">
            {shadowThreshold}x
          </text>

          <line
            x1="48"
            x2="664"
            y1={yNull}
            y2={yNull}
            stroke="#52525b"
            strokeOpacity="0.6"
            strokeDasharray="2 3"
          />
          <text x="6" y={yNull + 3} className="fill-zinc-500 font-mono text-[10px]">
            1.0x
          </text>

          {/* Curve + subtle area */}
          <path d={areaD} fill="url(#evFill)" />
          <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2.2" />

          {/* X-axis labels */}
          {labels.map((l, i) => (
            <text
              key={i}
              x={l.x}
              y={height - 6}
              textAnchor="middle"
              className="fill-zinc-500 font-mono text-[10px]"
            >
              {l.text}
            </text>
          ))}
        </svg>
      )}
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
        <span>{t("chart.ville")}</span>
        <span className="font-mono text-zinc-300">
          {t("chart.peak")}: {peakVal.toFixed(2)}x (cap {maxY.toFixed(0)}x)
        </span>
      </div>
    </div>
  );
};
