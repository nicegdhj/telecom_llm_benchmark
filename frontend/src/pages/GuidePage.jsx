import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowLeft, BookOpen } from 'lucide-react';
// 单一数据源：直接渲染仓库内的用户手册 Markdown（构建时打包进静态产物）
import guideMd from '../../../my_doc/platform_user_guide.md?raw';

// react-markdown 各元素的样式覆盖（项目未引入 tailwind typography，故逐项指定）
const components = {
  h1: ({ children }) => <h1 className="text-2xl font-bold text-gray-900 mt-2 mb-4 pb-2 border-b border-gray-200">{children}</h1>,
  h2: ({ children }) => <h2 className="text-xl font-bold text-gray-900 mt-8 mb-3">{children}</h2>,
  h3: ({ children }) => <h3 className="text-base font-semibold text-gray-800 mt-5 mb-2">{children}</h3>,
  p: ({ children }) => <p className="text-[14px] leading-7 text-gray-700 my-3">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-6 my-3 space-y-1 text-[14px] text-gray-700">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-6 my-3 space-y-1 text-[14px] text-gray-700">{children}</ol>,
  li: ({ children }) => <li className="leading-7">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
  a: ({ href, children }) => <a href={href} className="text-primary-600 hover:underline">{children}</a>,
  hr: () => <hr className="my-6 border-gray-100" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-primary-200 bg-blue-50/50 px-4 py-2 my-4 text-[13px] text-gray-600 rounded-r">{children}</blockquote>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code className="bg-gray-100 text-primary-700 px-1.5 py-0.5 rounded text-[13px] font-mono">{children}</code>
    ) : (
      <code className="block bg-gray-950 text-gray-100 p-4 rounded-lg text-xs font-mono overflow-x-auto my-4 whitespace-pre">{children}</code>
    ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-4">
      <table className="min-w-full border border-gray-200 rounded-lg text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  th: ({ children }) => <th className="border border-gray-200 px-3 py-2 text-left font-semibold text-gray-600">{children}</th>,
  td: ({ children }) => <td className="border border-gray-200 px-3 py-2 text-gray-700 align-top">{children}</td>,
};

export function GuidePage() {
  const navigate = useNavigate();
  return (
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors mb-4"
      >
        <ArrowLeft size={15} /> 返回
      </button>
      <div className="bg-white border border-gray-200 rounded-xl p-8 shadow-sm">
        <div className="flex items-center gap-2 text-primary-600 mb-2">
          <BookOpen size={20} />
          <span className="text-sm font-semibold">使用手册</span>
        </div>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {guideMd}
        </ReactMarkdown>
      </div>
    </div>
  );
}
