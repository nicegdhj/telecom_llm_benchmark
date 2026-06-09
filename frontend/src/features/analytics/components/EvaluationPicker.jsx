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
      <div className="grid grid-cols-3 gap-3">
        <FilterMultiSelect label="模型" options={models.map((m) => ({ id: m.id, label: m.name }))}
                            value={filter.model_ids} onChange={(v) => setFilter({ ...filter, model_ids: v })} />
        <FilterMultiSelect label="任务" options={tasks.map((t) => ({ id: t.id, label: t.key }))}
                            value={filter.task_ids} onChange={(v) => setFilter({ ...filter, task_ids: v })} />
        <FilterMultiSelect label="批次" options={batches.map((b) => ({ id: b.id, label: b.name }))}
                            value={filter.batch_ids} onChange={(v) => setFilter({ ...filter, batch_ids: v })} />
      </div>

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


function FilterMultiSelect({ label, options, value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <label className="label">{label}</label>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="input text-left text-sm w-full"
      >
        {value.length === 0 ? '全部' : `已选 ${value.length} 项`}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-56 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow w-full">
          {options.length === 0 && <div className="text-xs text-gray-400 px-3 py-2">无可选项</div>}
          {options.map((opt) => (
            <label key={opt.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={value.includes(opt.id)}
                onChange={() => {
                  const next = value.includes(opt.id)
                    ? value.filter((x) => x !== opt.id)
                    : [...value, opt.id];
                  onChange(next);
                }}
              />
              {opt.label}
            </label>
          ))}
          <div className="border-t border-gray-100 px-3 py-1 text-right">
            <button onClick={() => setOpen(false)} className="text-xs text-primary-600 hover:underline">关闭</button>
          </div>
        </div>
      )}
    </div>
  );
}
