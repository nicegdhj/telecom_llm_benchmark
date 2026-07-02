const STATUS_STYLES = {
  pending:    'bg-gray-100 text-gray-600',
  running:    'bg-blue-100 text-blue-700',
  success:    'bg-emerald-100 text-emerald-700',
  failed:     'bg-red-100 text-red-700',
  cancelled:  'bg-orange-100 text-orange-700',
  eval_done:  'bg-teal-100 text-teal-700',
  infer_done: 'bg-cyan-100 text-cyan-700',
};

export function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
      )}
      {status}
    </span>
  );
}
