"use client";

import Markdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

// Stage 7a: the shared markdown renderer for glossary definitions (and summaries). Inherits the
// Stage 4.7 safety posture — react-markdown does NOT parse raw HTML (no rehype-raw), and image/embed
// elements are disallowed — and adds KaTeX (remark-math → rehype-katex) so $…$ / $$…$$ formulas in
// technical definitions render from the start. RTL-aware: an Arabic definition sets dir="rtl".

const DISALLOWED = ["img", "image", "script", "iframe", "style", "form", "input", "object", "embed"];
const RTL_LANGUAGES = new Set(["ar"]);

export function dirForLanguage(language?: string | null): "rtl" | "ltr" {
  return language && RTL_LANGUAGES.has(language) ? "rtl" : "ltr";
}

function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const safe = typeof href === "string" && /^(https?:|mailto:)/i.test(href.trim());
  if (!safe) {
    return <>{children}</>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

export function MarkdownView({
  content,
  testId,
  language,
}: {
  content: string;
  testId?: string;
  language?: string | null;
}) {
  return (
    <div data-testid={testId} dir={dirForLanguage(language)} style={styles.markdown}>
      <Markdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        disallowedElements={DISALLOWED}
        unwrapDisallowed
        components={{ a: SafeLink }}
      >
        {content}
      </Markdown>
    </div>
  );
}

const styles = {
  markdown: {
    color: "#111827",
    fontSize: 14,
    lineHeight: 1.55,
  },
} satisfies Record<string, React.CSSProperties>;
