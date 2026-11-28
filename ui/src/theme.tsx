// Theme and display mode. Both are saved in this browser. Charts read the theme so they redraw on a switch.
import { createContext, useContext } from "react";

export type Theme = "light" | "dark";
export type Mode = "focus" | "advanced";
export const ThemeContext = createContext<Theme>("light");
export const ModeContext = createContext<Mode>("focus");
export const useTheme = () => useContext(ThemeContext);
export const useMode = () => useContext(ModeContext);

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function load(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
export function save(key: string, v: string) { try { localStorage.setItem(key, v); } catch { /* storage unavailable */ } }

export function initialTheme(): Theme {
  const saved = load("theme");
  if (saved === "light" || saved === "dark") return saved;
  if (saved === "terminal" || saved === "glass") return "dark"; // earlier theme names
  try { return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch { return "light"; }
}
