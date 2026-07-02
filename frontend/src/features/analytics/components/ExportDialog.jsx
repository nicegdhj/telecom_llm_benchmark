import { useState, useEffect } from 'react';
import { Modal } from '../../../components/ui/Modal';
import { api } from '../../../lib/api';

/**
 * 导出 zip 弹窗：对当前勾选的 evaluation_ids 直接打包，不依赖是否已保存模板。
 * 文件名默认填模板名（或留空用「对比导出」）。
 */
export function ExportDialog({ open, onClose, selectedIds = [], defaultName }) {
  const [filename, setFilename] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setFilename(defaultName || '');
      setError(null);
    }
  }, [open, defaultName]);

  async function handleExport() {
    if (selectedIds.length === 0) {
      setError('请先勾选至少一条评测结果');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { blob, filename: returnedName } = await api.analyticsViews.exportAdhoc({
        evaluation_ids: selectedIds,
        filename: filename.trim() || null,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = returnedName || 'export.zip';
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (e) {
      setError(e.message || '导出失败');
    } finally {
      setBusy(false);
    }
  }

  const finalName = filename.trim() || defaultName || '对比导出';

  return (
    <Modal open={open} onClose={onClose} title="导出对比报告" size="md">
      <div className="space-y-4">
        <p className="text-sm text-gray-500">
          打包当前勾选的 <b>{selectedIds.length}</b> 条评测结果：
          <code>summary.xlsx</code>、<code>charts.html</code>、每条 evaluation 的原始产物目录。
        </p>
        <div>
          <label className="label">文件名（无后缀）</label>
          <input
            className="input"
            placeholder="留空则使用模板名 / 对比导出"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-1">最终文件：{finalName}.zip</p>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-secondary" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={handleExport} disabled={busy || selectedIds.length === 0}>
            {busy ? '正在打包...' : '下载 zip'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
