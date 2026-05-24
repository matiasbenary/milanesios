/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Paleta D&D: pergamino, sangre, oro, hierro
        parchment: {
          50: '#fbf5e3',
          100: '#f5e8c8',
          200: '#ecd9a1',
          300: '#dec679',
          400: '#c9a44e',
          500: '#a78030',
        },
        wine: {
          500: '#9e3438',
          600: '#7e2a2e',
          700: '#5e1f22',
          800: '#3e1416',
          900: '#260b0d',
        },
        ink: {
          500: '#3e2a1c',
          700: '#28190e',
          900: '#15100a',
        },
        gold: {
          400: '#e6c66a',
          500: '#c9a44e',
          600: '#a07e30',
        },
        oracle: {
          // azules místicos para la bola de cristal
          50:  '#c7d6ff',
          200: '#94a8e3',
          400: '#6377c0',
          600: '#3b4796',
          800: '#1e1f5e',
          900: '#0d0b30',
        },
      },
      fontFamily: {
        display: ['"Cinzel"', 'serif'],
        body: ['"Cormorant Garamond"', 'Georgia', 'serif'],
        ui: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'parchment': '0 2px 8px rgba(50, 30, 10, 0.3), inset 0 0 30px rgba(120, 80, 30, 0.15)',
        'oracle-glow': '0 0 60px 10px rgba(120, 100, 220, 0.6), inset 0 0 40px rgba(200, 200, 255, 0.4)',
      },
      backgroundImage: {
        'parchment-tex': 'radial-gradient(ellipse at top, #f5e8c8 0%, #ecd9a1 40%, #dec679 100%)',
        'page-tex':
          "linear-gradient(180deg, rgba(40,25,14,0.04) 0%, rgba(40,25,14,0.08) 100%), radial-gradient(ellipse at 30% 20%, #f5e8c8 0%, #ecd9a1 70%)",
      },
      keyframes: {
        'oracle-swirl': {
          '0%':   { transform: 'rotate(0deg) scale(1)' },
          '50%':  { transform: 'rotate(180deg) scale(1.05)' },
          '100%': { transform: 'rotate(360deg) scale(1)' },
        },
        'oracle-pulse': {
          '0%, 100%': { opacity: '0.55', transform: 'scale(1)' },
          '50%':       { opacity: '0.9',  transform: 'scale(1.07)' },
        },
      },
      animation: {
        'oracle-swirl': 'oracle-swirl 18s linear infinite',
        'oracle-pulse': 'oracle-pulse 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
