/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // IBM Plex 在前（若本地装有则用），后接系统字体栈（含中文），内网无外链也美观
        sans: ['IBM Plex Sans', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        primary: {
          50:  '#e8f2fb',
          100: '#c5daf5',
          200: '#9ec0ee',
          300: '#73a4e6',
          400: '#4e8fdf',
          500: '#2b7acb',
          600: '#0C5CAB',
          700: '#0a4a8a',
          800: '#083b6e',
          900: '#062c52',
          950: '#03162a',
        },
      },
    },
  },
  plugins: [],
}
