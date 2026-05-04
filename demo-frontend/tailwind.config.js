/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        kitty: {
          50: '#FFF5F8',
          100: '#FFE8EE',
          200: '#FFD1DC',
          300: '#FFB3C6',
          400: '#FF6B8A',
          500: '#FF4D73',
          600: '#E4002B',
          700: '#B80023',
          800: '#8C001B',
          900: '#600013',
        },
        mint: {
          400: '#7ECDA0',
          500: '#5CB882',
        },
        gold: {
          400: '#FFCF70',
          500: '#FFC040',
        },
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      backgroundImage: {
        'kitty-gradient': 'linear-gradient(135deg, #FF6B8A 0%, #FFD1DC 50%, #FFF5F8 100%)',
        'kitty-gradient-soft': 'linear-gradient(135deg, #FFD1DC 0%, #FFF5F8 100%)',
        'kitty-gradient-header': 'linear-gradient(135deg, #FF6B8A 0%, #FF4D73 100%)',
      },
      boxShadow: {
        'kitty': '0 4px 14px rgba(255, 107, 138, 0.25)',
        'kitty-sm': '0 2px 8px rgba(255, 107, 138, 0.15)',
      },
    },
  },
  plugins: [],
}
