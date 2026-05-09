/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#020617',
        surface: '#0f172a',
        border: '#1e293b',
        primary: '#0ea5e9',
        'primary-hover': '#38bdf8',
        accent: '#ac4bff',
        success: '#00c758',
        muted: '#7dd3fc',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        heading: ['"Plus Jakarta Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
