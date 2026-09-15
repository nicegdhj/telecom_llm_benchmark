import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, transformReportToMatrix } from '../../lib/api';
import { Card, CardBody } from '../../components/ui/Card';
import { ArrowLeft, GitBranch, Table, User, ChevronRight, CheckCircle2, XCircle, Loader2, Circle } from 'lucide-react';
import { userDisplay } from '../../lib/userDisplay';
import { CellDetailPanel } from './components/CellDetailPanel';

const TABS = [
  { id: 'matrix', label: '详情', icon: Table },
  { id: 'revisions', label: '变更日志', icon: GitBranch },
];

export function BatchDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('matrix');

  const { data: batch } = useQuery({ queryKey: ['batches', id], queryFn: () => api.batches.get(Number(id)) });
  const { data: report } = useQuery({
    queryKey: ['batches', id, 'report'],
    queryFn: () => api.batches.report(Number(id)),
  });
  const { data: revisions } = useQuery({ queryKey: ['batches', id, 'revisions'], queryFn: () => api.batches.revisions(Number(id)) });

  const matrixData = report?.rows ? transformReportToMatrix(report.rows) : null;

  return (
    <div>
      <button onClick={() => navigate('/batches')} className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 mb-4 transition-colors">
        <ArrowLeft size={15} /> 返回批次列表
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">{batch?.name || '批次详情'}</h2>
          <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
            <span className="font-mono text-gray-400">#{batch?.id}</span>
            <span className={`px-1.5 py-0.5 rounded-md text-xs font-medium ${
              batch?.mode === 'all' ? 'bg-purple-100 text-purple-700' :
              batch?.mode === 'infer' ? 'bg-primary-100 text-primary-700' : 'bg-amber-100 text-amber-700'
            }`}>{batch?.mode}</span>
            <span className="text-gray-400">{batch?.default_eval_version}</span>
            <span className="text-gray-400">{batch?.created_at ? new Date(batch.created_at).toLocaleString() : '-'}</span>
            {batch?.created_by && (
              <span className="flex items-center gap-1 text-gray-400">
                <User size={13} />
                {userDisplay(batch.created_by)}
              </span>
            )}
            {batch?.last_modified_by && (
              <span className="flex items-center gap-1 text-gray-400">
                最后修改: {userDisplay(batch.last_modified_by)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-gray-100">
        {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors -mb-px ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon size={15} />
              {tab.label}
            </button>
          ))}
      </div>

      {activeTab === 'matrix' && <DetailTab batchId={Number(id)} data={matrixData} />}
      {activeTab === 'revisions' && <RevisionsTab revisions={revisions} />}
    </div>
  );
}


/**
 * 详情 Tab：上半矩阵（按状态着色，可点击下钻），下半 CellDetailPanel。
 *
 * 设计要点：
 * - 颜色按 status 着色：成功=绿、失败=红、运行中=蓝、待执行=灰、未跑=空白
 *   不再按 accuracy 阈值上色，避免「跑通了但 0% 准确率」被误显示为红
 * - 选中态：左侧加蓝边 + 深底；hover：ring
 * - 表格保持紧凑；左侧"模型"列 sticky
 */
