import { useAuthStore } from '../../store/authStore';

export function RoleButton({
  children,
  onClick,
  variant = 'primary',
  disabled = false,
  requireWrite = true,
  className = '',
  ...props
}) {
  const { canWrite } = useAuthStore();

  const isDisabled = disabled || (requireWrite && !canWrite());

  const baseStyles = 'inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors';
  const variantStyles = {
    primary: 'bg-primary-600 text-white hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-gray-300 disabled:cursor-not-allowed',
    ghost: 'text-gray-600 hover:text-gray-900 hover:bg-gray-50 disabled:text-gray-300 disabled:cursor-not-allowed',
  };

  return (
    <button
      onClick={onClick}
      disabled={isDisabled}
      className={`${baseStyles} ${variantStyles[variant]} ${className}`}
      title={requireWrite && !canWrite() ? '需要操作员或管理员权限' : undefined}
      {...props}
    >
      {children}
    </button>
  );
}
