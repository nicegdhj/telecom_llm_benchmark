import { useState, useEffect } from 'react';
import { Modal } from '../../../components/ui/Modal';

const ROLES = [
  { value: 'admin', label: '管理员' },
  { value: 'operator', label: '操作员' },
  { value: 'viewer', label: '访客' },
];

export function UserFormModal({ open, onClose, onSubmit, editing, isPending, error }) {
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    password: '',
    role: 'viewer',
    is_active: true,
  });

  useEffect(() => {
    if (editing) {
      setForm({
        username: editing.username || '',
        display_name: editing.display_name || '',
        password: '',
        role: editing.role || 'viewer',
        is_active: editing.is_active !== false,
      });
    } else {
      setForm({ username: '', display_name: '', password: '', role: 'viewer', is_active: true });
    }
  }, [editing, open]);

  function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    if (editing && !payload.password) {
      delete payload.password;
    }
    onSubmit(payload);
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? '编辑用户' : '新增用户'}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label">用户名 {editing ? <span className="text-gray-400">(不可修改)</span> : <span className="text-red-500">*</span>}</label>
          <input
            type="text"
            className="input"
            value={form.username}
            onChange={e => setForm({ ...form, username: e.target.value })}
            required={!editing}
            disabled={!!editing}
          />
        </div>

        <div>
          <label className="label">显示名</label>
          <input
            type="text"
            className="input"
            value={form.display_name}
            onChange={e => setForm({ ...form, display_name: e.target.value })}
          />
        </div>

        <div>
          <label className="label">密码 {editing && <span className="text-gray-400">(留空则不修改)</span>}</label>
          <input
            type="password"
            className="input"
            value={form.password}
            onChange={e => setForm({ ...form, password: e.target.value })}
            required={!editing}
          />
        </div>

        <div>
          <label className="label">角色</label>
          <select
            className="input"
            value={form.role}
            onChange={e => setForm({ ...form, role: e.target.value })}
          >
            {ROLES.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is_active"
            checked={form.is_active}
            onChange={e => setForm({ ...form, is_active: e.target.checked })}
          />
          <label htmlFor="is_active" className="text-sm text-gray-700">启用账号</label>
        </div>

        {error && (
          <p className="text-sm text-red-600">{error.message}</p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
          <button type="submit" className="btn-primary" disabled={isPending}>
            {isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
