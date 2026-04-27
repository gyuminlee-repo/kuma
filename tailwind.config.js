/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        container: "var(--radius-container)",
        control: "var(--radius-control)",
      },
      height: {
        header: "var(--header-h)",
        menubar: "var(--menubar-h)",
        statusbar: "var(--statusbar-h)",
        control: "var(--control-h)",
        "control-primary": "var(--control-h-primary)",
      },
      width: {
        sidebar: "var(--sidebar-w)",
      },
      fontSize: {
        title: "var(--text-title)",
        body: "var(--text-body)",
        caption: "var(--text-caption)",
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: "oklch(0.65 0.15 145)",
        warning: "oklch(0.72 0.15 75)",
        error: "oklch(0.55 0.20 25)",
        info: "oklch(0.60 0.12 250)",
      },
      transitionDuration: {
        fast: "var(--duration-fast)",
        base: "var(--duration-base)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
