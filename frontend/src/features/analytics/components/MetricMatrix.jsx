import { useState, useMemo } from 'react';

/**
 * 二维矩阵热力表：行=模型，列=任务，格子=某指标（准确率 / 耗时）。
 *
 * baseline（仅模型维度）：选一行模型作基准，其它模型每个格子与基准同任务比较着色。
 * - higherIsBetter=true（准确率）：高于基准→绿，低于→红
 * - higherIsBetter=false（耗时）：低于基准→绿（更快），高于→红
 * - 不选基准则无着色。基准行自身标「基准」、不着色。
 */
export function MetricMatrix({ rows, metric, higherIsBetter }) {
  const [baseline, setBaseline] = useState(null);

  const models = useMemo(
    () => [...new Map(rows.map((r) => [r.model_id, { id: r.model_id, name: r.model_name }])).values()],
    [rows],
  );
  const tasks = useMemo(
    () => [...new Map(rows.map((r) => [r.task_id, { id: r.task_id, key: r.task_key }])).values()],
    [rows],
  );

  const valueOf = (mid, tid) => {
    const row = rows.find((r) => r.model_id === mid && r.task_id === tid);
    return row ? row[metric] : null;
  };

  const fmt = (v) => {
    if (v == null) return '—';
    return metric === 'accuracy' ? `${v.toFixed(1)}%` : fmtDur(Math.round(v));
  };

  function tone(val, baseVal) {
    if (baseline == null || baseVal == null || val == null || val === baseVal) return null;
    const better = higherIsBetter ? val > baseVal : val < baseVal;
    return better
      ? { bg: 'bg-emerald-50', text: 'text-emerald-700' }
      : { bg: 'bg-red-50', text: 'text-red-600' };
  }

  return (
    <div className="space-y-3">
      {/* baseline 选择 + 图例 */}
      <div className="flex items-center gap-3 flex-wrap text-sm">
        <span className="text-gray-500">基准模型：</span>
        <select
          className="input py-1 text-sm w-auto"
          value={baseline ?? ''}
          onChange={(e) => setBaseline(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">不设基准</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        {baseline != null && (
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-300" /> 优于基准</span>
            <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-sm bg-red-300" /> 劣于基准</span>
          </div>
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
        <table className="min-w-full text-[13px] border-collapse">
          <thead>
            <tr className="bg-gradient-to-b from-gray-50 to-gray-100/60 border-b border-gray-200">
              <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400 sticky left-0 bg-gray-50 border-r border-gray-200">
                模型
              </th>
              {tasks.map((t) => (
                <th key={t.id} className="px-3 py-2.5 font-mono text-[11px] font-semibold text-gray-500 text-center min-w-[84px]">
                  {t.key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map((m) => {
              const isBase = m.id === baseline;
              return (
                <tr key={m.id} className={`border-b border-gray-100 last:border-b-0 ${isBase ? 'bg-primary-50/40' : 'hover:bg-gray-50/60'} transition-colors`}>
                  <td
                    className={`px-3 py-2 font-semibold border-r border-gray-200 sticky left-0 max-w-[130px] truncate ${isBase ? 'text-primary-700 bg-primary-50/40' : 'text-gray-800 bg-white'}`}
                    title={m.name}
                  >
                    {m.name}
                    {isBase && <span className="ml-1.5 px-1 py-0.5 rounded bg-primary-100 text-primary-600 text-[9px] font-medium align-middle">基准</span>}
                  </td>
                  {tasks.map((t) => {
                    const val = valueOf(m.id, t.id);
                    const baseVal = baseline != null ? valueOf(baseline, t.id) : null;
                    const c = isBase ? null : tone(val, baseVal);
                    return (
                      <td key={t.id} className="px-2 py-2 text-center">
                        <span className={`inline-block min-w-[52px] px-2 py-1 rounded-md font-semibold tabular-nums ${c ? `${c.bg} ${c.text}` : 'text-gray-700'}`}>
                          {fmt(val)}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fmtDur(s) {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}
