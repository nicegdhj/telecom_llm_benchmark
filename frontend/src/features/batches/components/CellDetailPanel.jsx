import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../../lib/api';
import { Card, CardBody } from '../../../components/ui/Card';
import { StatusBadge } from '../../../components/ui/StatusBadge';
import { JobLogModal } from '../../jobs/JobLogModal';
import { CellRerunModal } from './CellRerunModal';
import { CellResultPanel } from './CellResultPanel';
import { FileText, RotateCcw, GitMerge, BarChart3 } from 'lucide-react';

/**
 * 单 cell 详情面板：展示历史时间线 + 三要素 + 切版本 + 单元重跑入口。
 * 接收 cell 标识（batchId, modelId, taskId, modelName, taskKey），通过 cellDetail API 拉数据。
 */
export function CellDetailPanel({ batchId, modelId, taskId, modelName, taskKey }) {
  const qc = useQueryClient();
  const [logJob, setLogJob] = useState(null);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [resultJobId, setResultJobId] = useState(null);

  const { data: detail, isLoading } = useQuery({
    queryKey: ['cell', batchId, modelId, taskId],
    queryFn: () => api.batches.cellDetail(batchId, modelId, taskId),
    enabled: !!batchId && !!modelId && !!taskId,
  });

  const switchMut = useMutation({
    mutationFn: ({ pid, eid }) => api.batches.cellSwitchPointer(batchId, modelId, taskId, {
      current_prediction_id: pid,
      current_evaluation_id: eid,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cell', batchId, modelId, taskId] });
      qc.invalidateQueries({ queryKey: ['batches', batchId, 'report'] });
      qc.invalidateQueries({ queryKey: ['batches', batchId, 'revisions'] });
    },
  });

  if (isLoading || !detail) return <div className="text-gray-400 text-sm p-4">加载中...</div>;

  const history = detail.history || [];
  const currentInfer = history.find(
    (h) => h.kind === 'infer' && h.prediction_id === detail.current_prediction_id,
  );
  const currentScore = history.find(
    (h) => h.kind === 'eval' && h.evaluation_id === detail.current_evaluation_id,
  );

  return (
    <Card>
      <CardBody className="space-y-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-base font-semibold text-gray-800">
              {modelName} · <span className="font-mono text-gray-500">{taskKey}</span>
            </div>
            <div className="text-xs text-gray-500 mt-1">
              当前版本：
              <span className="font-mono ml-1">
                {currentInfer?.version_label || '—'}
              </span>
              {' + '}
              <span className="font-mono">{currentScore?.version_label || '—'}</span>
            </div>
          </div>
          <button
            className="btn-primary flex items-center gap-1.5 text-sm"
            onClick={() => setRerunOpen(true)}
          >
            <RotateCcw size={14} /> 重跑此单元
          </button>
        </div>

        {/* 三要素卡片 */}
        <div className="grid grid-cols-3 gap-3">
          <KpiCard label="准确率" value={currentScore?.accuracy != null ? `${currentScore.accuracy.toFixed(2)}%` : '—'} tone="primary" />
          <KpiCard
            label="耗时"
            value={
              (() => {
                const infer = currentInfer?.duration_sec ?? null;
                const score = currentScore?.duration_sec ?? null;
                if (infer == null && score == null) return '—';
                const parts = [];
                if (infer != null) parts.push(`推理 ${Math.round(infer)}s`);
                if (score != null) parts.push(`评分 ${Math.round(score)}s`);
                return parts.join(' / ');
              })()
            }
          />
          <KpiCard label="样本数" value={currentScore?.num_samples ?? currentInfer?.num_samples ?? '—'} />
        </div>

        {/* 历史时间线 */}
        <div>
          <div className="label flex items-center gap-2 mb-2">
            <GitMerge size={14} className="text-gray-400" /> 历史时间线
          </div>
          <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
            {history.length === 0 && (
              <div className="text-sm text-gray-400 px-3 py-4">暂无执行记录</div>
            )}
            {history.map((h) => {
              const isCurrent =
                (h.kind === 'infer' && h.prediction_id === detail.current_prediction_id) ||
                (h.kind === 'eval' && h.evaluation_id === detail.current_evaluation_id);
              return (
                <div
                  key={`${h.kind}-${h.job_id}`}
                  className={`px-3 py-2 text-sm flex items-center gap-3 ${
                    h.status === 'failed' || h.status === 'timeout' ? 'bg-red-50/40' : ''
                  } ${isCurrent ? 'ring-1 ring-primary-200 bg-primary-50/40' : ''}`}
                >
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                    h.kind === 'infer' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                  }`}>{h.kind === 'infer' ? '推理' : '评分'}</span>
                  <span className="font-mono text-gray-700 min-w-[80px]">{h.version_label || `job#${h.job_id}`}</span>
                  <StatusBadge status={h.status} />
                  <span className="text-gray-500 flex-1">
                    {h.kind === 'eval' && h.based_on_infer && (
                      <span className="text-gray-400">基于 <span className="font-mono">{h.based_on_infer}</span> · </span>
                    )}
                    {h.accuracy != null && <span className="font-semibold text-emerald-700">{h.accuracy.toFixed(2)}%</span>}
                    {h.duration_sec != null && <span className="ml-2 text-gray-400">{Math.round(h.duration_sec)}s</span>}
                    {h.finished_at && <span className="ml-2 text-gray-400">{new Date(h.finished_at).toLocaleString()}</span>}
                    {h.error_msg && <span className="ml-2 text-red-600">err: {h.error_msg.slice(0, 80)}</span>}
                  </span>
                  <div className="flex items-center gap-2">
                    {!isCurrent && (h.kind === 'infer' ? h.prediction_id : h.evaluation_id) && h.status === 'success' && (
                      <button
                        className="text-xs text-primary-600 hover:underline"
                        onClick={() => {
                          if (h.kind === 'infer') {
                            switchMut.mutate({ pid: h.prediction_id, eid: null });
                          } else {
                            // 评分指针的切换：必须跟它所基于的 prediction 一致
                            switchMut.mutate({
                              pid: h.source_prediction_id ?? detail.current_prediction_id,
                              eid: h.evaluation_id,
                            });
                          }
                        }}
                        disabled={switchMut.isPending}
                      >
                        切到此版本
                      </button>
                    )}
                    {h.kind === 'eval' && h.status === 'success' && h.evaluation_id && (
                      <button
                        className={`text-xs flex items-center gap-1 ${
                          resultJobId === h.job_id
                            ? 'text-primary-600 font-medium'
                            : 'text-gray-500 hover:text-gray-700'
                        }`}
                        onClick={() => setResultJobId(resultJobId === h.job_id ? null : h.job_id)}
                      >
                        <BarChart3 size={12} /> 结果展示
                      </button>
                    )}
                    <button
                      className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                      onClick={() => setLogJob({ id: h.job_id, batch_id: batchId })}
                      disabled={!h.log_path}
                    >
                      <FileText size={12} /> 日志
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          {switchMut.isError && (
            <p className="text-sm text-red-600 mt-2">{switchMut.error.message}</p>
          )}

          {resultJobId && (
            <CellResultPanel jobId={resultJobId} onClose={() => setResultJobId(null)} />
          )}
        </div>
      </CardBody>

      <JobLogModal
        job={logJob}
        open={!!logJob}
        onClose={() => setLogJob(null)}
      />
      <CellRerunModal
        open={rerunOpen}
        onClose={() => setRerunOpen(false)}
        batchId={batchId}
        modelId={modelId}
        taskId={taskId}
        history={history}
      />
    </Card>
  );
}


function KpiCard({ label, value, tone }) {
  const toneClass = tone === 'primary' ? 'text-primary-700' : 'text-gray-800';
  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-xl font-bold mt-1 ${toneClass}`}>{value}</div>
    </div>
  );
}
