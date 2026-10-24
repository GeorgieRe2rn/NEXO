import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export function useDarkMode() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");
  useEffect(() => {
    const update = () => setDark(document.documentElement.dataset.theme === "dark");
    window.addEventListener("nexo-theme", update);
    return () => window.removeEventListener("nexo-theme", update);
  }, []);
  return dark;
}
export default function ThemeToggle() {
  const dark = useDarkMode();
  function toggle() {
    const theme = dark ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("nexo-theme", theme); } catch { /* Private browsing. */ }
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#F3F1EC" : "#10171D");
    window.dispatchEvent(new Event("nexo-theme"));
  }
  return <button type="button" onClick={toggle} aria-label={dark ? "Activar modo claro" : "Activar modo oscuro"} title={dark ? "Modo claro" : "Modo oscuro"} className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-lg border border-ink-950/15 text-paper hover:bg-ink-950/5">{dark ? <Sun size={18}/> : <Moon size={18}/>}</button>;
}
