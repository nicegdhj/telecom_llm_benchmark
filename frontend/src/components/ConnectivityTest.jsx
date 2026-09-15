import { useState } from 'react';
import { Zap, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

/**
 * 连通性测试按钮 + 内联结果。
 * props.onTest: () => Promise<{ ok, status, latency_ms, message, reply }>
 */
export function ConnectivityTest({ onTest, disabled }) {
  const [state, setState] = useState('idle'); // idle | testing | done
  const [result, setResult] = useState(null);

  async function run() {
    setState('testing');
    setResult(null);
    try {
      const r = await onTest();
      setResult(r);
    } catch (e) {
      setResult({ ok: false, message: e?.message || '请求失败' });
    } finally {
      setState('done');
    }
  }

  const testing = state === 'testing';

  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <button
        type="button"
        onClick={run}
        disabled={disabled || testing}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-primary-600 hover:text-primary-700 hover:bg-primary-50 px-2 py-1 -ml-2 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {testing
          ? <Loader2 size={13} className="animate-spin" />
          : <Zap size={13} />}
        {testing ? '测试中…' : '连通性测试'}
      </button>

      {result && (
        <div
          className={`mt-2 flex items-start gap-1.5 rounded-md px-2 py-1.5 text-xs ${
            result.ok
              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100'
              : 'bg-red-50 text-red-700 ring-1 ring-red-100'
          }`}
        >
          {result.ok
            ? <CheckCircle2 size={13} className="mt-px flex-shrink-0" />
            : <XCircle size={13} className="mt-px flex-shrink-0" />}
          <div className="min-w-0">
            {result.ok ? (
              <>
                <span className="font-medium">连通正常</span>
                {result.latency_ms != null && (
                  <span className="text-emerald-600/80"> · {result.latency_ms}ms</span>
                )}
                {result.reply && (
                  <div className="mt-0.5 text-emerald-600/80 break-words line-clamp-2" title={result.reply}>
                    回复：{result.reply}
                  </div>
                )}
              </>
            ) : (
              <span className="break-words" title={result.message}>{result.message}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
