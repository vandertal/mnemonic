import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

/** index.html needs (1) an absolute og:image URL (link previews ignore relative ones) and
 *  (2) preload tags for the font files, whose hashed names are only known after the build. */
function htmlTweaks(siteUrl: string): Plugin {
  return {
    name: 'mnemonic-html-tweaks',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        const out = html.replaceAll('__SITE_URL__', siteUrl.replace(/\/$/, ''))
        if (!ctx.bundle) return out // dev server: fonts are served from node_modules, nothing to preload
        // Only the two subsets the UI really uses (uk + en); other scripts are fetched lazily by unicode-range.
        const fonts = Object.keys(ctx.bundle).filter((f) => /inter-(latin|cyrillic)-wght-normal.*\.woff2$/.test(f))
        const tags = fonts
          .map((f) => `    <link rel="preload" as="font" type="font/woff2" href="/${f}" crossorigin />\n`)
          .join('')
        return out.replace('</head>', `${tags}  </head>`)
      },
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react(), tailwindcss(), htmlTweaks(env.VITE_SITE_URL ?? '')],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  }
})
