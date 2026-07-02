import { useState, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const CHART = {
  grid: '#f3f4f6',
  tick: '#9ca3af',
  bar: '#6366f1',
  tooltip: { bg: '#fff', border: '#e5e7eb', text: '#111827' },
};

export function DurationBarChart({ rows }) {
  const [mode, setMode] = useState('byModel');
  const [selectedModel, setSelectedModel] = useState(null);

  const models = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.model_id, { id: r.model_id, name: r.model_name }])).values()], [rows]);
  const tasks  = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.task_id,  { id: r.task_id,  key: r.task_key  }])).values()], [rows]);

  const chartData = useMemo(() => {
    if (mode === 'byModel')
      return models.map(m => { const total = rows.filter(r => r.model_id === m.id).reduce((s, r) => s + (r.duration_sec || 0), 0); return { name: m.name, duration: Math.round(total) }; }).filter(d => d.duration > 0).sort((a, b) => b.duration - a.duration);
    if (mode === 'byTask')
      return tasks.map(t => { const total = rows.filter(r => r.task_id === t.id).reduce((s, r) => s + (r.duration_sec || 0), 0); return { name: t.key, duration: Math.round(total) }; }).filter(d => d.duration > 0).sort((a, b) => b.duration - a.duration);
    if (mode === 'singleModel' && selectedModel)
      return tasks.map(t => { const row = rows.find(r => r.model_id === selectedModel && r.task_id === t.id); return { name: t.key, duration: Math.round(row?.duration_sec || 0) }; }).filter(d => d.duration > 0);
    return [];
  }, [mode, selectedModel, rows, models, tasks]);

  function fmt(s) {
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">分析维度:</span>
          <select className="input py-1 text-sm" value={mode} onChange={e => setMode(e.target.value)}>
            <option value="byModel">多模型总耗时</option>
            <option value="byTask">多任务总耗时</option>
            <option value="singleModel">单模型 × 多任务</option>
          </select>
        </div>
        {mode === 'singleModel' && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">选择模型:</span>
            <select className="input py-1 text-sm" value={selectedModel || ''} onChange={e => setSelectedModel(Number(e.target.value))}>
              <option value="">请选择</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
      </div>
      {chartData.length > 0 ? (
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis dataKey="name" tick={{ fontSize: 12, fill: CHART.tick }} />
              <YAxis tick={{ fontSize: 12, fill: CHART.tick }} label={{ value: '秒', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: CHART.tick } }} />
              <Tooltip formatter={(v) => [fmt(v), '耗时']} contentStyle={{ borderRadius: 10, border: `1px solid ${CHART.tooltip.border}`, backgroundColor: CHART.tooltip.bg, color: CHART.tooltip.text, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
              <Bar dataKey="duration" fill={CHART.bar} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-80 flex items-center justify-center text-gray-400 bg-gray-50 rounded-xl border border-gray-100">
          <p>请选择维度以查看耗时图表</p>
        </div>
      )}
    </div>
  );
}
