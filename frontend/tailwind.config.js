/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Primary palette — indigo/violet
        primary: {
          50:  '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        violet: {
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
        },
        // Background layers
        background: {
          DEFAULT: '#0f172a', // slate-900
          card:    '#1e293b', // slate-800
          elevated:'#334155', // slate-700
        },
        // Semantic colours
        success: {
          50:  '#ecfdf5',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
        },
        warning: {
          50:  '#fffbeb',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
        },
        danger: {
          50:  '#fef2f2',
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
        },
        // Text hierarchy
        text: {
          primary:   '#f1f5f9', // slate-100
          secondary: '#cbd5e1', // slate-300
          muted:     '#94a3b8', // slate-400
          faint:     '#64748b', // slate-500
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        xl:  '0.875rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        card:   '0 4px 24px rgba(0,0,0,0.35)',
        glow:   '0 0 20px rgba(99,102,241,0.35)',
        'glow-emerald': '0 0 20px rgba(16,185,129,0.30)',
        'glow-amber':   '0 0 20px rgba(245,158,11,0.30)',
        'glow-red':     '0 0 20px rgba(239,68,68,0.30)',
      },
      backgroundImage: {
        'gradient-brand':  'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%)',
        'gradient-card':   'linear-gradient(145deg, #1e293b 0%, #162032 100%)',
        'gradient-hero':   'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(99,102,241,0.18) 0%, transparent 100%)',
        'gradient-success':'linear-gradient(135deg, #10b981, #34d399)',
        'gradient-danger': 'linear-gradient(135deg, #ef4444, #f87171)',
      },
      animation: {
        'fade-in':    'fadeIn 0.3s ease-in-out',
        'slide-up':   'slideUp 0.4s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'pulse-slow': 'pulse 2.5s cubic-bezier(0.4,0,0.6,1) infinite',
        'shimmer':    'shimmer 1.6s linear infinite',
        'bounce-soft':'bounceSoft 1s ease-in-out infinite',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%':   { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
        bounceSoft: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%':     { transform: 'translateY(-4px)' },
        },
        glowPulse: {
          '0%,100%': { boxShadow: '0 0 8px rgba(99,102,241,0.3)' },
          '50%':     { boxShadow: '0 0 24px rgba(99,102,241,0.6)' },
        },
      },
    },
  },
  plugins: [],
}
