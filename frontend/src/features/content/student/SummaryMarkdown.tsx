"use client";

import Markdown from "react-markdown";

// Stage 4.7 S1 (ADR-4.7-4): AI summary content is treated as UNTRUSTED markup even though it is ours.
// react-markdown does NOT parse raw HTML unless `rehype-raw` is added — we deliberately do NOT add it,
// so any embedded HTML (e.g. <script>) is inert text, never executed. We additionally disallow image
// and embed elements (no remote image fetches) and gate link protocols to http(s)/mailto.

const DISALLOWED = ["img", "image", "script", "iframe", "style", "form", "input", "object", "embed"];

function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const safe = typeof href === "string" && /^(https?:|mailto:)/i.test(href.trim());
  if (!safe) {
    return <>{children}</>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">
      {children}
    </a>
  );
}

export function SummaryMarkdown({ content, testId }: { content: string; testId?: string }) {
  return (
    <div data-testid={testId} className="text-lg leading-[1.65] text-text">
      <Markdown
        disallowedElements={DISALLOWED}
        unwrapDisallowed
        components={{ a: SafeLink }}
      >
        {content}
      </Markdown>
    </div>
  );
}
