export function userDisplay(user) {
  if (!user) return '已删除用户';
  if (typeof user === 'string') return user;
  const name = user.display_name || user.username || user.email || `User #${user.id}`;
  if (user.is_active === false) return `${name}（已停用）`;
  return name;
}

export function userBadge(user) {
  if (!user) return '-';
  const name = userDisplay(user);
  if (user.role) {
    return `${name} (${user.role})`;
  }
  return name;
}
