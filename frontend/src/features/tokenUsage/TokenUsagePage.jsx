import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Gauge, Plus, Search, Trash2 } from 'lucide-react';

import { Card, CardBody } from '../../components/ui/Card';
import { api } from '../../lib/api';
import { DEFAULT_NAMES, METRIC_COLUMNS, formatMetricValue } from './tokenUsageConfig';


function toInputTime(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return [
    date.getFullYear(), '-', pad(date.getMonth() + 1), '-', pad(date.getDate()),
    'T', pad(date.getHours()), ':00',
  ].join('');
}


function initialTimes() {
  const end = new Date();
  end.setMinutes(0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - 3);
  return { start: toInputTime(start), end: toInputTime(end) };
}


function toApiTime(value) {
  return `${value.replace('T', ' ')}:00`;
}


function intervalLabel(row) {
  return `${row.startTime}  →  ${row.endTime}`;
}


function MetricCells({ row }) {
  if (row.error) {
    return (
      <td colSpan={METRIC_COLUMNS.length} className="px-5 py-4 text-left text-sm text-red-600 bg-red-50/40">
        {row.error}
      </td>
    );
  }

  return METRIC_COLUMNS.map((column) => (
    <td key={column.key} className="px-5 py-4 text-center text-[13px] text-gray-700 whitespace-nowrap tabular-nums">
      {formatMetricValue(row.data?.[column.key], column.format)}
    </td>
  ));
}


