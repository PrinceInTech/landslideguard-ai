export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0f172a',
          light: '#1e293b',
          lighter: '#263447',
        },
        brand: {
          DEFAULT: '#f59e0b',
          dark: '#b45309',
          light: '#fbbf24',
        },
        accent: '#38bdf8',
      },
      // System stack only: the Inter webfont used to come from Google Fonts,
      // which the production CSP blocks. No runtime font download.
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
      },
    },
  },
  plugins: [],
}