function DetailTab({ batchId, data }) {
  const [selected, setSelected] = useState(null);
  if (!data) return <div className="text-gray-400">加载中...</div>;
  const { models, tasks, matrix } = data;

  return (
    <div className="space-y-5">
      <Card>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full text-[13px] border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b-2 border-gray-200">
                  <th className="px-4 py-3 font-semibold text-gray-600 text-left sticky left-0 bg-gray-50 border-r border-gray-200 min-w-[160px]">
                    模型 \ 任务
                  </th>
                  {tasks.map((t) => (
                    <th key={t.id} className="px-3 py-3 font-mono text-xs font-semibold text-gray-600 text-center min-w-[130px]">
                      {t.key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {models.map((m, mi) => (
                  <tr key={m.id} className="border-b border-gray-100 last:border-b-0">
                    <td className="px-4 py-3 font-semibold text-gray-800 bg-gray-50/50 border-r border-gray-200 sticky left-0">
                      {m.name}
                    </td>
                    {tasks.map((t, ti) => {
                      const cell = matrix[mi][ti];
                      const isSelected = selected?.modelId === m.id && selected?.taskId === t.id;
                      return (
                        <MatrixCell
                          key={t.id}
                          cell={cell}
                          isSelected={isSelected}
                          onClick={() => setSelected({ modelId: m.id, taskId: t.id, modelName: m.name, taskKey: t.key })}
                        />
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <p className="text-xs text-gray-400 -mt-2 px-1">
        点击矩阵中的格子，下方展示该模型 × 任务的版本历史、日志、与单元重跑入口。
      </p>

      {selected ? (
        <CellDetailPanel
          batchId={batchId}
          modelId={selected.modelId}
          taskId={selected.taskId}
          modelName={selected.modelName}
          taskKey={selected.taskKey}
        />
      ) : (
        <Card>
          <CardBody className="text-sm text-gray-400 py-6 text-center">
            选择上方矩阵中的任一格子查看单元详情
          </CardBody>
        </Card>
      )}
    </div>
  );
}


/**
 * 单个矩阵格子。按 status 上色：
 *   eval_done / success → 绿；infer_done → 蓝（半成品）；
 *   failed / cancelled → 红；running → 蓝（带 loader）；pending → 灰
 */
function MatrixCell({ cell, isSelected, onClick }) {
  const s = cell?.status;
  let palette, Icon;
  if (!cell) {
    palette = { bg: 'bg-white', text: 'text-gray-300', border: 'border-gray-100' };
    Icon = null;
  } else if (s === 'eval_done' || s === 'success') {
    palette = { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', accent: 'text-emerald-700' };
    Icon = CheckCircle2;
  } else if (s === 'infer_done') {
    palette = { bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200', accent: 'text-sky-700' };
    Icon = Circle;
  } else if (s === 'failed' || s === 'cancelled' || s === 'timeout') {
    palette = { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', accent: 'text-red-700' };
    Icon = XCircle;
  } else if (s === 'running') {
    palette = { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', accent: 'text-blue-700' };
    Icon = Loader2;
  } else {
    palette = { bg: 'bg-gray-50', text: 'text-gray-500', border: 'border-gray-200', accent: 'text-gray-500' };
    Icon = Circle;
  }

  const selRing = isSelected ? 'ring-2 ring-primary-500 ring-offset-1 z-10' : '';

  return (
    <td
      onClick={cell ? onClick : undefined}
      className={`relative p-0 ${cell ? 'cursor-pointer group' : 'cursor-default'}`}
      title={cell ? `点击查看详情 · 状态：${s}` : ''}
    >
      <div className={`m-1 p-2.5 rounded-lg border ${palette.bg} ${palette.border} ${selRing}
                       transition-all ${cell ? 'group-hover:shadow-md group-hover:scale-[1.02]' : ''}`}>
        {cell ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className={`text-lg font-bold ${palette.accent}`}>
                {cell.accuracy != null ? `${cell.accuracy.toFixed(1)}%` : '—'}
              </span>
              {Icon && (
                <Icon size={14} className={`${palette.accent} ${s === 'running' ? 'animate-spin' : ''}`} />
              )}
            </div>
            <div className={`text-[11px] ${palette.text} opacity-70`}>
              {cell.num_samples != null ? `${cell.num_samples} 样本` : '—'}
            </div>
            <div className={`text-[11px] font-medium ${palette.accent} flex items-center gap-1`}>
              <span>{statusLabel(s)}</span>
              <ChevronRight size={11} className="opacity-0 group-hover:opacity-60 transition-opacity ml-auto" />
            </div>
          </div>
        ) : (
          <div className="text-center text-gray-300 text-sm py-3">—</div>
        )}
      </div>
    </td>
  );
}


function statusLabel(s) {
  return {
    eval_done: '已评分',
    infer_done: '仅推理',
    failed: '失败',
    cancelled: '已取消',
    timeout: '超时',
    running: '运行中',
    pending: '待执行',
    success: '成功',
  }[s] || s || '—';
}


function RevisionsTab({ revisions }) {
  if (!revisions?.length) return <div className="text-gray-400">暂无变更记录</div>;
  return (
    <Card>
      <CardBody className="p-0">
        <table className="min-w-full divide-y divide-gray-100">
          <thead className="bg-gray-50">
            <tr>
              {['Rev', '类型', '变更说明', '操作人', '时间'].map(h => (
                <th key={h} className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {revisions.map(r => (
              <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 text-sm font-semibold text-gray-900">{r.rev_num}</td>
                <td className="px-6 py-4 text-sm">
                  <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${
                    r.change_type === 'create' ? 'bg-primary-100 text-primary-700' :
                    r.change_type === 'rerun' ? 'bg-amber-100 text-amber-700' :
                    r.change_type === 'rerun_cell' ? 'bg-amber-50 text-amber-700' :
                    r.change_type === 'switch_pointer' ? 'bg-purple-50 text-purple-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>{r.change_type}</span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{r.change_summary || '—'}</td>
                <td className="px-6 py-4 text-sm text-gray-600">{r.actor ? userDisplay(r.actor) : '—'}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{new Date(r.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
