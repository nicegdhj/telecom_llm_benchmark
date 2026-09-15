import { useState, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const CHART = {
  grid: '#f3f4f6',
  tick: '#9ca3af',
  bar: '#0C5CAB',
  tooltip: { bg: '#fff', border: '#e5e7eb', text: '#111827' },
};

export function AccuracyBarChart({ rows }) {
  const [mode, setMode] = useState('byTask');
  const [selectedModel, setSelectedModel] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);

  const models = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.model_id, { id: r.model_id, name: r.model_name }])).values()], [rows]);
  const tasks  = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.task_id,  { id: r.task_id,  key: r.task_key  }])).values()], [rows]);

  const chartData = useMemo(() => {
    if (mode === 'byTask' && selectedModel)
      return tasks.map(t => { const row = rows.find(r => r.model_id === selectedModel && r.task_id === t.id); return { name: t.key, accuracy: row?.accuracy ?? 0 }; }).filter(d => d.accuracy > 0).sort((a, b) => b.accuracy - a.accuracy);
    if (mode === 'byModel' && selectedTask)
      return models.map(m => { const row = rows.find(r => r.model_id === m.id && r.task_id === selectedTask); return { name: m.name, accuracy: row?.accuracy ?? 0 }; }).filter(d => d.accuracy > 0).sort((a, b) => b.accuracy - a.accuracy);
    return [];
  }, [mode, selectedModel, selectedTask, rows, models, tasks]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">分析维度:</span>
          <select className="input py-1 text-sm" value={mode} onChange={e => setMode(e.target.value)}>
            <option value="byTask">单模型 × 多任务</option>
            <option value="byModel">多模型 × 单任务</option>
          </select>
        </div>
        {mode === 'byTask' && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">选择模型:</span>
            <select className="input py-1 text-sm" value={selectedModel || ''} onChange={e => setSelectedModel(Number(e.target.value))}>
              <option value="">请选择</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
        {mode === 'byModel' && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">选择任务:</span>
            <select className="input py-1 text-sm" value={selectedTask || ''} onChange={e => setSelectedTask(Number(e.target.value))}>
              <option value="">请选择</option>
              {tasks.map(t => <option key={t.id} value={t.id}>{t.key}</option>)}
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
              <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: CHART.tick }} unit="%" />
              <Tooltip formatter={(v) => [`${v.toFixed(1)}%`, '准确率']} contentStyle={{ borderRadius: 10, border: `1px solid ${CHART.tooltip.border}`, backgroundColor: CHART.tooltip.bg, color: CHART.tooltip.text, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
              <Bar dataKey="accuracy" fill={CHART.bar} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-80 flex items-center justify-center text-gray-400 bg-gray-50 rounded-xl border border-gray-100">
          <p>请选择模型和任务以查看图表</p>
        </div>
      )}
    </div>
  );
}
