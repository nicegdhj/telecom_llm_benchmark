import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { FolderKanban, Activity, CheckCircle, XCircle } from 'lucide-react';

const STATS = [
  { key: 'totalBatches', label: '总批次',  icon: FolderKanban, color: 'text-primary-600', bg: 'bg-primary-50' },
  { key: 'runningJobs',  label: '运行中',  icon: Activity,     color: 'text-amber-600',   bg: 'bg-amber-50'   },
  { key: 'successJobs',  label: '成功',    icon: CheckCircle,  color: 'text-emerald-600', bg: 'bg-emerald-50' },
  { key: 'failedJobs',   label: '失败',    icon: XCircle,      color: 'text-red-600',     bg: 'bg-red-50'     },
];

function roundedTopRect(x, y, w, h, r) {
  if (h <= 0) return '';
  const rr = Math.min(r, h, w / 2);
  return `M${x + rr},${y} h${w - 2 * rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${h - rr} h${-w} v${-(h - rr)} a${rr},${rr} 0 0 1 ${rr},${-rr}z`;
}

function niceYTicks(maxVal) {
  if (maxVal <= 0) return [0];
  const step = maxVal <= 4 ? 1 : maxVal <= 10 ? 2 : maxVal <= 20 ? 5 : Math.ceil(maxVal / 4 / 5) * 5;
  const ticks = [];
  for (let v = 0; v <= maxVal; v += step) ticks.push(v);
  if (ticks[ticks.length - 1] < maxVal) ticks.push(maxVal);
  return [...new Set(ticks)];
}

