import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { Card, CardBody } from '../../components/ui/Card';
import { UserFormModal } from './components/UserFormModal';
import { ResetPasswordModal } from './components/ResetPasswordModal';
import { Plus, Pencil, Trash2, KeyRound, Users } from 'lucide-react';

const ROLE_LABELS = {
  admin: '管理员',
  operator: '操作员',
  viewer: '访客',
};

const ROLE_COLORS = {
  admin: 'bg-red-100 text-red-700',
  operator: 'bg-blue-100 text-blue-700',
  viewer: 'bg-gray-100 text-gray-700',
};

export function UsersPage() {
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);

  const { data: users, isLoading } = useQuery({ queryKey: ['users'], queryFn: api.users.list });

  const createMut = useMutation({
    mutationFn: api.users.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setFormOpen(false); },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }) => api.users.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setFormOpen(false); setEditing(null); },
  });

  const deleteMut = useMutation({
    mutationFn: api.users.del,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  function openCreate() { setEditing(null); setFormOpen(true); }
  function openEdit(u) { setEditing(u); setFormOpen(true); }
  function openReset(u) { setResetUser(u); setResetOpen(true); }

  function handleFormSubmit(data) {
    if (editing) {
      updateMut.mutate({ id: editing.id, data });
    } else {
      createMut.mutate(data);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Users size={24} className="text-primary-600" />
          <h2 className="text-2xl font-bold text-gray-900">用户管理</h2>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={openCreate}>
          <Plus size={18} /> 新增用户
        </button>
      </div>

      <Card>
        <CardBody className="p-0">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {['ID', '用户名', '显示名', '角色', '状态', '操作'].map(h => (
                  <th key={h} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {isLoading ? (
                <tr><td colSpan={6} className="px-6 py-4 text-gray-500">加载中...</td></tr>
              ) : users?.length === 0 ? (
                <tr><td colSpan={6} className="px-6 py-4 text-gray-500">暂无用户</td></tr>
              ) : users?.map(u => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{u.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{u.username}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{u.display_name || '-'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS[u.role] || ROLE_COLORS.viewer}`}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                      {u.is_active ? '启用' : '禁用'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm flex gap-2">
                    <button onClick={() => openEdit(u)} className="text-blue-600 hover:text-blue-800" title="编辑">
                      <Pencil size={16} />
                    </button>
                    <button onClick={() => openReset(u)} className="text-amber-600 hover:text-amber-800" title="重置密码">
                      <KeyRound size={16} />
                    </button>
                    <button onClick={() => deleteMut.mutate(u.id)} className="text-red-600 hover:text-red-800" title="删除">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <UserFormModal
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditing(null); }}
        onSubmit={handleFormSubmit}
        editing={editing}
        isPending={createMut.isPending || updateMut.isPending}
        error={createMut.error || updateMut.error}
      />

      <ResetPasswordModal
        open={resetOpen}
        onClose={() => { setResetOpen(false); setResetUser(null); }}
        user={resetUser}
      />
    </div>
  );
}
