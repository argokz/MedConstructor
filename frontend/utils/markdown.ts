import MarkdownIt from 'markdown-it'

const allowedLinkProtocols = new Set(['http:', 'https:', 'mailto:', 'tel:'])

function isSafeMarkdownLink(rawUrl: string): boolean {
  const trimmedUrl = rawUrl.trim()

  if (!trimmedUrl) {
    return false
  }

  if (/^[a-z][a-z\d+.-]*:/i.test(trimmedUrl)) {
    try {
      return allowedLinkProtocols.has(new URL(trimmedUrl).protocol)
    } catch {
      return false
    }
  }

  return true
}

const safeMarkdownRenderer = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: true,
  typographer: false,
})

safeMarkdownRenderer.validateLink = isSafeMarkdownLink

const defaultLinkOpenRule = safeMarkdownRenderer.renderer.rules.link_open

safeMarkdownRenderer.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer nofollow')

  if (defaultLinkOpenRule) {
    return defaultLinkOpenRule(tokens, idx, options, env, self)
  }

  return self.renderToken(tokens, idx, options)
}

export function renderSafeMarkdown(markdown: string | null | undefined): string {
  return safeMarkdownRenderer.render(markdown ?? '')
}

export function renderSafeInlineMarkdown(markdown: string | null | undefined): string {
  return safeMarkdownRenderer.renderInline(markdown ?? '')
}
