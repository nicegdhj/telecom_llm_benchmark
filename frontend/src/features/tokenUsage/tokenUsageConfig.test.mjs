import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_NAMES, METRIC_COLUMNS, formatMetricValue } from './tokenUsageConfig.js';


test('provides the two editable default MaaS names', () => {
  assert.deepEqual(DEFAULT_NAMES.map((item) => item.value), [
    'd29a854f-5b1f-4da9-9a1e-caecacfd1156',
    '76816616-c232-404c-bbb8-c950549231ee',
  ]);
});


test('lists every metric returned by the MaaS statistics API', () => {
  assert.deepEqual(METRIC_COLUMNS.map((item) => item.key), [
    'keyNum',
    'serviceNum',
    'apiNum',
    'callCount',
    'exceptionCount',
    'successRate',
    'tokenUsage',
    'avgTokenUsage',
    'avgRequestTokenUsage',
    'avgDelay',
    'avgTimeToFirstToken',
    'avgTokenSpeed',
    'avgTokenThroughput',
    'httpClientErrorAlerts',
    'httpServerErrorAlerts',
    'avgEndToEndTps',
    'avgModelOutputTokenTps',
    'timeToPerToken',
    'dataTypeList',
  ]);
});


test('formats units for display without recalculating values', () => {
  assert.equal(formatMetricValue(0, 'percent'), '0%');
  assert.equal(formatMetricValue(85.47, 'percent'), '85.47%');
  assert.equal(formatMetricValue(428.84, 'milliseconds'), '428.84ms');
  assert.equal(formatMetricValue(['pt', 'mc'], 'list'), 'pt、mc');
  assert.equal(formatMetricValue(null, 'plain'), '—');
});