function DailyJobsChart({ jobs }) {
  const [tooltip, setTooltip] = useState(null);

  const days = useMemo(() => {
    return Array.from({ length: 14 }, (_, i) => {
      const d = new Date();
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - (13 - i));
      const next = new Date(d);
      next.setDate(next.getDate() + 1);
      const dayJobs = (jobs || []).filter(j => {
        const t = new Date((j.created_at || '').endsWith('Z') ? j.created_at : j.created_at + 'Z');
        return t >= d && t < next;
      });
      return {
        date: d,
        success: dayJobs.filter(j => j.status === 'success').length,
        failed:  dayJobs.filter(j => j.status === 'failed').length,
        running: dayJobs.filter(j => j.status === 'running').length,
      };
    });
  }, [jobs]);

  const rawMax = Math.max(...days.map(d => d.success + d.failed + d.running), 1);
  const yTicks = niceYTicks(rawMax);
  const maxVal = yTicks[yTicks.length - 1];

  const chartH = 100, barW = 14, gap = 16, paddingL = 26, paddingB = 20, paddingT = 8, r = 3;
  const svgW = paddingL + days.length * (barW + gap) - gap + 8;
  const svgH = paddingT + chartH + paddingB;
  const baseY = paddingT + chartH;

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
      <div className="px-5 py-3.5 border-b border-gray-50 flex items-center justify-between">
        <div>
          <h3 className="text-[13px] font-semibold text-gray-800">每日任务量</h3>
          <p className="text-[11px] text-gray-400 mt-0.5">最近 14 天</p>
        </div>
        <div className="flex items-center gap-3 text-[10.5px] text-gray-400">
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full inline-block bg-[#34d399]" />成功</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full inline-block bg-[#f87171]" />失败</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full inline-block bg-[#60a5fa]" />运行中</span>
        </div>
      </div>
      <div className="px-4 pt-3 pb-2">
        <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`} style={{ overflow: 'visible', display: 'block' }}>
          {/* Y 轴刻度 */}
          {yTicks.map(v => {
            const y = baseY - (v / maxVal) * chartH;
            return (
              <g key={v}>
                <line x1={paddingL} y1={y} x2={svgW} y2={y}
                  stroke={v === 0 ? '#e2e8f0' : '#f1f5f9'} strokeWidth="1"
                  strokeDasharray={v === 0 ? '' : '4 3'} />
                <text x={paddingL - 5} y={y + 3.5} textAnchor="end" fontSize="7.5" fill="#cbd5e1">{v}</text>
              </g>
            );
          })}

          {/* 柱子 + X 轴标签 */}
          {days.map((d, i) => {
            const x = paddingL + i * (barW + gap);
            const isToday = i === 13;
            const total = d.success + d.failed + d.running;
            const sH = (d.success / maxVal) * chartH;
            const fH = (d.failed  / maxVal) * chartH;
            const rH = (d.running / maxVal) * chartH;
            const sY = baseY - sH;
            const fY = sY - fH;
            const rY = fY - rH;
            const segs = [];
            if (d.success > 0) segs.push({ y: sY, h: sH, fill: '#34d399', top: d.failed === 0 && d.running === 0 });
            if (d.failed  > 0) segs.push({ y: fY, h: fH, fill: '#f87171', top: d.running === 0 });
            if (d.running > 0) segs.push({ y: rY, h: rH, fill: '#60a5fa', top: true });

            return (
              <g key={i}
                onMouseEnter={() => setTooltip({ i, d, x: x + barW / 2 })}
                onMouseLeave={() => setTooltip(null)}
                style={{ cursor: total > 0 ? 'pointer' : 'default' }}
              >
                {/* 背景槽 */}
                <path d={roundedTopRect(x, paddingT, barW, chartH, r)} fill="#f8fafc" />
                {segs.map((seg, si) => (
                  <path key={si}
                    d={seg.top ? roundedTopRect(x, seg.y, barW, seg.h, r) : `M${x},${seg.y} h${barW} v${seg.h} h${-barW}z`}
                    fill={seg.fill}
                  />
                ))}
                <text x={x + barW / 2} y={baseY + 13} textAnchor="middle" fontSize="7.5"
                  fill={isToday ? '#0C5CAB' : '#94a3b8'}
                  fontWeight={isToday ? '700' : '400'}>
                  {isToday ? '今天' : `${d.date.getMonth() + 1}/${d.date.getDate()}`}
                </text>
              </g>
            );
          })}

          {/* Tooltip */}
          {tooltip && (() => {
            const { d, x: rawX } = tooltip;
            const total = d.success + d.failed + d.running;
            if (total === 0) return null;
            const boxW = 72, boxH = 54, lineH = 13;
            const tx = Math.max(boxW / 2 + 2, Math.min(rawX, svgW - boxW / 2 - 2));
            const ty = 2;
            return (
              <g pointerEvents="none">
                <rect x={tx - boxW / 2} y={ty} width={boxW} height={boxH} rx="5" fill="#1e293b" opacity="0.88" />
                <text x={tx} y={ty + 11} textAnchor="middle" fontSize="8" fill="#94a3b8" fontWeight="500">
                  {d.date.getMonth() + 1}/{d.date.getDate()}
                </text>
                <text x={tx} y={ty + 11 + lineH}   textAnchor="middle" fontSize="8.5" fill="#34d399">成功 {d.success}</text>
                <text x={tx} y={ty + 11 + lineH * 2} textAnchor="middle" fontSize="8.5" fill="#f87171">失败 {d.failed}</text>
                <text x={tx} y={ty + 11 + lineH * 3} textAnchor="middle" fontSize="8.5" fill="#60a5fa">运行 {d.running}</text>
              </g>
            );
          })()}
        </svg>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { data: batches } = useQuery({ queryKey: ['batches'], queryFn: api.batches.list });
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: api.jobs.list });

  const values = {
    totalBatches: batches?.length || 0,
    runningJobs:  jobs?.filter(j => j.status === 'running').length || 0,
    successJobs:  jobs?.filter(j => j.status === 'success').length || 0,
    failedJobs:   jobs?.filter(j => j.status === 'failed').length || 0,
  };

  return (
    <div>
      <div className="flex items-start justify-between mb-7">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 leading-tight">仪表盘</h1>
          <p className="text-sm text-gray-500 mt-0.5">系统评测运行概览</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {STATS.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${s.bg}`}>
              <s.icon size={22} className={s.color} />
            </div>
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">{s.label}</p>
              <p className="text-3xl font-bold text-gray-900 mt-0.5 leading-none">{values[s.key]}</p>
            </div>
          </div>
        ))}
      </div>

      <DailyJobsChart jobs={jobs} />
    </div>
  );
}
