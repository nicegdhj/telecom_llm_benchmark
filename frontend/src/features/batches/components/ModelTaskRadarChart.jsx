import { useState, useMemo } from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const CHART = {
  grid: '#e5e7eb',
  tick: '#6b7280',
  tooltip: { bg: '#fff', border: '#e5e7eb', text: '#111827' },
};
const colors = ['#0C5CAB', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

export function ModelTaskRadarChart({ rows }) {
  const [selectedModels, setSelectedModels] = useState([]);

  const models = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.model_id, { id: r.model_id, name: r.model_name }])).values()], [rows]);
  const tasks  = useMemo(() => [...new Map(rows.filter(r => r.accuracy != null).map(r => [r.task_id,  { id: r.task_id,  key: r.task_key  }])).values()], [rows]);

  const chartData = useMemo(() => tasks.map(t => {
    const point = { task: t.key };
    for (const m of models) { const row = rows.find(r => r.model_id === m.id && r.task_id === t.id); point[m.name] = row?.accuracy ?? 0; }
    return point;
  }), [rows, models, tasks]);

  function toggleModel(id) {
    setSelectedModels(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  const activeModels = selectedModels.length > 0 ? models.filter(m => selectedModels.includes(m.id)) : models.slice(0, 3);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-gray-500">对比模型:</span>
        {models.map(m => (
          <button
            key={m.id}
            onClick={() => toggleModel(m.id)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all border ${
              (selectedModels.length === 0 ? models.indexOf(m) < 3 : selectedModels.includes(m.id))
                ? 'bg-primary-600 text-white border-primary-600 shadow-sm'
                : 'bg-white text-gray-600 border-gray-200 hover:border-primary-300 hover:text-primary-600'
            }`}
          >
            {m.name}
          </button>
        ))}
        <span className="text-xs text-gray-400">点击切换</span>
      </div>
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} margin={{ top: 20, right: 80, bottom: 20, left: 80 }}>
            <PolarGrid stroke={CHART.grid} />
            <PolarAngleAxis dataKey="task" tick={{ fontSize: 11, fill: CHART.tick }} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10, fill: CHART.tick }} />
            {activeModels.map((m, i) => (
              <Radar key={m.id} name={m.name} dataKey={m.name} stroke={colors[i % colors.length]} fill={colors[i % colors.length]} fillOpacity={0.12} strokeWidth={2} />
            ))}
            <Tooltip formatter={(v, name) => [`${v.toFixed(1)}%`, name]} contentStyle={{ borderRadius: 10, border: `1px solid ${CHART.tooltip.border}`, backgroundColor: CHART.tooltip.bg, color: CHART.tooltip.text, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
            <Legend wrapperStyle={{ fontSize: 12, color: CHART.tick }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
