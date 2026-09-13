/**
 * PHINOX Tailwind build config — Phase 6 production build.
 *
 * Consumed by ``npm run build:css`` (see package.json) to compile
 * static/css/input.css → static/css/dist.css (minified, production-ready).
 *
 * Tokens: Phase 1's base.html inline config + Phase 2/3/5 additions are
 * transcribed here verbatim. The compiled dist.css replaces the CDN
 * <script> tag in production (templates/base.html uses a hybrid approach:
 * CDN in dev, dist.css in prod via {% if not DEBUG %}).
 *
 * Per دستور §9: zero border-radius is enforced (borderRadius block below).
 */
module.exports = {
  darkMode: "class",
  // Scan every .html template — Phase 1-5 ported Stitch designs across
  // templates/, apps/*/templates/, and the core/components/.
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // ── PHINOX project tokens (existing — from Phase 1 base.html) ──
        "phx-surface":          "#121414",
        "phx-surface-dim":      "#0d0e0f",
        "phx-surface-low":      "#1a1c1c",
        "phx-surface-mid":      "#1e2020",
        "phx-surface-high":     "#292a2a",
        "phx-surface-highest":  "#343535",
        "phx-fire":             "#E85D04",
        "phx-fire-dim":         "#b34800",
        "phx-text":             "#e3e2e2",
        "phx-text-dim":         "#8e9192",
        "phx-text-muted":       "#c4c7c7",
        "phx-border":           "#343535",
        "phx-border-bright":    "#444748",

        // ── Stitch brand-* tokens (Phase 4 integration) ──────────────
        "brand-bg":             "#0a0a0a",
        "brand-pitch":          "#000000",
        "brand-black":          "#0a0a0a",
        "brand-surface":        "#121414",
        "brand-panel":          "#1a1c1c",
        "brand-card":           "#181818",
        "brand-subtle":         "#1a1a1a",
        "brand-dim":            "#0d0e0f",
        "brand-light":          "#e3e2e2",
        "brand-text":           "#e3e2e2",
        "brand-subtext":        "#8e9192",
        "brand-muted":          "#c4c7c7",
        "brand-border":         "#2a2a2a",
        "brand-orange":         "#E85D04",
        "brand-orangeHover":    "#FF6A1A",
        "brand-green":          "#4ade80",

        // ── Stitch Material Design 3 surface tokens ──────────────────
        "surface":              "#121414",
        "surface-dim":          "#121414",
        "surface-bright":       "#38393a",
        "surface-variant":      "#343535",
        "surface-container-lowest": "#0d0e0f",
        "surface-container-low":  "#1a1c1c",
        "surface-container":     "#1e2020",
        "surface-container-high":"#292a2a",
        "surface-container-highest": "#343535",
        "surface-tint":          "#c8c6c5",
        "background":           "#121414",
        "on-background":         "#e3e2e2",
        "on-surface":            "#e3e2e2",
        "on-surface-variant":    "#c4c7c7",
        "inverse-surface":       "#e3e2e2",
        "inverse-on-surface":    "#2f3131",
        "outline":               "#8e9192",
        "outline-variant":       "#444748",

        // ── Stitch Material Design 3 primary / secondary / tertiary ──
        "primary":               "#E85D04",
        "on-primary":            "#0a0a0a",
        "primary-container":     "#0f0f0f",
        "on-primary-container":  "#e3e2e2",
        "primary-fixed":         "#ffdbcd",
        "primary-fixed-dim":     "#ffb596",
        "on-primary-fixed":      "#360f00",
        "on-primary-fixed-variant":"#7c2e00",
        "inverse-primary":       "#5f5e5e",
        "secondary":             "#c6c6c7",
        "on-secondary":          "#2f3131",
        "secondary-container":   "#454747",
        "on-secondary-container":"#b4b5b5",
        "secondary-fixed":       "#e2e2e2",
        "secondary-fixed-dim":  "#c6c6c7",
        "on-secondary-fixed":    "#1a1c1c",
        "on-secondary-fixed-variant":"#454747",
        "tertiary":              "#ffb596",
        "on-tertiary":           "#581e00",
        "tertiary-container":   "#210700",
        "on-tertiary-container": "#d35300",
        "tertiary-fixed":        "#d5e3ff",
        "tertiary-fixed-dim":    "#a6c8ff",
        "on-tertiary-fixed":     "#001c3b",
        "on-tertiary-fixed-variant":"#004787",
        "error":                 "#ffb4ab",
        "on-error":              "#690005",
        "error-container":       "#93000a",
        "on-error-container":    "#ffdad6",

        // Legacy alias kept from original tailwind.config.js
        "fire-orange": "#E85D04",
      },
      fontFamily: {
        "display": ["\"Archivo Narrow\"", "sans-serif"],
        "mono":    ["\"JetBrains Mono\"", "monospace"],
        "body":    ["\"Hanken Grotesk\"", "sans-serif"],
        // Stitch Material Design 3 font-family aliases:
        "display-xl":         ["\"Hanken Grotesk\"", "sans-serif"],
        "headline-lg":         ["\"Hanken Grotesk\"", "sans-serif"],
        "headline-lg-mobile":  ["\"Hanken Grotesk\"", "sans-serif"],
        "body-md":             ["\"Hanken Grotesk\"", "sans-serif"],
        "label-sm":            ["\"JetBrains Mono\"", "monospace"],
        "label-xs":             ["\"JetBrains Mono\"", "monospace"],
        "label-technical":     ["\"JetBrains Mono\"", "monospace"],
        "technical-sm":        ["\"JetBrains Mono\"", "monospace"],
        "headline":            ["\"Archivo Narrow\"", "sans-serif"],
        // Original Phase 1 font aliases (kept for back-compat with old templates):
        "button-text": ["\"Archivo Narrow\""],
        "body-base": ["\"JetBrains Mono\""],
        "headline-md": ["\"Archivo Narrow\""],
        "headline-md-mobile": ["\"Archivo Narrow\""],
      },
      fontSize: {
        // Stitch Material Design 3 type-scale aliases:
        "display-xl":         ["80px", {"lineHeight": "1.0", "letterSpacing": "-0.04em", "fontWeight": "800"}],
        "headline-lg":        ["48px", {"lineHeight": "1.1", "letterSpacing": "-0.02em", "fontWeight": "700"}],
        "headline-lg-mobile": ["32px", {"lineHeight": "1.2", "fontWeight": "700"}],
        "body-md":            ["16px", {"lineHeight": "1.6", "letterSpacing": "0.01em", "fontWeight": "400"}],
        "label-technical":    ["12px", {"lineHeight": "1.4", "letterSpacing": "0.08em", "fontWeight": "500"}],
        "label-sm":           ["10px", {"lineHeight": "1.2", "fontWeight": "400"}],
        "label-xs":           ["10px", {"lineHeight": "1.2", "letterSpacing": "0.25em", "fontWeight": "700"}],
        "technical-sm":       ["12px", {"lineHeight": "1.4", "letterSpacing": "0.20em", "fontWeight": "500"}],
      },
      spacing: {
        "unit":           "4px",
        "gutter":         "24px",
        "margin-mobile":  "16px",
        "margin-desktop": "64px",
        "section-gap":    "128px",
        "container-max":  "1440px",
        "touch-target-min": "48px",
      },
      // BRAND LAW: zero border-radius on everything (AGENTS.md §0.6)
      borderRadius: {
        "DEFAULT": "0px",
        "none":    "0px",
        "sm":      "0px",
        "md":      "0px",
        "lg":      "0px",
        "xl":      "0px",
        "2xl":     "0px",
        "3xl":     "0px",
        "full":    "9999px", // pills for badges only
      },
      letterSpacing: {
        "wide-xl": "0.15em",
        "wide-2xl": "0.20em",
        "wide-3xl": "0.25em",
        "widest":   "0.25em",
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/container-queries"),
  ],
};
