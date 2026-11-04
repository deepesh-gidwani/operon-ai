/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#090c12',
        panel: '#0f141e',
        raised: '#151c29',
        edge: '#1e2635',
        accent: {
          DEFAULT: '#4d84ff',
          soft: '#8db0ff',
          dim: '#24406e',
        },
        success: '#3ecf8e',
        warn: '#d9a13b',
        danger: '#f26d6d',
      },
      fontFamily: {
        display: ['Sora', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
