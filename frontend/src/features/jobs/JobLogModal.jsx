import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Modal } from '../../components/ui/Modal';
import { api } from '../../lib/api';
import { useInterval } from '../../hooks/useInterval';
import { Download } from 'lucide-react';

const TABS = [
  { id: 'exec', label: '执行日志' },
  { id: 'framework', label: '框架日志' },
];

export function JobLogModal({ job, open, onClose }) {
  const jobId = job?.id;
  const batchId = job?.batch_id;
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tab, setTab] = useState('exec');

  // 执行日志：后端包裹 docker run 的 stdout/stderr
  const exec = useQuery({
    queryKey: ['jobs', jobId, 'log'],
    queryFn: () => api.jobs.log(jobId),
    enabled: open && !!jobId && tab === 'exec',
    refetchOnWindowFocus: false,
  });

  // 框架日志：ais_bench 框架内部 .out 细节日志
  const framework = useQuery({
    queryKey: ['jobs', jobId, 'framework-log'],
    queryFn: () => api.jobs.frameworkLog(jobId),
    enabled: open && !!jobId && tab === 'framework',
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (open && jobId) {
      setAutoRefresh(true);
      setTab('exec');
    }
  }, [open, jobId]);

  const active = tab === 'exec' ? exec : framework;
  useInterval(() => { if (open && autoRefresh) active.refetch(); }, 60000);

  const logContent = active.data?.log ?? '';
  const noFramework = tab === 'framework' && active.data && active.data.available === false;
  const title = batchId ? `Task ${batchId} · Job ${jobId} 日志` : `Job ${jobId} 日志`;
  const downloadName = batchId
    ? `task_${batchId}_job_${jobId}_${tab}.txt`
    : `job_${jobId}_${tab}.txt`;

  return (
    <Modal open={open} onClose={onClose} title={title} size="xl">
      <div className="space-y-3">
        {/* Tab 切换 */}
        <div className="flex gap-1 border-b border-gray-100">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors ${
                tab === t.id
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-gray-500 cursor-pointer">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            自动刷新 (60s)
          </label>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (!logContent) return;
                const blob = new Blob([logContent], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = downloadName; a.click();
                URL.revokeObjectURL(url);
              }}
              disabled={!logContent}
              className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Download size={14} /> 下载 .txt
            </button>
            <button onClick={() => active.refetch()} className="text-sm text-primary-600 hover:text-primary-700 font-medium transition-colors" disabled={active.isLoading}>
              {active.isLoading ? '加载中...' : '立即刷新'}
            </button>
          </div>
        </div>
        <div className="bg-gray-950 text-gray-100 rounded-xl p-4 max-h-[60vh] min-h-[300px] overflow-auto font-mono text-xs leading-relaxed whitespace-pre-wrap border border-gray-800">
          {logContent || (
            <span className="text-gray-500">
              {active.isLoading
                ? '加载中...'
                : noFramework
                  ? '该执行未产生框架日志（可能尚未运行完成，或框架未输出 .out 文件）'
                  : '暂无日志'}
            </span>
          )}
        </div>
      </div>
    </Modal>
  );
}
