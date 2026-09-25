import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [
    react(),
    {
      name: "figma-capture",
      apply: "serve",
      transformIndexHtml(html) {
        return html.replace(
          "</head>",
          `<script>
        if (location.hash.includes('figmacapture=')) {
          const script = document.createElement('script');
          script.src = 'https://mcp.figma.com/mcp/html-to-design/capture.js';
          script.async = true;
          document.head.appendChild(script);
        }
      </script></head>`,
        );
      },
    },
  ],
  build: { outDir: "dist" },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
