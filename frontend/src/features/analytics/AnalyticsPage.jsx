import { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Copy, Trash2, Download, FileText, BarChart3, ArrowRight, ArrowLeft } from 'lucide-react';
import { api } from '../../lib/api';
import { Card, CardBody } from '../../components/ui/Card';
import { EvaluationPicker } from './components/EvaluationPicker';
import { ComparisonView } from './components/ComparisonView';
import { ExportDialog } from './components/ExportDialog';

/**
 * 测评分析主页：
 * - 左：AnalysisView 模板列表
 * - 右：Evaluation 候选筛选 + 多选 + 对比视图 + 保存/导出
 */
export function AnalyticsPage() {
  const qc = useQueryClient();
  const [activeViewId, setActiveViewId] = useState(null);
  const [name, setName] = useState('');
  const [selectedIds, setSelectedIds] = useState([]); // evaluation_id 列表
  const [chartConfig, setChartConfig] = useState({ primary_metric: 'accuracy' });
  const [exportOpen, setExportOpen] = useState(false);
  const [step, setStep] = useState('select'); // 'select' | 'compare'

  const { data: views = [] } = useQuery({
    queryKey: ['analytics-views'],
    queryFn: () => api.analyticsViews.list(),
  });

  // 切换 view 时载入其状态
  useEffect(() => {
    if (activeViewId == null) return;
    const v = views.find((x) => x.id === activeViewId);
    if (v) {
      setName(v.name);
      setSelectedIds(v.evaluation_ids || []);
      setChartConfig(v.chart_config || { primary_metric: 'accuracy' });
    }
  }, [activeViewId, views]);

  const createMut = useMutation({
    mutationFn: (payload) => api.analyticsViews.create(payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['analytics-views'] });
      setActiveViewId(data.id);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }) => api.analyticsViews.update(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analytics-views'] }),
  });

  const delMut = useMutation({
    mutationFn: (id) => api.analyticsViews.del(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analytics-views'] });
      setActiveViewId(null);
      setName('');
      setSelectedIds([]);
    },
  });

  // 「开始对比」即落库：填了名 + 选了结果就 upsert 当前分析任务，再进对比屏。
  // 反复修改回到这一步会 update 同一条（activeViewId 存在），不新增记录。
  function handleStartCompare() {
    if (!name.trim()) return alert('请先填写分析任务名');
    if (selectedIds.length === 0) return alert('请先勾选评测结果');
    const payload = { name: name.trim(), evaluation_ids: selectedIds, chart_config: chartConfig };
    if (activeViewId) updateMut.mutate({ id: activeViewId, payload });
    else createMut.mutate(payload);
    setStep('compare');
  }

  // 「分析复用」：基于当前配置另存为一个新分析任务，名默认 原名_copy_时间戳，可改。
  function handleDuplicate() {
    if (selectedIds.length === 0 && !activeViewId) return alert('请先选择评测结果或选中一个分析任务');
    const ts = new Date().toLocaleString('sv').replace(/[-: ]/g, '').slice(0, 12);
    const suggested = `${name.trim() || '分析任务'}_copy_${ts}`;
    const finalName = window.prompt('新分析任务名（可修改）', suggested);
    if (!finalName || !finalName.trim()) return;
    createMut.mutate({ name: finalName.trim(), evaluation_ids: selectedIds, chart_config: chartConfig });
  }

  function handleNew() {
    setActiveViewId(null);
    setName('');
    setSelectedIds([]);
    setChartConfig({ primary_metric: 'accuracy' });
  }

  const activeView = useMemo(() => views.find((x) => x.id === activeViewId), [views, activeViewId]);

  // ── 对比屏 ──────────────────────────────────────────────
  if (step === 'compare') {
    return (
      <div>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setStep('select')}
              className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              <ArrowLeft size={15} /> 返回选择
            </button>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <BarChart3 size={20} className="text-primary-600" />
              {name || activeView?.name || '对比结果'}
              <span className="text-sm font-normal text-gray-400">· 共 {selectedIds.length} 条</span>
            </h2>
          </div>
          <button
            onClick={() => setExportOpen(true)}
            disabled={selectedIds.length === 0}
            className="btn-secondary flex items-center gap-1.5"
          >
            <Download size={14} /> 导出 zip
          </button>
        </div>

        <ComparisonView selectedIds={selectedIds} />

        <ExportDialog
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          selectedIds={selectedIds}
          defaultName={name || activeView?.name || ''}
        />
      </div>
    );
  }

  // ── 选择屏 ──────────────────────────────────────────────
  return (
    <div>
      <div className="mb-5">
        <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <BarChart3 size={22} className="text-primary-600" /> 测评分析
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          勾选若干评测结果，点「开始对比」进入对比视图；可保存为模板复用。
        </p>
      </div>

      <div className="grid grid-cols-12 gap-5">
        {/* 模板列表 */}
        <aside className="col-span-3">
          <Card>
            <CardBody className="p-3">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-gray-700">分析任务</span>
                <button onClick={handleNew} className="text-primary-600 hover:text-primary-700" title="新建分析任务">
                  <Plus size={16} />
                </button>
              </div>
              <div className="space-y-1">
                {views.length === 0 && <p className="text-xs text-gray-400 px-2 py-3">暂无分析任务，点击右上 + 新建</p>}
                {views.map((v) => (
                  <div
                    key={v.id}
                    onClick={() => setActiveViewId(v.id)}
                    className={`group flex items-center justify-between gap-1 px-2 py-1.5 rounded cursor-pointer text-sm ${
                      activeViewId === v.id ? 'bg-primary-50 text-primary-700' : 'hover:bg-gray-50 text-gray-700'
                    }`}
                  >
                    <span className="flex items-center gap-1.5 truncate">
                      <FileText size={13} /> {v.name}
                    </span>
                    <button
                      className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`删除模板 "${v.name}"?`)) delMut.mutate(v.id);
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </aside>

        {/* 主区 */}
        <main className="col-span-9 space-y-4">
          <Card>
            <CardBody className="space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <input
                  className="input flex-1 min-w-[200px]"
                  placeholder="分析任务名（必填）"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <button
                  onClick={handleDuplicate}
                  className="btn-secondary flex items-center gap-1.5"
                  title="基于当前配置另存为一个新分析任务"
                >
                  <Copy size={14} /> 分析复用
                </button>
              </div>

              <EvaluationPicker
                selectedIds={selectedIds}
                onChange={setSelectedIds}
              />
            </CardBody>
          </Card>

          {/* 开始对比（落库当前分析任务并进入对比视图）*/}
          <div className="flex justify-end">
            <button
              onClick={handleStartCompare}
              disabled={selectedIds.length === 0 || !name.trim()}
              className="btn-primary flex items-center gap-1.5"
              title={!name.trim() ? '请先填写分析任务名' : (selectedIds.length ? '保存并进入对比视图' : '请先勾选评测结果')}
            >
              开始对比（{selectedIds.length}） <ArrowRight size={15} />
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}
