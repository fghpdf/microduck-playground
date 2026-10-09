import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { translations } from "./translations";
export type Locale = "zh" | "en" | "ja" | "ko";
const valid = (v: unknown): v is Locale =>
  ["zh", "en", "ja", "ko"].includes(String(v));
function initial(): Locale {
  try {
    const saved = window.localStorage.getItem("ducklab.locale");
    return valid(saved) ? saved : "zh";
  } catch {
    return "zh";
  }
}
const fallback = {
  locale: "zh" as Locale,
  setLocale: (_v: Locale) => {},
  t: (s: string) => s,
};
const Context = createContext(fallback);
export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLanguage] = useState<Locale>(initial);
  const setLocale = useCallback((next: Locale) => {
    if (!valid(next)) return;
    setLanguage(next);
    try {
      window.localStorage.setItem("ducklab.locale", next);
    } catch {
      /* Settings remain available in memory. */
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : locale;
  }, [locale]);
  const t = useCallback(
    (text: string) =>
      locale === "zh" ? text : (translations[locale][text] ?? text),
    [locale],
  );
  return (
    <Context.Provider value={{ locale, setLocale, t }}>
      {children}
    </Context.Provider>
  );
}
export function useI18n() {
  return useContext(Context);
}
