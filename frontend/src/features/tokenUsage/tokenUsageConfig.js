export const DEFAULT_NAMES = [
  { label: '接口 1', value: 'd29a854f-5b1f-4da9-9a1e-caecacfd1156' },
  { label: '接口 2', value: '76816616-c232-404c-bbb8-c950549231ee' },
];

export const METRIC_COLUMNS = [
  { key: 'keyNum', label: '调用来源', format: 'plain' },
  { key: 'serviceNum', label: '调用服务', format: 'plain' },
  { key: 'apiNum', label: '调用接口', format: 'plain' },
  { key: 'callCount', label: '调用次数', format: 'plain' },
  { key: 'exceptionCount', label: '异常次数', format: 'plain' },
  { key: 'successRate', label: '成功率', format: 'percent' },
  { key: 'tokenUsage', label: 'Token 数消耗', format: 'plain' },
  { key: 'avgTokenUsage', label: '平均 Token 消耗', format: 'plain' },
  { key: 'avgRequestTokenUsage', label: '平均请求 Token 消耗', format: 'plain' },
  { key: 'avgDelay', label: '请求时长', format: 'milliseconds' },
  { key: 'avgTimeToFirstToken', label: '平均首 Token 延时', format: 'milliseconds' },
  { key: 'avgTokenSpeed', label: '平均生成速度', format: 'plain' },
  { key: 'avgTokenThroughput', label: '平均吞吐速度', format: 'plain' },
  { key: 'httpClientErrorAlerts', label: '4xx 错误', format: 'plain' },
  { key: 'httpServerErrorAlerts', label: '5xx 错误', format: 'plain' },
  { key: 'avgEndToEndTps', label: '端到端 TPS', format: 'plain' },
  { key: 'avgModelOutputTokenTps', label: '模型生成 TPS', format: 'plain' },
  { key: 'timeToPerToken', label: 'TPOT', format: 'plain' },
  { key: 'dataTypeList', label: '数据类型', format: 'list' },
];

export function formatMetricValue(value, format) {
  if (value === null || value === undefined || value === '') return '—';
  if (format === 'percent') return `${value}%`;
  if (format === 'milliseconds') return `${value}ms`;
  if (format === 'list') return Array.isArray(value) ? value.join('、') : String(value);
  return String(value);
}
