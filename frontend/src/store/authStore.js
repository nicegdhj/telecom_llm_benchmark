import { create } from 'zustand';

function loadUser() {
  try {
    return JSON.parse(localStorage.getItem('eval_auth_user') || 'null');
  } catch {
    return null;
  }
}

export const useAuthStore = create((set, get) => ({
  token: localStorage.getItem('eval_auth_token') || '',
  user: loadUser(),

  setSession: ({ session_token, user }) => {
    localStorage.setItem('eval_auth_token', session_token);
    localStorage.setItem('eval_auth_user', JSON.stringify(user));
    set({ token: session_token, user });
  },

  clearSession: () => {
    localStorage.removeItem('eval_auth_token');
    localStorage.removeItem('eval_auth_user');
    set({ token: '', user: null });
  },

  isAuthenticated: () => !!get().token && !!get().user,
  isAdmin: () => get().user?.role === 'admin',
  canWrite: () => ['admin', 'operator'].includes(get().user?.role),
}));
