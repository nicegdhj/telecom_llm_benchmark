import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

export function RequireAdmin({ children }) {
  const { isAdmin } = useAuthStore();

  if (!isAdmin()) {
    return <Navigate to="/" replace />;
  }

  return children;
}
