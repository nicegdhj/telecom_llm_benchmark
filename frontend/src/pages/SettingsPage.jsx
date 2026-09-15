import { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';
import { Card, CardHeader, CardBody } from '../components/ui/Card';
import { User, Lock } from 'lucide-react';
import { userDisplay } from '../lib/userDisplay';

export function SettingsPage() {
  const { user } = useAuthStore();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  async function handleChangePassword(e) {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (newPassword !== confirmPassword) {
      setPasswordError('两次输入的新密码不一致');
      return;
    }

    if (newPassword.length < 6) {
      setPasswordError('新密码长度至少为6位');
      return;
    }

    setChangingPassword(true);
    try {
      await api.auth.changePassword({
        old_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess('密码修改成功');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPasswordError(err.message || '密码修改失败');
    } finally {
      setChangingPassword(false);
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">设置</h2>

      {/* 用户信息卡片 */}
      <Card>
        <CardHeader className="flex items-center gap-2">
          <User size={20} className="text-primary-600" />
          <h3 className="text-base font-semibold">当前用户</h3>
        </CardHeader>
        <CardBody className="space-y-3">
          {user ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">用户名</span>
                <span className="text-sm font-medium text-gray-900">{user.username}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">显示名</span>
                <span className="text-sm font-medium text-gray-900">{user.display_name || '-'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">角色</span>
                <span className="text-sm font-medium text-gray-900">
                  {user.role === 'admin' ? '管理员' : user.role === 'operator' ? '操作员' : '访客'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">显示名称</span>
                <span className="text-sm font-medium text-gray-900">{userDisplay(user)}</span>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-500">未登录</p>
          )}
        </CardBody>
      </Card>

      {/* 修改密码卡片 */}
      <Card>
        <CardHeader className="flex items-center gap-2">
          <Lock size={20} className="text-primary-600" />
          <h3 className="text-base font-semibold">修改密码</h3>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
            <div>
              <label className="label">当前密码</label>
              <input
                type="password"
                className="input"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label">新密码</label>
              <input
                type="password"
                className="input"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>
            <div>
              <label className="label">确认新密码</label>
              <input
                type="password"
                className="input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            {passwordError && (
              <p className="text-sm text-red-600">{passwordError}</p>
            )}
            {passwordSuccess && (
              <p className="text-sm text-green-600">{passwordSuccess}</p>
            )}

            <button
              type="submit"
              className="btn-primary"
              disabled={changingPassword}
            >
              {changingPassword ? '修改中...' : '修改密码'}
            </button>
          </form>
        </CardBody>
      </Card>

    </div>
  );
}
