import { useAuthStore } from '../store/authStore';

// API 也挂在统一前缀下：/chuilei/eval/api/v1（前缀来自 vite base）
const API_BASE = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api/v1`;

function getToken() {
  return localStorage.getItem('eval_auth_token') || '';
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    ...options.headers,
  };

  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    useAuthStore.getState().clearSession();
    window.location.href = `${import.meta.env.BASE_URL}login`;
    return;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request('/health'),

  auth: {
    login: (data) => request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    logout: () => request('/auth/logout', { method: 'POST' }),
    me: () => request('/auth/me'),
    changePassword: (data) => request('/auth/change-password', { method: 'POST', body: JSON.stringify(data) }),
  },

  users: {
    list: () => request('/users'),
    get: (id) => request(`/users/${id}`),
    create: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    del: (id) => request(`/users/${id}`, { method: 'DELETE' }),
    resetPassword: (id, data) => request(`/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify(data) }),
  },

  models: {
    list: () => request('/models'),
    get: (id) => request(`/models/${id}`),
    create: (data) => request('/models', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/models/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    del: (id) => request(`/models/${id}`, { method: 'DELETE' }),
  },

  judges: {
    list: () => request('/judges'),
    get: (id) => request(`/judges/${id}`),
    create: (data) => request('/judges', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/judges/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    del: (id) => request(`/judges/${id}`, { method: 'DELETE' }),
  },

  tasks: {
    list: () => request('/tasks'),
    get: (id) => request(`/tasks/${id}`),
    datasets: (taskId) => request(`/tasks/${taskId}/datasets`),
    uploadDataset: (taskId, formData) => request(`/tasks/${taskId}/datasets`, {
      method: 'POST',
      body: formData,
      headers: {}, // fetch will set Content-Type with boundary for FormData
    }),
    // 下载某版本数据为 zip，直接触发浏览器下载（走原始 fetch 拿 blob）
    downloadDataset: async (taskId, versionId) => {
      const token = localStorage.getItem('eval_auth_token') || '';
      const res = await fetch(`${API_BASE}/tasks/${taskId}/datasets/${versionId}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cd = res.headers.get('content-disposition') || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : `dataset_${versionId}.zip`;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  },

  batches: {
    list: () => request('/batches'),
    get: (id) => request(`/batches/${id}`),
    create: (data) => request('/batches', { method: 'POST', body: JSON.stringify(data) }),
    report: (id, rev) => request(`/batches/${id}/report${rev ? `?rev=${rev}` : ''}`),
    revisions: (id) => request(`/batches/${id}/revisions`),
    rerun: (id, data) => request(`/batches/${id}/rerun`, { method: 'POST', body: JSON.stringify(data) }),
    clone: (id, data = {}) => request(`/batches/${id}/clone`, { method: 'POST', body: JSON.stringify(data) }),
    cellDetail: (id, mid, tid) => request(`/batches/${id}/cells/${mid}/${tid}`),
    cellSwitchPointer: (id, mid, tid, data) =>
      request(`/batches/${id}/cells/${mid}/${tid}/pointer`, {
        method: 'PUT', body: JSON.stringify(data),
      }),
    cellRerun: (id, mid, tid, data) =>
      request(`/batches/${id}/cells/${mid}/${tid}/rerun`, {
        method: 'POST', body: JSON.stringify(data),
      }),
  },

  jobs: {
    list: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request(`/jobs${qs ? `?${qs}` : ''}`);
    },
    get: (id) => request(`/jobs/${id}`),
    log: (id) => request(`/jobs/${id}/log`),
    frameworkLog: (id) => request(`/jobs/${id}/framework-log`),
    cancel: (id) => request(`/jobs/${id}/cancel`, { method: 'POST' }),
  },

  predictions: {
    get: (id) => request(`/predictions/${id}`),
  },

  evaluations: {
    get: (id) => request(`/evaluations/${id}`),
    search: (params = {}) => {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === null || v === '') continue;
        if (Array.isArray(v)) v.forEach((x) => qs.append(k, x));
        else qs.append(k, v);
      }
      const s = qs.toString();
      return request(`/evaluations/search${s ? `?${s}` : ''}`);
    },
  },

  analyticsViews: {
    list: () => request('/analysis-views'),
    get: (id) => request(`/analysis-views/${id}`),
    create: (data) => request('/analysis-views', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/analysis-views/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    del: (id) => request(`/analysis-views/${id}`, { method: 'DELETE' }),
    // 导出走原始 fetch，因为我们要拿 blob
    exportZip: async (id, filename) => {
      const token = localStorage.getItem('eval_auth_token') || '';
      const qs = filename ? `?filename=${encodeURIComponent(filename)}` : '';
      const res = await fetch(`${API_BASE}/analysis-views/${id}/export${qs}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const cd = res.headers.get('content-disposition') || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      return { blob, filename: m ? m[1] : `analysis_${id}.zip` };
    },
    // 临时导出：直接对当前勾选的 evaluation_ids 打包，不必先存模板
    exportAdhoc: async ({ evaluation_ids, filename }) => {
      const token = localStorage.getItem('eval_auth_token') || '';
      const res = await fetch(`${API_BASE}/analysis-views/export-adhoc`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ evaluation_ids, filename: filename || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const cd = res.headers.get('content-disposition') || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      return { blob, filename: m ? m[1] : 'export.zip' };
    },
  },
};

// Transform helper: flatten BatchReport rows into matrix
export function transformReportToMatrix(rows) {
  const models = [];
  const tasks = [];
  const modelMap = new Map();
  const taskMap = new Map();

  for (const row of rows) {
    if (!modelMap.has(row.model_id)) {
      modelMap.set(row.model_id, models.length);
      models.push({ id: row.model_id, name: row.model_name });
    }
    if (!taskMap.has(row.task_id)) {
      taskMap.set(row.task_id, tasks.length);
      tasks.push({ id: row.task_id, key: row.task_key });
    }
  }

  const matrix = Array(models.length).fill(null).map(() => Array(tasks.length).fill(null));

  for (const row of rows) {
    const mi = modelMap.get(row.model_id);
    const ti = taskMap.get(row.task_id);
    matrix[mi][ti] = row;
  }

  return { models, tasks, matrix };
}
