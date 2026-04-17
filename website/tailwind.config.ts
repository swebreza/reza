import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

const config: Config = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        teal: {
          DEFAULT: '#00d4aa',
          50: '#e6fff9',
          100: '#b3ffe9',
          200: '#66ffd4',
          300: '#1affbe',
          400: '#00e5b0',
          500: '#00d4aa',
          600: '#00a880',
          700: '#007d5f',
          800: '#00523f',
          900: '#002720',
        },
        sky: {
          brand: '#38b2f8',
        },
        indigo: {
          brand: '#7c5cfc',
        },
        navy: '#0d1117',
        surface: {
          dark: '#131920',
          darker: '#0b0f16',
        },
      },
      fontFamily: {
        syne: ['var(--font-syne)', 'sans-serif'],
        dm: ['var(--font-dm-sans)', 'sans-serif'],
        mono: ['var(--font-jetbrains)', 'monospace'],
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #00d4aa 0%, #38b2f8 50%, #7c5cfc 100%)',
        'brand-gradient-r': 'linear-gradient(270deg, #00d4aa 0%, #38b2f8 50%, #7c5cfc 100%)',
      },
      animation: {
        'fade-up': 'fadeUp 0.6s ease-out forwards',
        'fade-in': 'fadeIn 0.4s ease-out forwards',
        'counter': 'counter 2s ease-out forwards',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(24px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: 'none',
          },
        },
      },
    },
  },
  plugins: [typography],
}

export default config
