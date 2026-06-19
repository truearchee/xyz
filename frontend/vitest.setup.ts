import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount React trees between tests (RTL does not auto-clean under vitest).
afterEach(() => cleanup());

// jsdom lacks these; React Aria (Modal) touches them. Minimal stubs.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

if (!("ResizeObserver" in window)) {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}
