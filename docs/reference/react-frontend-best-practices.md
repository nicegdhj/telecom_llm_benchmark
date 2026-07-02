
React 前端最佳实践参考指南
================

一份关于使用 Vite 和 Tailwind CSS 构建现代 React 应用程序的简明参考指南。

* * *

目录
--

1.  [项目结构](https://www.google.com/search?q=%231-%E9%A1%B9%E7%9B%AE%E7%BB%93%E6%9E%84)
2.  [组件设计](https://www.google.com/search?q=%232-%E7%BB%84%E4%BB%B6%E8%AE%BE%E8%AE%A1)
3.  [状态管理](https://www.google.com/search?q=%233-%E7%8A%B6%E6%80%81%E7%AE%A1%E7%90%86)
4.  [数据获取](https://www.google.com/search?q=%234-%E6%95%B0%E6%8D%AE%E8%8E%B7%E5%8F%96)
5.  [表单与验证](https://www.google.com/search?q=%235-%E8%A1%A8%E5%8D%95%E4%B8%8E%E9%AA%8C%E8%AF%81)
6.  [使用 Tailwind 进行样式设计](https://www.google.com/search?q=%236-%E4%BD%BF%E7%94%A8-tailwind-%E8%BF%9B%E8%A1%8C%E6%A0%B7%E5%BC%8F%E8%AE%BE%E8%AE%A1)
7.  [性能](https://www.google.com/search?q=%237-%E6%80%A7%E8%83%BD)
8.  [Hooks 模式](https://www.google.com/search?q=%238-hooks-%E6%A8%A1%E5%BC%8F)
9.  [路由](https://www.google.com/search?q=%239-%E8%B7%AF%E7%94%B1)
10.  [错误处理](https://www.google.com/search?q=%2310-%E9%94%99%E8%AF%AF%E5%A4%84%E7%90%86)
11.  [测试](https://www.google.com/search?q=%2311-%E6%B5%8B%E8%AF%95)
12.  [可访问性](https://www.google.com/search?q=%2312-%E5%8F%AF%E8%AE%BF%E9%97%AE%E6%80%A7)
13.  [反模式](https://www.google.com/search?q=%2313-%E5%8F%8D%E6%A8%A1%E5%BC%8F)

* * *

1\. 项目结构
--------

### 基于功能的结构（推荐）

```
src/
├── features/
│   ├── habits/
│   │   ├── components/
│   │   │   ├── HabitCard.jsx
│   │   │   ├── HabitForm.jsx
│   │   │   └── HabitList.jsx
│   │   ├── hooks/
│   │   │   └── useHabits.js
│   │   ├── api/
│   │   │   └── habits.js
│   │   └── index.js           # 公共导出
│   └── calendar/
│       ├── components/
│       ├── hooks/
│       └── index.js
├── components/                 # 共享/公共组件
│   ├── ui/
│   │   ├── Button.jsx
│   │   ├── Card.jsx
│   │   └── Modal.jsx
│   └── layout/
│       ├── Header.jsx
│       └── Layout.jsx
├── hooks/                      # 共享 hooks
│   └── useLocalStorage.js
├── lib/                        # 实用程序
│   ├── api.js                  # API 客户端
│   └── utils.js
├── pages/                      # 路由页面
│   ├── Dashboard.jsx
│   └── HabitDetail.jsx
├── App.jsx
├── main.jsx
└── index.css
```

### 文件命名规范

| 类型  | 规范  | 示例  |
| --- | --- | --- |
| 组件  | PascalCase | `HabitCard.jsx` |
| Hooks | camelCase, `use` 前缀 | `useHabits.js` |
| 实用程序 | camelCase | `formatDate.js` |
| 常量  | SCREAMING\_SNAKE\_CASE | `API_BASE_URL` |
| CSS/样式 | kebab-case | `habit-card.css` |

### 桶式导出 (Barrel Exports)

```
// features/habits/index.js
export { HabitCard } from './components/HabitCard';
export { HabitForm } from './components/HabitForm';
export { useHabits } from './hooks/useHabits';

// 在其他地方使用
import { HabitCard, useHabits } from '@/features/habits';
```

**注意**：在大型项目中，桶式导出可能会损害 Tree-shaking 效果并延长构建时间。请谨慎使用。

* * *

2\. 组件设计
--------

### 函数组件

```
// 简单组件
function HabitCard({ habit, onComplete }) {
  return (
    <div className="p-4 border rounded">
      <h3>{habit.name}</h3>
      <button onClick={() => onComplete(habit.id)}>Complete</button>
    </div>
  );
}

// 带有默认 Props
function HabitCard({ habit, onComplete, showStreak = true }) {
  // ...
}

// 在参数中解构
function HabitCard({ habit: { id, name, streak }, onComplete }) {
  // ...
}
```

### 组件组合

```
// 复合组件模式
function Card({ children, className }) {
  return <div className={`border rounded ${className}`}>{children}</div>;
}

Card.Header = function CardHeader({ children }) {
  return <div className="p-4 border-b font-bold">{children}</div>;
};

Card.Body = function CardBody({ children }) {
  return <div className="p-4">{children}</div>;
};

// 使用
<Card>
  <Card.Header>Habit Details</Card.Header>
  <Card.Body>Content here</Card.Body>
</Card>
```

### Props 设计

```
// 优先使用具体的 Props 而非展开操作
// 正确做法
function Button({ onClick, disabled, children, variant = 'primary' }) {
  return <button onClick={onClick} disabled={disabled}>{children}</button>;
}

// 避免过度展开
// 错误做法 - 很难知道接收了哪些 Props
function Button(props) {
  return <button {...props} />;
}

// 接收 className 以提高样式灵活性
function Card({ children, className = '' }) {
  return <div className={`base-styles ${className}`}>{children}</div>;
}
```

### Children 模式

```
// 使用 Children 进行组合
function Layout({ children }) {
  return (
    <div className="container mx-auto">
      <Header />
      <main>{children}</main>
      <Footer />
    </div>
  );
}

// 使用 Render props 获得更多控制权
function HabitList({ habits, renderItem }) {
  return (
    <ul>
      {habits.map(habit => (
        <li key={habit.id}>{renderItem(habit)}</li>
      ))}
    </ul>
  );
}

// 使用
<HabitList
  habits={habits}
  renderItem={(habit) => <HabitCard habit={habit} />}
/>
```

* * *

3\. 状态管理
--------

### 何时使用什么

| 状态类型 | 解决方案 |
| --- | --- |
| 服务器/异步数据 | TanStack Query |
| 表单状态 | react-hook-form 或 useState |
| 本地 UI 状态 | useState |
| 共享 UI 状态 | Context 或 Zustand |
| URL 状态 | React Router |

### useState 最佳实践

```
// 对相关状态进行分组
const [habit, setHabit] = useState({ name: '', description: '' });

// vs 多个 useState（适用于相互独立的值）
const [name, setName] = useState('');
const [isOpen, setIsOpen] = useState(false);

// 基于前一个值进行状态更新时使用函数式更新
setCount(prev => prev + 1);

// 惰性初始化开销较大的状态
const [data, setData] = useState(() => expensiveComputation());
```

### 状态提升

```
// 父组件拥有状态，子组件通过 props 接收
function Dashboard() {
  const [selectedDate, setSelectedDate] = useState(new Date());

  return (
    <>
      <DatePicker date={selectedDate} onChange={setSelectedDate} />
      <HabitList date={selectedDate} />
      <Stats date={selectedDate} />
    </>
  );
}
```

### Context API

```
// 创建 context
const HabitContext = createContext(null);

// Provider 组件
function HabitProvider({ children }) {
  const [habits, setHabits] = useState([]);

  const value = {
    habits,
    addHabit: (habit) => setHabits(prev => [...prev, habit]),
    removeHabit: (id) => setHabits(prev => prev.filter(h => h.id !== id)),
  };

  return (
    <HabitContext.Provider value={value}>
      {children}
    </HabitContext.Provider>
  );
}

// 用于消费 context 的自定义 hook
function useHabitContext() {
  const context = useContext(HabitContext);
  if (!context) {
    throw new Error('useHabitContext must be used within HabitProvider');
  }
  return context;
}

// 使用
function HabitList() {
  const { habits, removeHabit } = useHabitContext();
  // ...
}
```

### Zustand (Redux 的简单替代方案)

```
// store/habits.js
import { create } from 'zustand';

const useHabitStore = create((set) => ({
  selectedHabitId: null,
  filterStatus: 'all',
  setSelectedHabit: (id) => set({ selectedHabitId: id }),
  setFilter: (status) => set({ filterStatus: status }),
}));

// 在组件中使用
function HabitFilter() {
  const { filterStatus, setFilter } = useHabitStore();
  // ...
}
```

* * *

4\. 数据获取
--------

### TanStack Query 设置

```
// main.jsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 分钟
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router />
    </QueryClientProvider>
  );
}
```

### 基础查询

```
// hooks/useHabits.js
import { useQuery } from '@tanstack/react-query';
import { fetchHabits } from '../api/habits';

export function useHabits() {
  return useQuery({
    queryKey: ['habits'],
    queryFn: fetchHabits,
  });
}

// 在组件中使用
function HabitList() {
  const { data: habits, isLoading, error } = useHabits();

  if (isLoading) return <Spinner />;
  if (error) return <Error message={error.message} />;

  return (
    <ul>
      {habits.map(habit => <HabitCard key={habit.id} habit={habit} />)}
    </ul>
  );
}
```

### 带参数的查询

```
export function useHabit(habitId) {
  return useQuery({
    queryKey: ['habits', habitId],
    queryFn: () => fetchHabit(habitId),
    enabled: !!habitId, // 仅在 habitId 存在时运行
  });
}

export function useCompletions(habitId, month) {
  return useQuery({
    queryKey: ['completions', habitId, month],
    queryFn: () => fetchCompletions(habitId, month),
  });
}
```

### 变更 (Mutations)

```
import { useMutation, useQueryClient } from '@tanstack/react-query';

export function useCreateHabit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createHabit,
    onSuccess: () => {
      // 使查询失效并重新获取
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
  });
}

export function useCompleteHabit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ habitId, date }) => completeHabit(habitId, date),
    onSuccess: (_, { habitId }) => {
      queryClient.invalidateQueries({ queryKey: ['habits'] });
      queryClient.invalidateQueries({ queryKey: ['completions', habitId] });
    },
  });
}

// 使用
function HabitCard({ habit }) {
  const { mutate: complete, isPending } = useCompleteHabit();

  return (
    <button
      onClick={() => complete({ habitId: habit.id, date: today })}
      disabled={isPending}
    >
      {isPending ? 'Saving...' : 'Complete'}
    </button>
  );
}
```

### 乐观更新

```
export function useCompleteHabit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: completeHabit,
    onMutate: async ({ habitId, date }) => {
      // 取消任何传出的重新获取请求
      await queryClient.cancelQueries({ queryKey: ['habits'] });

      // 快照之前的值
      const previousHabits = queryClient.getQueryData(['habits']);

      // 乐观更新
      queryClient.setQueryData(['habits'], (old) =>
        old.map(h => h.id === habitId
          ? { ...h, completedToday: true, currentStreak: h.currentStreak + 1 }
          : h
        )
      );

      return { previousHabits };
    },
    onError: (err, variables, context) => {
      // 发生错误时回滚
      queryClient.setQueryData(['habits'], context.previousHabits);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['habits'] });
    },
  });
}
```

### API 客户端

```
// lib/api.js
const API_BASE = '/api';

async function request(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'An error occurred');
  }

  if (response.status === 204) return null;
  return response.json();
}

// api/habits.js
export const fetchHabits = () => request('/habits');
export const fetchHabit = (id) => request(`/habits/${id}`);
export const createHabit = (data) => request('/habits', { method: 'POST', body: JSON.stringify(data) });
export const completeHabit = (id, date) => request(`/habits/${id}/complete`, { method: 'POST', body: JSON.stringify({ date }) });
```

* * *

5\. 表单与验证
---------

### React Hook Form + Zod

```
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const habitSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().max(500).optional(),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, 'Invalid color').default('#10B981'),
});

function HabitForm({ onSubmit, defaultValues }) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm({
    resolver: zodResolver(habitSchema),
    defaultValues,
  });

  const handleFormSubmit = async (data) => {
    await onSubmit(data);
    reset();
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)}>
      <div>
        <label htmlFor="name">Name</label>
        <input
          id="name"
          {...register('name')}
          className={errors.name ? 'border-red-500' : ''}
        />
        {errors.name && <span className="text-red-500">{errors.name.message}</span>}
      </div>

      <div>
        <label htmlFor="description">Description</label>
        <textarea id="description" {...register('description')} />
        {errors.description && <span className="text-red-500">{errors.description.message}</span>}
      </div>

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Saving...' : 'Save'}
      </button>
    </form>
  );
}
```

### 简单受控表单

```
function SimpleForm({ onSubmit }) {
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    onSubmit({ name });
    setName('');
    setError('');
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Habit name"
      />
      {error && <span className="text-red-500">{error}</span>}
      <button type="submit">Add</button>
    </form>
  );
}
```

* * *

6\. 使用 Tailwind 进行样式设计
----------------------

### Vite 配置

```
// vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
});

// tailwind.config.js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#10B981',
      },
    },
  },
  plugins: [],
};

// src/index.css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### 组件样式模式

```
// 内联类
function Button({ children, variant = 'primary' }) {
  const baseClasses = 'px-4 py-2 rounded font-medium transition-colors';
  const variantClasses = {
    primary: 'bg-primary text-white hover:bg-primary/90',
    secondary: 'bg-gray-200 text-gray-800 hover:bg-gray-300',
    danger: 'bg-red-500 text-white hover:bg-red-600',
  };

  return (
    <button className={`${baseClasses} ${variantClasses[variant]}`}>
      {children}
    </button>
  );
}

// 使用 clsx 处理条件类
import clsx from 'clsx';

function HabitCard({ habit, isCompleted }) {
  return (
    <div className={clsx(
      'p-4 border rounded',
      isCompleted && 'bg-green-50 border-green-200',
      !isCompleted && 'bg-white border-gray-200'
    )}>
      {habit.name}
    </div>
  );
}
```

### 响应式设计

```
// 移动端优先方法
<div className="
  p-2 md:p-4 lg:p-6
  grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4
  text-sm md:text-base
">
  {/* 内容 */}
</div>

// 断点：sm(640px) md(768px) lg(1024px) xl(1280px) 2xl(1536px)
```

### 常见模式

```
// 卡片
<div className="bg-white rounded-lg shadow-md p-4">

// Flex 居中
<div className="flex items-center justify-center">

// 网格布局
<div className="grid grid-cols-7 gap-1">

// 文本截断
<p className="truncate">Long text...</p>

// 焦点环
<button className="focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2">

// 禁用状态
<button className="disabled:opacity-50 disabled:cursor-not-allowed" disabled={isPending}>
```

* * *

7\. 性能
------

### React.memo

```
// 仅在 props 更改时重新渲染
const HabitCard = memo(function HabitCard({ habit, onComplete }) {
  return (
    <div>
      <h3>{habit.name}</h3>
      <button onClick={() => onComplete(habit.id)}>Complete</button>
    </div>
  );
});

// 自定义比较
const HabitCard = memo(function HabitCard({ habit, onComplete }) {
  // ...
}, (prevProps, nextProps) => {
  return prevProps.habit.id === nextProps.habit.id &&
         prevProps.habit.completedToday === nextProps.habit.completedToday;
});
```

### useCallback 和 useMemo

```
// useCallback - 缓存传递给子组件的函数
function HabitList({ habits }) {
  const handleComplete = useCallback((id) => {
    // ...
  }, []); // 空依赖项 = 稳定的引用

  return habits.map(h => (
    <HabitCard key={h.id} habit={h} onComplete={handleComplete} />
  ));
}

// useMemo - 缓存开销较大的计算结果
function Stats({ completions }) {
  const stats = useMemo(() => {
    return calculateExpensiveStats(completions);
  }, [completions]);

  return <div>{stats.average}</div>;
}
```

**何时使用**：

*   `useCallback`：传递给经 memo 处理过的子组件的函数
*   `useMemo`：开销较大的计算，或者用于依赖项的引用一致性

**何时不使用**：

*   简单的计算
*   原始类型值
*   未传递给子组件的函数

### 代码分割

```
import { lazy, Suspense } from 'react';

// 延迟加载路由
const Settings = lazy(() => import('./pages/Settings'));
const Analytics = lazy(() => import('./pages/Analytics'));

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Suspense>
  );
}
```

### 列表虚拟化

```
// 对于超长列表 (1000+ 项)，使用 react-window
import { FixedSizeList } from 'react-window';

function VirtualizedList({ items }) {
  return (
    <FixedSizeList
      height={400}
      width="100%"
      itemCount={items.length}
      itemSize={50}
    >
      {({ index, style }) => (
        <div style={style}>{items[index].name}</div>
      )}
    </FixedSizeList>
  );
}
```

* * *

8\. Hooks 模式
------------

### 自定义 Hooks

```
// useLocalStorage
function useLocalStorage(key, initialValue) {
  const [value, setValue] = useState(() => {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : initialValue;
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue];
}

// useDebounce
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// useToggle
function useToggle(initialValue = false) {
  const [value, setValue] = useState(initialValue);
  const toggle = useCallback(() => setValue(v => !v), []);
  return [value, toggle];
}
```

### useEffect 模式

```
// 清理函数
useEffect(() => {
  const controller = new AbortController();

  fetch('/api/data', { signal: controller.signal })
    .then(res => res.json())
    .then(setData);

  return () => controller.abort(); // 卸载时清理
}, []);

// 事件监听器
useEffect(() => {
  const handleResize = () => setWidth(window.innerWidth);
  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, []);

// 与外部系统同步
useEffect(() => {
  const subscription = externalStore.subscribe(setData);
  return () => subscription.unsubscribe();
}, []);
```

### useEffect 陷阱

```
// 错误做法：缺失依赖项
useEffect(() => {
  fetchData(userId); // userId 不在依赖项中 - 闭包陷阱
}, []);

// 正确做法：包含所有依赖项
useEffect(() => {
  fetchData(userId);
}, [userId]);

// 错误做法：在依赖项中使用对象/数组（每次渲染都会产生新引用）
useEffect(() => {
  doSomething(options); // options = {} 每次渲染都会创建新对象
}, [options]);

// 正确做法：使用 memo 或者原始类型值
const memoizedOptions = useMemo(() => options, [options.key1, options.key2]);
useEffect(() => {
  doSomething(memoizedOptions);
}, [memoizedOptions]);
```

* * *

9\. 路由
------

### React Router v6 设置

```
// App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="habits/:habitId" element={<HabitDetail />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### 布局路由

```
// Layout.jsx
import { Outlet, Link } from 'react-router-dom';

function Layout() {
  return (
    <div className="min-h-screen">
      <nav className="bg-white shadow">
        <Link to="/">Dashboard</Link>
        <Link to="/settings">Settings</Link>
      </nav>
      <main className="container mx-auto p-4">
        <Outlet /> {/* 子路由在此渲染 */}
      </main>
    </div>
  );
}
```

### 路由参数

```
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';

function HabitDetail() {
  const { habitId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const month = searchParams.get('month') || getCurrentMonth();

  return (
    <div>
      <button onClick={() => navigate('/')}>Back</button>
      <button onClick={() => setSearchParams({ month: 'next' })}>
        Next Month
      </button>
    </div>
  );
}
```

### 导航

```
import { Link, NavLink, useNavigate } from 'react-router-dom';

// 简单链接
<Link to="/settings">Settings</Link>

// 激活样式
<NavLink
  to="/"
  className={({ isActive }) => isActive ? 'text-primary' : 'text-gray-600'}
>
  Dashboard
</NavLink>

// 程序化导航
const navigate = useNavigate();
navigate('/habits/1');
navigate(-1); // 后退
navigate('/', { replace: true }); // 替换历史记录
```

* * *

10\. 错误处理
---------

### 错误边界

```
import { Component } from 'react';

class ErrorBoundary extends Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught:', error, errorInfo);
    // 发送到错误追踪服务
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-4 text-red-500">
          <h2>Something went wrong</h2>
          <button onClick={() => this.setState({ hasError: false })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// 使用
<ErrorBoundary fallback={<ErrorPage />}>
  <App />
</ErrorBoundary>
```

### 异步错误处理

```
function HabitList() {
  const { data, error, isError } = useHabits();

  if (isError) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded">
        <p>Failed to load habits: {error.message}</p>
        <button onClick={() => refetch()}>Retry</button>
      </div>
    );
  }

  return <ul>{/* ... */}</ul>;
}
```

### Toast 通知

```
// 使用 react-hot-toast 等通知库
import toast from 'react-hot-toast';

function useCreateHabit() {
  return useMutation({
    mutationFn: createHabit,
    onSuccess: () => {
      toast.success('Habit created!');
    },
    onError: (error) => {
      toast.error(`Failed: ${error.message}`);
    },
  });
}
```

* * *

11\. 测试
-------

### 使用 Vitest 进行设置

```
// vite.config.js
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
});

// src/test/setup.js
import '@testing-library/jest-dom';
```

### 组件测试

```
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('HabitCard', () => {
  it('renders habit name', () => {
    render(<HabitCard habit={{ id: 1, name: 'Exercise' }} />);
    expect(screen.getByText('Exercise')).toBeInTheDocument();
  });

  it('calls onComplete when button clicked', async () => {
    const onComplete = vi.fn();
    render(<HabitCard habit={{ id: 1, name: 'Exercise' }} onComplete={onComplete} />);

    await userEvent.click(screen.getByRole('button', { name: /complete/i }));

    expect(onComplete).toHaveBeenCalledWith(1);
  });
});
```

### 带 Provider 的测试

```
// test/utils.jsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

export function renderWithProviders(ui) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

### 模拟 API 调用

```
import { vi } from 'vitest';
import * as api from '../api/habits';

vi.mock('../api/habits');

it('loads and displays habits', async () => {
  api.fetchHabits.mockResolvedValue([
    { id: 1, name: 'Exercise' },
  ]);

  renderWithProviders(<HabitList />);

  await waitFor(() => {
    expect(screen.getByText('Exercise')).toBeInTheDocument();
  });
});
```

* * *

12\. 可访问性
---------

### 语义化 HTML

```
// 使用语义化元素
<header>...</header>
<nav>...</nav>
<main>...</main>
<article>...</article>
<aside>...</aside>
<footer>...</footer>

// 正确使用标题层级 (h1 > h2 > h3)
<h1>Dashboard</h1>
<section>
  <h2>Today's Habits</h2>
</section>
```

### ARIA 属性

```
// 标签
<button aria-label="Close modal">×</button>

// Live regions（用于动态内容）
<div aria-live="polite" aria-atomic="true">
  {statusMessage}
</div>

// 状态
<button aria-pressed={isCompleted}>Complete</button>
<button aria-expanded={isOpen}>Menu</button>

// 角色
<div role="alert">{errorMessage}</div>
```

### 焦点管理

```
// 模态框中的焦点捕获
function Modal({ isOpen, onClose, children }) {
  const modalRef = useRef();

  useEffect(() => {
    if (isOpen) {
      modalRef.current?.focus();
    }
  }, [isOpen]);

  return isOpen ? (
    <div
      ref={modalRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
    >
      {children}
    </div>
  ) : null;
}
```

### 键盘导航

```
// 处理键盘交互
function ListItem({ onSelect }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
    >
      Item
    </div>
  );
}
```

* * *

13\. 反模式
--------

### 常见错误

| 反模式 | 问题  | 解决方案 |
| --- | --- | --- |
| Props 钻取 (Drilling) | 难以维护 | 使用 Context 或组件组合 |
| 巨型组件 | 难以测试/维护 | 拆分为更小的组件 |
| 使用 useEffect 处理派生状态 | 增加不必要的复杂度 | 在渲染期间直接计算 |
| 使用索引作为 key | 导致列表重新排序时的 bug | 使用稳定的唯一 ID |
| 直接操作 DOM | 与 React 产生冲突 | 谨慎使用 refs |

### 代码示例

```
// 错误做法：在 useEffect 中处理派生状态
const [fullName, setFullName] = useState('');
useEffect(() => {
  setFullName(`${firstName} ${lastName}`);
}, [firstName, lastName]);

// 正确做法：在渲染期间计算
const fullName = `${firstName} ${lastName}`;

// 错误做法：使用索引作为 key（在列表变化时会导致 bug）
{items.map((item, index) => <Item key={index} item={item} />)}

// 正确做法：使用稳定的唯一 ID
{items.map(item => <Item key={item.id} item={item} />)}

// 错误做法：在 useEffect 中获取数据且没有清理机制
useEffect(() => {
  fetch('/api/data').then(res => res.json()).then(setData);
}, []);

// 正确做法：使用 TanStack Query 或添加清理逻辑
useEffect(() => {
  let cancelled = false;
  fetch('/api/data')
    .then(res => res.json())
    .then(data => { if (!cancelled) setData(data); });
  return () => { cancelled = true; };
}, []);
```

* * *

快速参考
----

### 常用导入

```
// React
import { useState, useEffect, useCallback, useMemo, useRef, memo, createContext, useContext } from 'react';

// React Router
import { BrowserRouter, Routes, Route, Link, useParams, useNavigate } from 'react-router-dom';

// TanStack Query
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// Form
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
```

* * *

资源
--

*   [React 官方文档](https://react.dev/)
*   [TanStack Query](https://tanstack.com/query/latest)
*   [React Router](https://reactrouter.com/)
*   [Tailwind CSS](https://tailwindcss.com/)
*   [React Hook Form](https://react-hook-form.com/)
*   [Zod](https://zod.dev/)

