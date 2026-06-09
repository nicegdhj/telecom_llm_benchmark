import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../../lib/api';
import { Card, CardBody, CardHeader } from '../../../components/ui/Card';
import { MetricMatrix } from './MetricMatrix';
import { ModelTaskRadarChart } from '../../batches/components/ModelTaskRadarChart';
import { Table as TableIcon, BarChart3, Activity, Radar, Info } from 'lucide-react';

const SECTIONS = [
  { id: 'table',    label: '明细表',    icon: TableIcon },
  { id: 'accuracy', label: '准确率',    icon: BarChart3 },
  { id: 'duration', label: '耗时',      icon: Activity },
  { id: 'radar',    label: '能力雷达',  icon: Radar },
];

/**
 * 测评分析的对比视图。
 * - 没选任何 evaluation 时：占位提示
 * - 选了之后：上方切 section（表格/准确率/耗时/雷达），渲染对应视图
 *
 * 复用 features/batches/components 里的 3 个 chart 组件，
 * 它们消费的 row 字段 (model_id/model_name/task_id/task_key/accuracy/num_samples/duration_sec)
 * 与 /evaluations/search 输出完全兼容。
 */
export function ComparisonView({ selectedIds = [] }) {
  const [active, setActive] = useState('table');

  // 精确按选中的 id 查询，避免「全量 1000 条再过滤、超量丢失」
  const { data: rows = [] } = useQuery({
    queryKey: ['evaluations-by-ids', selectedIds],
    queryFn: () => api.evaluations.search({ eval_ids: selectedIds, limit: 1000 }),
    enabled: selectedIds.length > 0,
  });

  if (selectedIds.length === 0) {
    return (
      <Card>
        <CardBody className="text-sm text-gray-400 py-10 text-center">
          <BarChart3 size={28} className="mx-auto text-gray-300 mb-2" />
          上方勾选若干 evaluation 后，这里展示对比明细与图表
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-sm font-semibold text-gray-700">对比视图 · 共 {rows.length} 条</h3>
          <div className="flex gap-1">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                  active === s.id
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <s.icon size={13} /> {s.label}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardBody>
        {active === 'table' && <DetailTable rows={rows} />}
        {active === 'accuracy' && <MetricMatrix rows={rows} metric="accuracy" higherIsBetter />}
        {active === 'duration' && <MetricMatrix rows={rows} metric="duration" higherIsBetter={false} />}
        {active === 'radar' && (
          <div className="space-y-3">
            <div className="flex gap-2 text-xs text-gray-500 bg-blue-50/50 border border-blue-100 rounded-lg px-3 py-2">
              <Info size={14} className="text-blue-400 flex-shrink-0 mt-0.5" />
              <p>
                能力雷达：每个<b>角</b>是一个任务（准确率 0–100%），每个<b>模型</b>是一圈多边形。
                圈越鼓综合越强，某个角凹进去说明该模型在那个任务是短板。适合 3–6 个任务、2–4 个模型横向比；任务太少时建议看「准确率矩阵」。
              </p>
            </div>
            <ModelTaskRadarChart rows={rows} />
          </div>
        )}
      </CardBody>
    </Card>
  );
}


function DetailTable({ rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm divide-y divide-gray-100">
        <thead className="bg-gray-50">
          <tr>
            {['#', '模型', '任务', '批次', '版本', '状态', '准确率', '样本数', '耗时(s)', '完成时间'].map((h) => (
              <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-gray-500">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-gray-50">
              <td className="px-3 py-2 font-mono text-gray-400">#{r.id}</td>
              <td className="px-3 py-2 font-medium text-gray-800">{r.model_name}</td>
              <td className="px-3 py-2 font-mono text-gray-600">{r.task_key}</td>
              <td className="px-3 py-2 text-gray-500">{r.batch_name}</td>
              <td className="px-3 py-2 font-mono text-gray-500">{r.version_label}</td>
              <td className="px-3 py-2">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                  r.status === 'success' ? 'bg-emerald-50 text-emerald-700' :
                  r.status === 'failed' ? 'bg-red-50 text-red-700' :
                  'bg-gray-100 text-gray-600'
                }`}>{r.status}</span>
              </td>
              <td className="px-3 py-2 font-semibold text-emerald-700">
                {r.accuracy != null ? `${r.accuracy.toFixed(2)}%` : '—'}
              </td>
              <td className="px-3 py-2 text-gray-500">{r.num_samples ?? '—'}</td>
              <td className="px-3 py-2 text-gray-500">{r.duration_sec != null ? Math.round(r.duration_sec) : '—'}</td>
              <td className="px-3 py-2 text-gray-500 text-xs">
                {r.finished_at ? new Date(r.finished_at).toLocaleString() : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
