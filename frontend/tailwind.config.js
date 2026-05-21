/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        positive: { bg: '#DCFCE7', text: '#16A34A', border: '#16A34A' },
        negative: { bg: '#FEE2E2', text: '#DC2626', border: '#DC2626' },
        neutral:  { bg: '#FEF9C3', text: '#CA8A04', border: '#D97706' },
      },
    },
  },
  plugins: [],
}
