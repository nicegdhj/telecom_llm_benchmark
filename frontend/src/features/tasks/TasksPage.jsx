import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { Card, CardBody } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { Upload, Download, Database, Check, FileCode2, FlaskConical, BarChart3, Settings2 } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { TASK_DETAIL_META } from '../../lib/taskDetailMeta';

const CATEGORY_COLORS = {
  '知识类':           'bg-sky-100 text-sky-700',
  '推理类':           'bg-orange-100 text-orange-700',
  '生成类':           'bg-emerald-100 text-emerald-700',
  '数学与代码类':     'bg-violet-100 text-violet-700',
  '知识问答':         'bg-teal-100 text-teal-700',
  '意图理解-工具调用':'bg-rose-100 text-rose-700',
  '意图理解-分类':    'bg-amber-100 text-amber-700',
  '意图理解-关键信息抽取': 'bg-indigo-100 text-indigo-700',
  '运维-告警聚类':    'bg-cyan-100 text-cyan-700',
  '安全-身份认知':    'bg-red-100 text-red-700',
};

function CategoryBadge({ category }) {
  const key = Object.keys(CATEGORY_COLORS).find(k => category?.startsWith(k));
  const cls = CATEGORY_COLORS[key] ?? 'bg-gray-100 text-gray-600';
  return <span className={`px-1.5 py-0.5 rounded-md text-xs font-medium ${cls}`}>{category}</span>;
}

function DetailSection({ icon: Icon, title, children }) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-2.5">
        <Icon size={15} className="text-primary-600 flex-shrink-0" />
        <h4 className="text-[13px] font-semibold text-gray-800">{title}</h4>
      </div>
      <div className="ml-5">{children}</div>
    </div>
  );
}

function TaskDetail({ task }) {
  const meta = TASK_DETAIL_META[task.key];

  if (!meta) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <FlaskConical size={32} className="mb-3 opacity-40" />
        <p className="text-sm">该任务暂无详情配置</p>
        <p className="text-xs mt-1 text-gray-300">可在 <code className="bg-gray-100 px-1 rounded">src/lib/taskDetailMeta.js</code> 中手动补充</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">

      {/* 数据格式 */}
      <DetailSection icon={FileCode2} title="数据格式">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
            {meta.format.type}
          </span>
          <span className="text-[12px] text-gray-500">{meta.format.desc}</span>
        </div>
        {meta.format.fields && (
          <div className="mt-2 space-y-1">
            {Object.entries(meta.format.fields).map(([k, v]) => (
              <div key={k} className="flex gap-2 text-[12px]">
                <code className="text-purple-700 font-mono bg-purple-50 px-1 rounded flex-shrink-0">{k}</code>
                <span className="text-gray-500">{v}</span>
              </div>
            ))}
          </div>
        )}
      </DetailSection>

      {/* 数据样例 */}
      <DetailSection icon={FlaskConical} title="数据样例">
        <div className="rounded-lg overflow-hidden border border-gray-200">
          <div className="bg-gray-800 text-gray-400 text-[10px] px-3 py-1.5 flex justify-between">
            <span>输入（input）</span>
            <span className="font-mono">.jsonl</span>
          </div>
          <pre className="bg-gray-900 text-emerald-300 text-[11px] p-3 overflow-auto max-h-36 leading-relaxed font-mono">
            {JSON.stringify(meta.demo.input, null, 2)}
          </pre>
          <div className="bg-gray-100 border-t border-gray-200 px-3 py-2 flex items-start gap-2">
            <span className="text-[10px] text-gray-400 font-medium flex-shrink-0 mt-0.5">期望输出</span>
            <code className="text-[11px] text-amber-700 font-mono break-all">{meta.demo.output}</code>
          </div>
        </div>
      </DetailSection>

      {/* 准确率计算 */}
      <DetailSection icon={BarChart3} title="准确率计算方式">
        <div className="space-y-2">
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
            <p className="text-[11px] text-blue-500 mb-0.5 font-medium">公式</p>
            <code className="text-[12px] text-blue-800 font-mono">{meta.accuracy.formula}</code>
          </div>
          <p className="text-[12px] text-gray-600 leading-relaxed">{meta.accuracy.desc}</p>
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
            <span className="text-[10px] text-amber-500 font-medium flex-shrink-0 mt-0.5">举例</span>
            <p className="text-[12px] text-amber-800">{meta.accuracy.example}</p>
          </div>
        </div>
      </DetailSection>

      {/* ais_bench 配置 */}
      <DetailSection icon={Settings2} title="ais_bench 任务配置">
        <div className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5 space-y-1.5">
          {[
            ['suite_name', meta.aisBench.suite],
            ['eval_type',  meta.aisBench.evalType],
            ['shot',       meta.aisBench.shot],
            ['note',       meta.aisBench.note],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-3 text-[12px]">
              <span className="text-gray-400 font-mono w-20 flex-shrink-0">{k}:</span>
              <span className="text-gray-700">{v}</span>
            </div>
          ))}
        </div>
      </DetailSection>
    </div>
  );
}

