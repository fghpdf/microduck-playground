import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
afterEach(cleanup);

// Node 26 exposes an unavailable storage getter; use isolated browser storage in tests.
const stored = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => {
      stored.set(key, String(value));
    },
    removeItem: (key: string) => {
      stored.delete(key);
    },
    clear: () => {
      stored.clear();
    },
    key: (index: number) => [...stored.keys()][index] ?? null,
    get length() {
      return stored.size;
    },
  },
});
