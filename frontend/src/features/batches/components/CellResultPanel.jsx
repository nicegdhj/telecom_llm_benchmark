import { useQuery } from '@tanstack/react-query';
import { api } from '../../../lib/api';
import { X } from 'lucide-react';

const KIND_META = {
  good: { label: '好', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  empty_output: { label: '空输出', cls: 'bg-gray-100 text-gray-600 border-gray-200' },
  parse_fail: { label: '解析失败', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
};

/**
 * 单次评分的"结果展示"：质量统计 + 抽样前 10 条 details。
 * 好 = 推理输出非空且解析成功（无论答案对错）。
 */
export function CellResultPanel({ jobId, onClose }) {
  const { data, isLoading } = useQuery({
    queryKey: ['jobs', jobId, 'quality'],
    queryFn: () => api.jobs.quality(jobId),
    enabled: !!jobId,
    refetchOnWindowFocus: false,
  });

  const pct = (n) => (data?.total ? Math.round((n / data.total) * 100) : 0);

  return (
    <div className="mt-4 border border-gray-200 rounded-xl bg-white overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-100">
        <span className="text-sm font-semibold text-gray-700">
          结果展示 <span className="text-gray-400 font-normal">· job#{jobId}</span>
        </span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <X size={16} />
        </button>
      </div>

      {isLoading ? (
        <div className="px-4 py-6 text-sm text-gray-400">加载中...</div>
      ) : !data?.available ? (
        <div className="px-4 py-6 text-sm text-gray-400">该评分暂无可展示的结果明细（可能未产出 details）。</div>
      ) : (
        <div className="p-4 space-y-4">
          {/* 质量统计 */}
          <div>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-sm text-gray-500">执行质量</span>
              <span className="text-lg font-bold text-emerald-600">{pct(data.good)}%</span>
              <span className="text-xs text-gray-400">好 {data.good} / {data.total}</span>
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div className="bg-emerald-500" style={{ width: `${pct(data.good)}%` }} title={`好 ${data.good}`} />
              <div className="bg-gray-300" style={{ width: `${pct(data.empty_output)}%` }} title={`空输出 ${data.empty_output}`} />
              <div className="bg-amber-500" style={{ width: `${pct(data.parse_fail)}%` }} title={`解析失败 ${data.parse_fail}`} />
            </div>
            <div className="flex gap-4 mt-2 text-xs text-gray-500">
              <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />好 {data.good}</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1" />空输出 {data.empty_output}</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />解析失败 {data.parse_fail}</span>
            </div>
          </div>

          {/* 抽样明细 */}
          <div>
            <div className="text-sm text-gray-500 mb-2">抽样明细（前 {data.samples?.length || 0} 条）</div>
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {(data.samples || []).map((s, i) => {
                const meta = KIND_META[s.kind] || KIND_META.good;
                return (
                  <div key={i} className="border border-gray-100 rounded-lg p-3 bg-gray-50/60">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[11px] text-gray-400 font-mono">#{i + 1}</span>
                      <span className={`text-[11px] px-1.5 py-0.5 rounded border ${meta.cls}`}>{meta.label}</span>
                      <span className="text-[11px] text-gray-400 ml-auto">评分: <span className="font-mono text-gray-600">{s.eval_res || '—'}</span></span>
                    </div>
                    <Field label="输入" value={s.prompt} />
                    <Field label="模型输出" value={s.prediction} />
                    <Field label="参考答案" value={s.gold} />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="mb-1.5 last:mb-0">
      <div className="text-[11px] text-gray-400 mb-0.5">{label}</div>
      <pre className="text-xs text-gray-700 whitespace-pre-wrap break-words font-sans bg-white border border-gray-100 rounded px-2 py-1.5 max-h-40 overflow-y-auto">
        {value || <span className="text-gray-300">（空）</span>}
      </pre>
    </div>
  );
}
