import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#0a0b0e',
        surface: {
          DEFAULT: '#12151c',
          muted: '#181c26',
          border: '#242b3b',
        },
        brand: {
          blue: '#3b82f6',
          cyan: '#06b6d4',
          accent: '#0ea5e9',
        },
      },
    },
  },
  plugins: [],
};

export default config;
