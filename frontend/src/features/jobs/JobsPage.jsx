import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { Card, CardBody } from '../../components/ui/Card';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { JobLogModal } from './JobLogModal';
import { XCircle, AlertTriangle } from 'lucide-react';
import { userDisplay } from '../../lib/userDisplay';

const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '运行中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
];

function toBeijingTime(utcStr) {
  if (!utcStr) return '—';
  const d = new Date(utcStr.endsWith('Z') ? utcStr : utcStr + 'Z');
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

const CANCELLABLE = new Set(['pending', 'running']);

export function JobsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [batchIdFilter, setBatchIdFilter] = useState('');
  const [logJob, setLogJob] = useState(null);
  const [logOpen, setLogOpen] = useState(false);
  const [confirmCancelId, setConfirmCancelId] = useState(null);

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs', { status: statusFilter, batch_id: batchIdFilter }],
    queryFn: () => {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const bid = batchIdFilter.trim();
      if (bid && /^\d+$/.test(bid)) {
        params.batch_id = parseInt(bid, 10);
      }
      return api.jobs.list(params);
    },
    refetchOnMount: 'always',
  });

  const cancelMut = useMutation({
    mutationFn: (id) => api.jobs.cancel(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); setConfirmCancelId(null); },
  });

  function openLog(job) { setLogJob(job); setLogOpen(true); }

  return (
    <div>
      <div className="flex items-start justify-between mb-7">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 leading-tight">执行记录</h1>
          <p className="text-sm text-gray-500 mt-0.5">任务执行详情与状态追踪</p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          {STATUS_FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-semibold transition-all ${
                statusFilter === f.value
                  ? 'text-white shadow-sm'
                  : 'border border-gray-200 text-gray-600 hover:border-gray-300 bg-white'
              }`}
              style={statusFilter === f.value ? { background: '#0C5CAB' } : {}}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* 搜索框 */}
        <div className="relative flex items-center">
          <input
            type="text"
            placeholder="输入测评任务ID搜索..."
            value={batchIdFilter}
            onChange={(e) => {
              const val = e.target.value;
              if (val === '' || /^\d+$/.test(val)) {
                setBatchIdFilter(val);
              }
            }}
            className="w-[200px] pl-3 pr-8 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
          />
          {batchIdFilter && (
            <button
              onClick={() => setBatchIdFilter('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs transition-colors"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      <Card>
        <CardBody className="p-0">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-gray-100">
                {['测评任务ID', '数据集', '类型', '版本号', '状态', '模型', '提交人', '创建时间', '日志', '操作'].map(h => (
                  <th key={h} className="px-4 py-3 text-center text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {isLoading ? (
                <tr><td colSpan={10} className="px-4 py-8 text-center text-sm text-gray-400">加载中...</td></tr>
              ) : jobs?.length === 0 ? (
                <tr><td colSpan={10} className="px-4 py-12 text-center text-sm text-gray-400">暂无记录</td></tr>
              ) : jobs?.map(job => (
                <tr key={job.id} className="trow transition-colors">
                  <td className="px-4 py-3.5 text-center text-[13px] text-primary-600 font-medium">
                    {job.batch_id ?? '—'}
                  </td>
                  <td className="px-4 py-3.5 text-center text-[13px] text-gray-700 font-medium">
                    {job.task_key ?? '—'}
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                      job.type === 'infer' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                    }`}>{job.type}</span>
                  </td>
                  <td className="px-4 py-3.5 text-center text-[12px] font-mono text-gray-600">
                    {job.version_label ?? '—'}
                  </td>
                  <td className="px-4 py-3.5 text-center"><StatusBadge status={job.status} /></td>
                  <td className="px-4 py-3.5 text-center text-[13px] text-gray-700 max-w-[160px] truncate">{job.model_name || '—'}</td>
                  <td className="px-4 py-3.5 text-center text-[12px] text-gray-500">
                    {job.created_by ? userDisplay(job.created_by) : '—'}
                  </td>
                  <td className="px-4 py-3.5 text-center text-[12px] text-gray-500">{toBeijingTime(job.created_at)}</td>
                  <td className="px-4 py-3.5 text-center">
                    <button
                      onClick={() => openLog(job)}
                      className="text-[12px] text-primary-600 hover:text-primary-700 hover:bg-blue-50 px-2.5 py-1 rounded-lg transition-colors font-medium"
                    >
                      查看
                    </button>
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    {CANCELLABLE.has(job.status) ? (
                      confirmCancelId === job.id ? (
                        <div className="flex items-center gap-1 justify-center">
                          <AlertTriangle size={13} className="text-amber-500" />
                          <span className="text-xs text-gray-500">确认？</span>
                          <button onClick={() => cancelMut.mutate(job.id)} disabled={cancelMut.isPending} className="text-xs text-red-600 font-medium hover:text-red-700 px-1">确认</button>
                          <button onClick={() => setConfirmCancelId(null)} className="text-xs text-gray-400 hover:text-gray-600 px-1">取消</button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmCancelId(job.id)}
                          className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded-lg transition-colors mx-auto"
                        >
                          <XCircle size={13} /> 取消
                        </button>
                      )
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-gray-300 px-2 py-1 mx-auto w-fit cursor-not-allowed select-none">
                        <XCircle size={13} /> 取消
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <JobLogModal job={logJob} open={logOpen} onClose={() => setLogOpen(false)} />
    </div>
  );
}