export function TokenUsagePage() {
  const [defaults] = useState(() => initialTimes());
  const [startTime, setStartTime] = useState(defaults.start);
  const [endTime, setEndTime] = useState(defaults.end);
  const [granularity, setGranularity] = useState('day');
  const [names, setNames] = useState(DEFAULT_NAMES.map((item) => ({ ...item })));
  const [result, setResult] = useState(null);
  const [submittedNames, setSubmittedNames] = useState([]);
  const [formError, setFormError] = useState('');

  const query = useMutation({
    mutationFn: (payload) => api.tokenUsage.query(payload),
    onSuccess: (data) => {
      setResult(data);
      setSubmittedNames(data.names || []);
    },
  });

  function updateName(index, field, value) {
    setNames((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [field]: value } : item
    )));
  }

  function removeName(index) {
    setNames((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  function handleSubmit(event) {
    event.preventDefault();
    setFormError('');
    query.reset();

    const effectiveNames = names.filter((item) => item.value.trim());
    if (!startTime || !endTime) {
      setFormError('请选择开始时间和结束时间');
      return;
    }
    if (endTime <= startTime) {
      setFormError('结束时间必须晚于开始时间');
      return;
    }
    if (effectiveNames.length === 0) {
      setFormError('至少填写一个 Name 接口标识');
      return;
    }

    query.mutate({
      names: effectiveNames,
      startTime: toApiTime(startTime),
      endTime: toApiTime(endTime),
      granularity,
    });
  }

  return (
    <div className="min-w-0">
      <div className="mb-6">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-blue-50 text-primary-600 flex items-center justify-center">
            <Gauge size={19} />
          </div>
          <div>
            <h1 className="text-[22px] font-bold text-gray-900 leading-tight">Token 用量查询</h1>
            <p className="text-sm text-gray-500 mt-0.5">按小时或按天查看 MaaS 接口的原始统计结果</p>
          </div>
        </div>
      </div>

      <Card className="mb-5">
        <CardBody className="p-5">
          <form onSubmit={handleSubmit}>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(190px,1fr)_minmax(190px,1fr)_180px_auto] gap-4 items-end">
              <label>
                <span className="label">开始时间</span>
                <input
                  type="datetime-local"
                  step="3600"
                  value={startTime}
                  onChange={(event) => setStartTime(event.target.value)}
                  className="input"
                />
              </label>
              <label>
                <span className="label">结束时间</span>
                <input
                  type="datetime-local"
                  step="3600"
                  value={endTime}
                  onChange={(event) => setEndTime(event.target.value)}
                  className="input"
                />
              </label>
              <div>
                <span className="label">统计维度</span>
                <div className="grid grid-cols-2 p-1 rounded-lg bg-gray-100 h-[38px]">
                  {[
                    { value: 'day', label: '天' },
                    { value: 'hour', label: '小时' },
                  ].map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => setGranularity(item.value)}
                      className={`rounded-md text-xs font-semibold transition-all ${
                        granularity === item.value
                          ? 'bg-white text-primary-700 shadow-sm'
                          : 'text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
              <button type="submit" disabled={query.isPending} className="btn-primary h-[38px] px-6">
                <Search size={15} />
                {query.isPending ? '查询中...' : '查询'}
              </button>
            </div>

            <div className="mt-5 pt-5 border-t border-gray-100">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-gray-800">Names</h2>
                  <p className="text-xs text-gray-400 mt-0.5">名称仅用于识别，接口标识会作为 names 参数查询</p>
                </div>
                <button
                  type="button"
                  onClick={() => setNames((current) => [...current, { label: '', value: '' }])}
                  className="btn-secondary py-1.5 px-3 text-xs"
                >
                  <Plus size={13} /> 增加 Name
                </button>
              </div>

              <div className="space-y-2">
                {names.map((item, index) => (
                  <div key={index} className="grid grid-cols-1 md:grid-cols-[220px_minmax(320px,1fr)_34px] gap-2">
                    <input
                      className="input"
                      placeholder="友好名称，如：后端 API"
                      value={item.label}
                      onChange={(event) => updateName(index, 'label', event.target.value)}
                    />
                    <input
                      className="input font-mono text-xs"
                      placeholder="接口标识"
                      value={item.value}
                      onChange={(event) => updateName(index, 'value', event.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => removeName(index)}
                      className="h-[38px] rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors flex items-center justify-center"
                      title="删除"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
                {names.length === 0 && (
                  <p className="text-xs text-amber-600 py-2">当前没有 Name，请点击“增加 Name”。</p>
                )}
              </div>
            </div>

            {formError && <p className="mt-3 text-sm text-red-600">{formError}</p>}
            {query.isError && <p className="mt-3 text-sm text-red-600">{query.error.message}</p>}
          </form>
        </CardBody>
      </Card>

      {result ? (
        <Card>
          <div className="px-5 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">查询结果</h2>
              <p className="text-xs text-gray-400 mt-0.5">数据均为 MaaS 接口原始返回，平台不做求和或平均</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {submittedNames.map((item, index) => (
                <span key={`${item.label}-${item.value}-${index}`} className="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2.5 py-1 text-xs text-primary-700">
                  <strong className="font-semibold">{item.label || '未命名'}</strong>
                  <span className="font-mono text-[10px] text-primary-500">{item.value}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[3000px] w-full border-collapse">
              <thead>
                <tr className="bg-[#f3f6fc] border-b border-gray-100">
                  <th className="sticky left-0 z-20 bg-[#f3f6fc] min-w-[330px] px-5 py-3.5 text-left text-[12px] font-semibold text-gray-600 whitespace-nowrap">
                    统计区间
                  </th>
                  {METRIC_COLUMNS.map((column) => (
                    <th key={column.key} className="px-5 py-3.5 text-center text-[12px] font-semibold text-gray-600 whitespace-nowrap">
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {result.rows.map((row) => (
                  <tr key={`${row.startTime}-${row.endTime}`} className="trow">
                    <td className="sticky left-0 z-10 bg-white px-5 py-4 text-[13px] font-medium text-primary-600 whitespace-nowrap border-r border-gray-100">
                      {intervalLabel(row)}
                    </td>
                    <MetricCells row={row} />
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-primary-100 bg-blue-50/60">
                  <td className="sticky left-0 z-10 bg-[#edf5fc] px-5 py-4 text-[13px] font-bold text-gray-800 whitespace-nowrap border-r border-primary-100">
                    汇总·{intervalLabel(result.summary)}
                  </td>
                  <MetricCells row={result.summary} />
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      ) : (
        <Card>
          <CardBody className="py-16 text-center">
            <Gauge size={28} className="mx-auto text-gray-300 mb-3" />
            <p className="text-sm text-gray-400">设置查询条件后，查询结果将显示在这里</p>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
