import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../../lib/api';
import { Modal } from '../../../components/ui/Modal';

export function ResetPasswordModal({ open, onClose, user }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');

  const resetMut = useMutation({
    mutationFn: ({ id, data }) => api.users.resetPassword(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setPassword('');
      setConfirmPassword('');
      setError('');
      onClose();
    },
    onError: (err) => {
      setError(err.message);
    },
  });

  function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    if (password.length < 6) {
      setError('密码长度至少为6位');
      return;
    }

    resetMut.mutate({ id: user?.id, data: { new_password: password } });
  }

  return (
    <Modal open={open} onClose={onClose} title={`重置密码 - ${user?.username || ''}`}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label">新密码 <span className="text-red-500">*</span></label>
          <input
            type="password"
            className="input"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </div>

        <div>
          <label className="label">确认密码 <span className="text-red-500">*</span></label>
          <input
            type="password"
            className="input"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            required
          />
        </div>

        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
          <button type="submit" className="btn-primary" disabled={resetMut.isPending}>
            {resetMut.isPending ? '重置中...' : '重置密码'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
