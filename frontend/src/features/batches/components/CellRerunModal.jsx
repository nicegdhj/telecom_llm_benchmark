import { useState, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../../lib/api';
import { Modal } from '../../../components/ui/Modal';

/**
 * 单 cell 重跑弹窗。
 * - what="infer"/"both"：不需要 source_prediction_id
 * - what="eval"：必须从历史推理产物中选一个 success 的 prediction
 */
export function CellRerunModal({ open, onClose, batchId, modelId, taskId, history = [] }) {
  const qc = useQueryClient();
  const [what, setWhat] = useState('both');
  const [sourcePid, setSourcePid] = useState('');
  const [judgeId, setJudgeId] = useState('');

  const { data: judges } = useQuery({ queryKey: ['judges'], queryFn: api.judges.list });

  const inferOptions = useMemo(
    () => history.filter((h) => h.kind === 'infer' && h.status === 'success' && h.prediction_id),
    [history]
  );

  const mut = useMutation({
    mutationFn: () => api.batches.cellRerun(batchId, modelId, taskId, {
      what,
      source_prediction_id: what === 'eval' && sourcePid ? Number(sourcePid) : null,
      judge_id: what === 'eval' && judgeId ? Number(judgeId) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cell', batchId, modelId, taskId] });
      qc.invalidateQueries({ queryKey: ['batches', batchId, 'report'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
      onClose();
    },
  });

  function submit(e) {
    e.preventDefault();
    if (what === 'eval' && !sourcePid) return;
    mut.mutate();
  }

  return (
    <Modal open={open} onClose={onClose} title="重跑此单元" size="md">
      <form onSubmit={submit} className="space-y-5">
        <div>
          <div className="label mb-2">重跑类型</div>
          <div className="space-y-2">
            {[
              { value: 'both', label: '推理 + 评分' },
              { value: 'infer', label: '仅推理' },
              { value: 'eval', label: '仅评分（必须基于已有推理版本）' },
            ].map((opt) => (
              <label key={opt.value} className="flex items-center gap-2 text-sm cursor-pointer text-gray-700">
                <input
                  type="radio"
                  name="what"
                  value={opt.value}
                  checked={what === opt.value}
                  onChange={(e) => setWhat(e.target.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        {what === 'eval' && (
          <div>
            <label className="label">推理版本 <span className="text-red-500">*</span></label>
            {inferOptions.length === 0 ? (
              <p className="text-sm text-red-600">
                此单元尚无成功的推理产物，无法仅评分；请先「推理 + 评分」或「仅推理」
              </p>
            ) : (
              <select
                className="input"
                value={sourcePid}
                onChange={(e) => setSourcePid(e.target.value)}
                required
              >
                <option value="">请选择推理版本</option>
                {inferOptions.map((h) => (
                  <option key={h.prediction_id} value={h.prediction_id}>
                    {h.version_label} · {h.num_samples ?? '?'} 样本 ·{' '}
                    {h.finished_at ? new Date(h.finished_at).toLocaleString() : '—'}
                  </option>
                ))}
              </select>
            )}

            <label className="label mt-4">评分模型</label>
            <select
              className="input"
              value={judgeId}
              onChange={(e) => setJudgeId(e.target.value)}
            >
              <option value="">沿用批次默认评分模型</option>
              {(judges || []).map((j) => (
                <option key={j.id} value={j.id}>
                  {j.name}（{j.model_name}）
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">不选则使用批次创建时配置的评分模型。</p>
          </div>
        )}

        {mut.isError && <p className="text-sm text-red-600">{mut.error.message}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
          <button
            type="submit"
            className="btn-primary"
            disabled={mut.isPending || (what === 'eval' && (!sourcePid || inferOptions.length === 0))}
          >
            {mut.isPending ? '提交中...' : '执行'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
