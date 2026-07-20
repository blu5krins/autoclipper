/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        surface: '#18181b',
        border: '#27272a',
        primary: '#3b82f6',
        accent: '#8b5cf6',
      },
    },
  },
  plugins: [],
}
