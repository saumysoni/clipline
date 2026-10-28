// Builds the editor's timeline (React + Twick) into one script and one stylesheet, which js/editor.js loads and mounts
// (window.PitTimeline). `npm run build` writes them to ../static/editor-app/; they're committed, so the server needs
// no Node. Twick's own stylesheet is cleaned on the way: its @import of a dozen web fonts (Google Fonts, cdnfonts) is
// dropped (privacy policy: no third-party requests), and every rule is scoped to .pc-tl, the timeline's box, so its
// generic class names (.card, .btn, .input...) can't restyle the rest of Pit Crew.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import prefixer from "postcss-prefix-selector";
import fs from "node:fs";
import path from "node:path";

const dropImports = { postcssPlugin: "drop-font-imports", AtRule: { import: (rule) => rule.remove() } };

// LICENSES.txt beside the bundle: every npm package that ends up in it, with its licence (Twick's asks for its licence
// and notices to go with it; React and the rest are MIT and ask the same).
const licenses = {
  name: "licenses",
  generateBundle(_, bundle) {
    const names = new Set();
    for (const chunk of Object.values(bundle)) {
      for (const id of Object.keys(chunk.modules || {})) {
        const m = id.replace(/\\/g, "/").match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
        if (m) names.add(m[1]);
      }
    }
    const parts = [...names].sort().map((name) => {
      const dir = path.join("node_modules", name), pkg = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf8"));
      // Twick's npm packages don't carry their licence: licenses/twick-LICENSE.md is its LICENSE.md from GitHub
      const own = fs.readdirSync(dir).find((f) => /^(licen[cs]e|copying)/i.test(f));
      const file = own ? path.join(dir, own) : name.startsWith("@twick/") ? "licenses/twick-LICENSE.md" : null;
      return `${name} ${pkg.version} (${pkg.license || "see below"})\n${"=".repeat(72)}\n` +
             (file ? fs.readFileSync(file, "utf8").trim() : `Licence: ${pkg.license}`) + "\n";
    });
    this.emitFile({ type: "asset", fileName: "LICENSES.txt", source:
      "The editor's timeline (timeline.js, style.css) is built from these packages (editor-app/, `npm run build`).\n\n" +
      parts.join("\n\n") });
  },
};

export default defineConfig({
  plugins: [react(), licenses],
  resolve: { alias: { "@twick/live-player": new URL("./src/player-state.jsx", import.meta.url).pathname } },
  css: {
    postcss: {
      plugins: [dropImports, prefixer({
        prefix: ".pc-tl",
        transform: (prefix, selector, prefixed) =>
          selector === ":root" || selector === "html" || selector === "body" ? prefix : prefixed,
      })],
    },
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
    "import.meta.env.VITE_TWICK_ANALYTICS_ENABLED": JSON.stringify("false"),  // no analytics, ever (privacy policy)
  },
  build: {
    outDir: process.env.OUT_DIR || "../static/editor-app",
    emptyOutDir: true,
    cssCodeSplit: false, minify: process.env.NOMIN ? false : "esbuild",
    sourcemap: false,
    lib: { entry: "src/main.jsx", name: "PitTimeline", formats: ["iife"], fileName: () => "timeline.js" },
  },
});
