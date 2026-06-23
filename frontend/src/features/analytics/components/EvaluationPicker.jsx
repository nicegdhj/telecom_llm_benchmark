import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../../lib/api';

/**
 * Evaluation 候选选择器：筛选 + 按「最小单元」折叠多选。
 *
 * 折叠规则：同一个 模型×任务×批次（cell）只占一行，多个版本（v1_score/v2_score…）
 * 收进行内下拉，默认选最新版。勾选即把该单元「当前选定版本」的 evaluation_id 加入。
 * onChange 接收最新的 evaluation_id 列表。
 */
export function EvaluationPicker({ selectedIds = [], onChange }) {
  // 只对比成功的评测，故状态固定 success、不再透出筛选器
  const [filter, setFilter] = useState({
    model_ids: [],
    task_ids: [],
    batch_ids: [],
  });
  // 每个单元「待选/显示」的版本 id（未勾选时也记住用户切到了哪版）
  const [picked, setPicked] = useState({});

  const { data: models = [] } = useQuery({ queryKey: ['models'], queryFn: () => api.models.list() });
  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: () => api.tasks.list() });
  const { data: batches = [] } = useQuery({ queryKey: ['batches'], queryFn: () => api.batches.list() });

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['evaluations-search', filter],
    queryFn: () => api.evaluations.search({
      model_ids: filter.model_ids.length ? filter.model_ids : undefined,
      task_ids: filter.task_ids.length ? filter.task_ids : undefined,
      batch_ids: filter.batch_ids.length ? filter.batch_ids : undefined,
      status: 'success',
      limit: 200,
    }),
  });

  // 按 cell 分组；rows 已按 created_at desc，故 versions[0] 即最新版
  const groups = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const key = `${r.model_id}|${r.task_id}|${r.batch_id}`;
      if (!map.has(key)) map.set(key, { key, model_name: r.model_name, task_key: r.task_key, batch_name: r.batch_name, versions: [] });
      map.get(key).versions.push(r);
    }
    return [...map.values()];
  }, [rows]);

  const allRowIds = rows.map((r) => r.id);

  // 该单元是否已勾选（selectedIds 含其任一版本）
  const isChecked = (g) => g.versions.some((v) => selectedIds.includes(v.id));
  // 当前选定/显示的版本 id：已勾选用 selected 中那个，否则用 picked 或最新版
  const currentId = (g) => {
    const sel = g.versions.find((v) => selectedIds.includes(v.id));
    if (sel) return sel.id;
    return picked[g.key] ?? g.versions[0].id;
  };

  function toggleGroup(g) {
    const groupIds = g.versions.map((v) => v.id);
    if (isChecked(g)) {
      onChange(selectedIds.filter((id) => !groupIds.includes(id)));
    } else {
      onChange([...selectedIds, currentId(g)]);
    }
  }

  function changeVersion(g, newId) {
    setPicked((p) => ({ ...p, [g.key]: newId }));
    if (isChecked(g)) {
      const groupIds = g.versions.map((v) => v.id);
      onChange([...selectedIds.filter((id) => !groupIds.includes(id)), newId]);
    }
  }

  const allChecked = groups.length > 0 && groups.every(isChecked);
  function toggleAll() {
    const others = selectedIds.filter((id) => !allRowIds.includes(id));
    if (allChecked) onChange(others);
    else onChange([...others, ...groups.map(currentId)]);
  }

  return (
    <div className="space-y-3">
      <CombinedFilter
        groups={[
          { key: 'model_ids', label: '模型', options: models.map((m) => ({ id: m.id, label: m.name })) },
          { key: 'task_ids', label: '任务', options: tasks.map((t) => ({ id: t.id, label: t.key })) },
          { key: 'batch_ids', label: '批次', options: batches.map((b) => ({ id: b.id, label: b.name })) },
        ]}
        value={filter}
        onApply={setFilter}
      />

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <div className="bg-gray-50 px-3 py-2 text-xs text-gray-500 flex items-center justify-between">
          <span>候选 {groups.length} 个单元 · 已选 {selectedIds.length} 条</span>
          <button onClick={toggleAll} className="text-primary-600 hover:underline" disabled={groups.length === 0}>
            {allChecked ? '全部取消' : '全选当前'}
          </button>
        </div>
        <div className="max-h-72 overflow-y-auto divide-y divide-gray-100">
          {isLoading && <div className="text-sm text-gray-400 px-3 py-3">加载中...</div>}
          {!isLoading && groups.length === 0 && <div className="text-sm text-gray-400 px-3 py-3">无匹配结果</div>}
          {groups.map((g) => {
            const cur = g.versions.find((v) => v.id === currentId(g)) || g.versions[0];
            return (
              <div key={g.key} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-gray-50">
                <input
                  type="checkbox"
                  className="cursor-pointer"
                  checked={isChecked(g)}
                  onChange={() => toggleGroup(g)}
                />
                <span className="font-medium text-gray-700">{g.model_name}</span>
                <span className="text-gray-300">·</span>
                <span className="font-mono text-gray-600">{g.task_key}</span>
                <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-[11px]">{g.batch_name}</span>

                {g.versions.length > 1 ? (
                  <select
                    className="text-[12px] font-mono border border-gray-200 rounded px-1.5 py-0.5 text-gray-600 bg-white"
                    value={currentId(g)}
                    onChange={(e) => changeVersion(g, Number(e.target.value))}
                    title="该单元有多个版本，可切换"
                  >
                    {g.versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.version_label}{v.accuracy != null ? ` · ${v.accuracy.toFixed(1)}%` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="font-mono text-gray-400 text-[12px]">{cur.version_label}</span>
                )}

                <span className="flex-1 text-right">
                  {cur.accuracy != null && <span className="font-semibold text-emerald-700">{cur.accuracy.toFixed(2)}%</span>}
                  {cur.num_samples != null && <span className="text-gray-400 ml-2">{cur.num_samples} 样本</span>}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


/**
 * 合并筛选：模型 / 任务 / 批次 三列同屏点选，默认"全部"，点一次「确认」统一应用。
 * value/onApply 使用 { model_ids, task_ids, batch_ids } 形状。
 */
function CombinedFilter({ groups, value, onApply }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);

  function openPanel() {
    setDraft(value);   // 每次打开同步当前已应用的筛选
    setOpen(true);
  }
  function toggle(key, id) {
    setDraft((d) => {
      const cur = d[key] || [];
      const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
      return { ...d, [key]: next };
    });
  }
  const selectAll = (key) => setDraft((d) => ({ ...d, [key]: [] })); // 空 = 全部
  const reset = () => setDraft({ model_ids: [], task_ids: [], batch_ids: [] });
  function confirm() {
    onApply(draft);
    setOpen(false);
  }

  const summary = groups
    .map((g) => `${g.label} ${(value[g.key]?.length || 0) === 0 ? '全部' : value[g.key].length}`)
    .join(' · ');

  return (
    <div>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openPanel())}
        className="input text-left text-sm w-full flex items-center justify-between"
      >
        <span className="text-gray-700">{summary}</span>
        <span className="text-gray-400 text-xs">{open ? '收起' : '筛选'}</span>
      </button>

      {open && (
        <div className="mt-2 border border-gray-200 rounded-lg bg-white shadow-sm">
          <div className="grid grid-cols-3 divide-x divide-gray-100">
            {groups.map((g) => {
              const sel = draft[g.key] || [];
              const isAll = sel.length === 0;
              return (
                <div key={g.key} className="flex flex-col min-h-0">
                  <div className="px-3 py-2 text-xs font-semibold text-gray-500 border-b border-gray-100">{g.label}</div>
                  <div className="max-h-56 overflow-y-auto py-1">
                    <label className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 text-sm cursor-pointer">
                      <input type="checkbox" checked={isAll} onChange={() => selectAll(g.key)} />
                      <span className={isAll ? 'text-primary-600 font-medium' : 'text-gray-600'}>全部</span>
                    </label>
                    {g.options.length === 0 && <div className="text-xs text-gray-400 px-3 py-2">无可选项</div>}
                    {g.options.map((opt) => (
                      <label key={opt.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 text-sm cursor-pointer">
                        <input type="checkbox" checked={sel.includes(opt.id)} onChange={() => toggle(g.key, opt.id)} />
                        <span className="text-gray-700 truncate">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex items-center justify-end gap-2 px-3 py-2 border-t border-gray-100 bg-gray-50">
            <button onClick={reset} className="text-xs text-gray-500 hover:text-gray-700">重置</button>
            <button onClick={confirm} className="btn-primary text-xs px-4 py-1.5">确认</button>
          </div>
        </div>
      )}
    </div>
  );
}