export function TasksPage() {
  const qc = useQueryClient();
  const { canWrite } = useAuthStore();
  const [selectedTask, setSelectedTask] = useState(null);
  const [activeTab, setActiveTab] = useState('detail'); // 'detail' | 'manage'
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({ tag: '', is_default: false, note: '', file: null });

  const { data: tasks, isLoading } = useQuery({ queryKey: ['tasks'], queryFn: api.tasks.list });

  // 数据加载完成后默认选中第一个任务
  useEffect(() => {
    if (tasks?.length && !selectedTask) {
      setSelectedTask(tasks[0]);
      setActiveTab('detail');
    }
  }, [tasks]);

  const { data: datasets } = useQuery({
    queryKey: ['tasks', selectedTask?.id, 'datasets'],
    queryFn: () => api.tasks.datasets(selectedTask.id),
    enabled: !!selectedTask,
  });

  const uploadMut = useMutation({
    mutationFn: ({ taskId, formData }) => api.tasks.uploadDataset(taskId, formData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['tasks', selectedTask?.id, 'datasets'] });
      setUploadOpen(false);
      setUploadForm({ tag: '', is_default: false, note: '', file: null });
    },
  });

  function handleUpload(e) {
    e.preventDefault();
    const fd = new FormData();
    fd.append('tag', uploadForm.tag);
    fd.append('is_default', uploadForm.is_default);
    if (uploadForm.note) fd.append('note', uploadForm.note);
    fd.append('file', uploadForm.file);
    uploadMut.mutate({ taskId: selectedTask.id, formData: fd });
  }

  function selectTask(t, tab = 'detail') {
    setSelectedTask(t);
    setActiveTab(tab);
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-7">
        <div>
          <h1 className="text-[22px] font-bold text-gray-900 leading-tight">任务与数据</h1>
          <p className="text-sm text-gray-500 mt-0.5">管理评测任务及数据集版本</p>
        </div>
      </div>

      <div className="flex gap-6" style={{ height: 'calc(100vh - 160px)' }}>
        {/* 左侧任务列表 — 独立滚动 */}
        <div className="w-80 flex-shrink-0 flex flex-col min-h-0">
          <Card className="flex flex-col min-h-0 flex-1">
            <CardBody className="p-0 flex flex-col min-h-0">
              <div className="px-4 py-3 border-b border-gray-100 font-semibold text-sm text-gray-700 flex-shrink-0">
                任务列表 <span className="text-gray-400 font-normal text-xs">({tasks?.length ?? 0})</span>
              </div>
              <div className="overflow-y-auto flex-1">
              {isLoading ? (
                <div className="px-4 py-4 text-sm text-gray-400">加载中...</div>
              ) : tasks?.map(t => (
                <div
                  key={t.id}
                  className="border-b border-gray-50 transition-colors relative"
                  style={selectedTask?.id === t.id
                    ? { background: '#eff6ff', borderLeft: '3px solid #0C5CAB' }
                    : { borderLeft: '3px solid transparent' }
                  }
                >
                  {/* 卡片主体（点击选中，默认详情） */}
                  <button
                    className="w-full text-left px-4 pt-3 pb-1"
                    onClick={() => selectTask(t, 'detail')}
                  >
                    <div className="flex items-start justify-between">
                      <div className="text-sm font-semibold text-gray-900 leading-snug pr-2 flex-1">
                        {t.alias || t.key}
                      </div>
                      {t.dataset_count > 0 && (
                        <span className="flex items-center gap-1 text-[10px] text-emerald-600 flex-shrink-0 mt-0.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                          {t.dataset_count}版本
                        </span>
                      )}
                    </div>
                    {t.alias && (
                      <div className="text-xs text-gray-400 font-mono mt-0.5">{t.key}</div>
                    )}
                    <div className="mt-1.5 flex items-center flex-wrap gap-1">
                      {t.category && <CategoryBadge category={t.category} />}
                      <span className={`px-1.5 py-0.5 rounded-md text-xs font-medium ${t.type === 'custom' ? 'bg-primary-100 text-primary-700' : 'bg-purple-100 text-purple-700'}`}>{t.type}</span>
                      {t.is_llm_judge && <span className="px-1.5 py-0.5 rounded-md text-xs font-medium bg-amber-100 text-amber-700">LLM Judge</span>}
                    </div>
                  </button>

                  {/* 详情 / 管理 按钮 */}
                  <div className="flex items-center justify-end gap-1 px-4 pb-2.5 pt-1">
                    <button
                      onClick={() => selectTask(t, 'detail')}
                      className={`text-[11px] font-medium px-2 py-0.5 rounded transition-colors ${
                        selectedTask?.id === t.id && activeTab === 'detail'
                          ? 'bg-primary-600 text-white'
                          : 'text-primary-600 hover:bg-primary-50'
                      }`}
                    >
                      详情
                    </button>
                    <button
                      onClick={() => selectTask(t, 'manage')}
                      className={`text-[11px] font-medium px-2 py-0.5 rounded transition-colors ${
                        selectedTask?.id === t.id && activeTab === 'manage'
                          ? 'bg-gray-600 text-white'
                          : 'text-gray-500 hover:bg-gray-100'
                      }`}
                    >
                      管理
                    </button>
                  </div>
                </div>
              ))}
              </div>{/* end overflow-y-auto */}
            </CardBody>
          </Card>
        </div>

        {/* 右侧内容区 — 独立滚动 */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {selectedTask ? (
            <div className="flex flex-col min-h-0 flex-1">
              {/* 固定标题栏 + tabs */}
              <div className="flex-shrink-0">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">{selectedTask.alias || selectedTask.key}</h3>
                    {selectedTask.alias && (
                      <p className="text-xs text-gray-400 font-mono mt-0.5">{selectedTask.key}</p>
                    )}
                    {selectedTask.category && (
                      <div className="mt-1"><CategoryBadge category={selectedTask.category} /></div>
                    )}
                  </div>
                  {activeTab === 'manage' && (
                    <button className="btn-primary flex items-center gap-2" onClick={() => setUploadOpen(true)} disabled={!canWrite()} title={!canWrite() ? '需要操作员或管理员权限' : undefined}>
                      <Upload size={15} /> 上传数据集
                    </button>
                  )}
                </div>
                <div className="flex gap-1 mb-3 border-b border-gray-200">
                  {[['detail', '数据集详情'], ['manage', '版本管理']].map(([tab, label]) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-4 py-2 text-[13px] font-medium transition-colors border-b-2 -mb-px ${
                        activeTab === tab
                          ? 'border-primary-600 text-primary-700'
                          : 'border-transparent text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* 可滚动内容区 */}
              <div className="overflow-y-auto flex-1">
                {activeTab === 'detail' ? (
                  <Card>
                    <CardBody className="py-5 px-6">
                      <TaskDetail task={selectedTask} />
                    </CardBody>
                  </Card>
                ) : (
                  <Card>
                    <CardBody className="p-0">
                      <table className="min-w-full">
                        <thead>
                          <tr className="border-b border-gray-100">
                            {['Tag', '默认', 'Hash', '上传时间', '备注', '下载'].map(h => (
                              <th key={h} className="px-4 py-3 text-center text-[11px] font-semibold text-gray-400 uppercase tracking-wider">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {datasets?.length === 0 ? (
                            <tr><td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">暂无数据集版本，点击右上角上传</td></tr>
                          ) : datasets?.map(d => (
                            <tr key={d.id} className="hover:bg-gray-50 transition-colors">
                              <td className="px-4 py-3 text-sm font-semibold text-gray-900">{d.tag}</td>
                              <td className="px-4 py-3 text-center">{d.is_default ? <Check size={15} className="text-emerald-500 mx-auto" /> : <span className="text-gray-300">—</span>}</td>
                              <td className="px-4 py-3 text-xs text-gray-400 font-mono">{d.content_hash ? d.content_hash.slice(0, 12) + '…' : <span className="text-gray-300">—</span>}</td>
                              <td className="px-4 py-3 text-sm text-gray-500">{new Date(d.uploaded_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</td>
                              <td className="px-4 py-3 text-sm text-gray-500">{d.note || <span className="text-gray-300">—</span>}</td>
                              <td className="px-4 py-3 text-center">
                                <button
                                  onClick={() => api.tasks.downloadDataset(selectedTask.id, d.id).catch(() => alert('下载失败'))}
                                  title="下载该版本数据 (zip)"
                                  className="text-gray-400 hover:text-indigo-600 transition-colors"
                                >
                                  <Download size={16} className="mx-auto" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </CardBody>
                  </Card>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-gray-300">
              <Database size={48} className="mb-4" />
              <p className="text-gray-400">点击左侧任务卡片的「详情」或「管理」</p>
            </div>
          )}
        </div>
      </div>

      <Modal open={uploadOpen} onClose={() => setUploadOpen(false)} title="上传数据集">
        <form onSubmit={handleUpload} className="space-y-4">
          <div>
            <label className="label">版本标签 <span className="text-red-500">*</span></label>
            <input className="input" value={uploadForm.tag} onChange={e => setUploadForm({ ...uploadForm, tag: e.target.value })} required />
          </div>
          <div>
            <label className="label">JSONL 文件 <span className="text-red-500">*</span></label>
            <input type="file" accept=".jsonl" className="input py-1.5" onChange={e => setUploadForm({ ...uploadForm, file: e.target.files[0] })} required />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="is_default" checked={uploadForm.is_default} onChange={e => setUploadForm({ ...uploadForm, is_default: e.target.checked })} />
            <label htmlFor="is_default" className="text-sm text-gray-700">设为默认版本</label>
          </div>
          <div>
            <label className="label">备注</label>
            <input className="input" value={uploadForm.note} onChange={e => setUploadForm({ ...uploadForm, note: e.target.value })} />
          </div>
          {uploadMut.isError && <p className="text-sm text-red-600">{uploadMut.error.message}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" className="btn-secondary" onClick={() => setUploadOpen(false)}>取消</button>
            <button type="submit" className="btn-primary" disabled={uploadMut.isPending}>
              {uploadMut.isPending ? '上传中...' : '上传'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
