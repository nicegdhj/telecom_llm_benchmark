import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../../lib/api';

function toBeijingTime(utcStr) {
  if (!utcStr) return '—';
  const d = new Date(utcStr.endsWith('Z') ? utcStr : utcStr + 'Z');
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}
import { Card, CardBody } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { Plus, Activity, Info, RotateCcw } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const STATUS_CONFIG = {
  pending:  { label: '待执行', cls: 'bg-gray-100 text-gray-500' },
  running:  { label: '执行中', cls: 'bg-blue-100 text-blue-600' },
  success:  { label: '已完成', cls: 'bg-emerald-100 text-emerald-700' },
  failed:   { label: '有失败', cls: 'bg-red-100 text-red-600' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}>
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
      )}
      {cfg.label}
    </span>
  );
}

export function BatchesPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { canWrite } = useAuthStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [taskVersions, setTaskVersions] = useState({}); // task_id -> list of versions
  const [selectedConfig, setSelectedConfig] = useState(null);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [form, setForm] = useState({
    name: '', mode: 'all', model_ids: [], task_ids: [],
    task_version_map: {},
    default_eval_version: 'eval_init', default_judge_id: '', notes: '',
  });

  const { data: batches, isLoading } = useQuery({ queryKey: ['batches'], queryFn: api.batches.list });
  const { data: models } = useQuery({ queryKey: ['models'], queryFn: api.models.list });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: api.tasks.list });
  const { data: judges } = useQuery({ queryKey: ['judges'], queryFn: api.judges.list });

  const createMut = useMutation({
    mutationFn: api.batches.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['batches'] });
      setModalOpen(false);
      setForm({ name: '', mode: 'all', model_ids: [], task_ids: [], task_version_map: {}, default_eval_version: 'eval_init', default_judge_id: '', notes: '' });
    },
  });

  const cloneMut = useMutation({
    mutationFn: (id) => api.batches.clone(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['batches'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
      navigate('/jobs');
    },
  });

  const loadTaskVersions = async (taskId) => {
    if (taskVersions[taskId]) return;
    try {
      const list = await api.tasks.datasets(taskId);
      setTaskVersions(prev => ({ ...prev, [taskId]: list }));
      // 默认选择第一个（最新上传的），或者是默认版本
      const defaultVer = list.find(v => v.is_default) || list[0];
      if (defaultVer) {
        setForm(prev => ({
          ...prev,
          task_version_map: {
            ...prev.task_version_map,
            [taskId]: defaultVer.id
          }
        }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleTaskToggle = (taskId) => {
    const isChecking = !form.task_ids.includes(taskId);
    setForm(prev => {
      const nextTaskIds = isChecking 
        ? [...prev.task_ids, taskId] 
        : prev.task_ids.filter(id => id !== taskId);
        
      const nextVersionMap = { ...prev.task_version_map };
      if (!isChecking) {
        delete nextVersionMap[taskId];
      }
      return {
        ...prev,
        task_ids: nextTaskIds,
        task_version_map: nextVersionMap
      };
    });
    
    if (isChecking) {
      loadTaskVersions(taskId);
    }
  };

  function handleSubmit(e) {
    e.preventDefault();
    const payload = {
      ...form,
      model_ids: form.model_ids.map(Number),
      task_ids: form.task_ids.map(Number),
      default_judge_id: form.default_judge_id ? Number(form.default_judge_id) : null,
    };
    // 过滤未选中任务的版本
    const filteredVersionMap = {};
    form.task_ids.forEach(tid => {
      if (form.task_version_map[tid]) {
        filteredVersionMap[tid] = Number(form.task_version_map[tid]);
      }
    });
    payload.task_version_map = filteredVersionMap;
    createMut.mutate(payload);
  }

  function toggleSelection(arr, val) {
    const v = Number(val);
    return arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v];
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-7">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 leading-tight">测评管理</h1>
          <p className="text-sm text-gray-500 mt-0.5">共 {batches?.length ?? 0} 个评测批次</p>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={() => setModalOpen(true)} disabled={!canWrite()} title={!canWrite() ? '需要操作员或管理员权限' : undefined}>
          <Plus size={16} /> 创建任务
        </button>
      </div>

      <div className="flex items-center gap-2 mb-5 px-4 py-3 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-700">
        <Info size={15} className="flex-shrink-0" />
        <span>任务创建后将自动调度执行，</span>
        <Link to="/jobs" className="font-medium underline underline-offset-2 hover:text-blue-900 flex items-center gap-1">
          前往执行记录 <Activity size={13} />
        </Link>
        <span>查看实时状态与日志。</span>
      </div>

      <Card>
        <CardBody className="p-0 overflow-x-auto relative">
          <table className="min-w-full table-auto min-w-[1100px]">
            <thead>
              <tr className="border-b border-gray-100 bg-white">
                {['评测任务ID', '名称', '模式', 'Eval Version', '创建时间', '状态', '测评配置', '操作', '测评结果'].map((h, i) => {
                  const isLast = i === 8;
                  return (
                    <th 
                      key={h} 
                      className={`px-5 py-3 text-center text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap ${
                        isLast ? 'sticky right-0 bg-white z-10 shadow-[-4px_0_8px_-4px_rgba(0,0,0,0.1)]' : ''
                      }`}
                    >
                      {h}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {isLoading ? (
                <tr><td colSpan={9} className="px-5 py-8 text-center text-sm text-gray-400">加载中...</td></tr>
              ) : batches?.length === 0 ? (
                <tr><td colSpan={9} className="px-5 py-12 text-center text-sm text-gray-400">暂无评测任务</td></tr>
              ) : batches?.map(b => (
                <tr key={b.id} className="trow cursor-pointer transition-colors group" onClick={() => navigate(`/batches/${b.id}`)}>
                  <td className="px-5 py-4 text-center text-[12px] font-mono text-gray-400 whitespace-nowrap">{b.id}</td>
                  <td className="px-5 py-4 text-center text-[13px] font-semibold text-gray-900 whitespace-nowrap">{b.name}</td>
                  <td className="px-5 py-4 text-center whitespace-nowrap">
                    <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                      b.mode === 'all' ? 'bg-purple-50 text-purple-700' :
                      b.mode === 'infer' ? 'bg-primary-50 text-primary-700' : 'bg-amber-50 text-amber-700'
                     }`}>{b.mode === 'all' ? '推理+评测' : b.mode === 'infer' ? '仅推理' : '仅评测'}</span>
                  </td>
                  <td className="px-5 py-4 text-center text-[12px] text-gray-500 font-mono whitespace-nowrap">{b.default_eval_version}</td>
                  <td className="px-5 py-4 text-center text-[12px] text-gray-500 whitespace-nowrap">
                    {toBeijingTime(b.created_at)}
                  </td>
                  <td className="px-5 py-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                    <div className="flex justify-center">
                      <StatusBadge status={b.status} />
                    </div>
                  </td>
                  <td className="px-5 py-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => {
                        setSelectedConfig(b.eval_config);
                        setConfigModalOpen(true);
                      }}
                      className="text-[12px] text-primary-600 hover:text-primary-700 hover:bg-blue-50 px-2.5 py-1 rounded-lg transition-colors font-medium border border-primary-200 bg-white"
                    >
                      查看
                    </button>
                  </td>
                  <td className="px-5 py-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                    {canWrite() && (
                      <div className="flex justify-center">
                        <button
                          onClick={e => { e.stopPropagation(); cloneMut.mutate(b.id); }}
                          disabled={cloneMut.isPending}
                          title="以相同配置重新发起任务"
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[12px] font-medium border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 transition-colors disabled:opacity-40"
                        >
                          <RotateCcw size={12} />
                          重试
                        </button>
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-4 text-center sticky right-0 bg-white group-hover:bg-gray-50 transition-colors z-10 shadow-[-4px_0_8px_-4px_rgba(0,0,0,0.1)]" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={e => { e.stopPropagation(); navigate(`/batches/${b.id}`); }}
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-primary-600 hover:bg-primary-50 transition-colors font-bold text-base mx-auto"
                    >→</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="创建任务" size="lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">任务名称 <span className="text-red-500">*</span></label>
            <input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div>
            <label className="label">模式</label>
            <select className="input" value={form.mode} onChange={e => setForm({ ...form, mode: e.target.value })}>
              <option value="all">推理 + 评测 (all)</option>
              <option value="infer">仅推理 (infer)</option>
              <option value="eval">仅评测 (eval)</option>
            </select>
          </div>
          <div>
            <label className="label">选择评测模型 <span className="text-red-500">*</span></label>
            <div className="border border-gray-200 rounded-lg p-3 space-y-2 max-h-40 overflow-y-auto bg-gray-50">
              {models?.length === 0 ? (
                <p className="text-sm text-gray-400">暂无模型，请先在「评测模型」中新增</p>
              ) : models?.map(m => (
                <label key={m.id} className="flex items-center gap-2 text-sm cursor-pointer text-gray-700">
                  <input type="checkbox" checked={form.model_ids.includes(m.id)} onChange={() => setForm({ ...form, model_ids: toggleSelection(form.model_ids, m.id) })} />
                  <span>{m.name} <span className="text-gray-400">({m.model_name})</span></span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="label">选择评测任务 <span className="text-red-500">*</span></label>
            <div className="border border-gray-200 rounded-lg p-3 space-y-3 max-h-60 overflow-y-auto bg-gray-50">
              {tasks?.map(t => {
                const isSelected = form.task_ids.includes(t.id);
                const versions = taskVersions[t.id];
                return (
                  <div key={t.id} className="space-y-1.5 pb-2 border-b border-gray-100 last:border-b-0">
                    <label className="flex items-center gap-2 text-sm cursor-pointer text-gray-700 font-medium">
                      <input 
                        type="checkbox" 
                        checked={isSelected} 
                        onChange={() => handleTaskToggle(t.id)} 
                      />
                      <span>{t.alias || t.key} <span className="text-gray-400 font-mono text-xs">{t.alias ? `(${t.key})` : ''}</span></span>
                    </label>
                    
                    {isSelected && (
                      <div className="pl-6 flex items-center gap-2">
                        <span className="text-xs text-gray-400 whitespace-nowrap">版本:</span>
                        {!versions ? (
                          <span className="text-xs text-gray-400 animate-pulse">正在加载版本列表...</span>
                        ) : versions.length === 0 ? (
                          <span className="text-xs text-amber-600">暂无上传的版本(将默认选用系统初始版本)</span>
                        ) : (
                          <select 
                            className="input py-0.5 px-2 text-xs w-fit max-w-[200px] border border-gray-200 rounded" 
                            value={form.task_version_map[t.id] || ''}
                            onChange={(e) => setForm(prev => ({
                              ...prev,
                              task_version_map: {
                                ...prev.task_version_map,
                                [t.id]: Number(e.target.value)
                              }
                            }))}
                          >
                            {versions.map(v => (
                              <option key={v.id} value={v.id}>
                                {v.tag}{v.is_default ? ' (默认)' : ''}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">评测版本</label>
              <input className="input" value={form.default_eval_version} onChange={e => setForm({ ...form, default_eval_version: e.target.value })} />
            </div>
            <div>
              <label className="label">打分模型</label>
              <select className="input" value={form.default_judge_id} onChange={e => setForm({ ...form, default_judge_id: e.target.value })}>
                <option value="">不使用</option>
                {judges?.map(j => <option key={j.id} value={j.id}>{j.name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="label">备注</label>
            <input className="input" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>
          {createMut.isError && <p className="text-sm text-red-600">{createMut.error.message}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>取消</button>
            <button type="submit" className="btn-primary" disabled={createMut.isPending}>
              {createMut.isPending ? '创建中...' : '创建'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={configModalOpen} onClose={() => setConfigModalOpen(false)} title="测评配置详情" size="lg">
        <div className="space-y-4">
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 font-mono text-xs overflow-x-auto max-h-[500px]">
            <pre className="whitespace-pre-wrap">{selectedConfig ? JSON.stringify(selectedConfig, null, 2) : '暂无配置信息'}</pre>
          </div>
          <div className="flex justify-end pt-2">
            <button type="button" className="btn-primary" onClick={() => setConfigModalOpen(false)}>关闭</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
