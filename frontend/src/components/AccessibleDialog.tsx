"use client";

import { useEffect, useRef, type ComponentPropsWithoutRef, type KeyboardEvent } from "react";

export default function AccessibleDialog({ children, onClose, ...props }: ComponentPropsWithoutRef<"section"> & { onClose: () => void }) {
  const dialog = useRef<HTMLElement>(null);
  const controls = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>("a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex='0']") ?? []).filter((element) => element.getClientRects().length > 0);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = dialog.current?.querySelector<HTMLElement>("button:not([disabled]),[href],input:not([disabled])");
    (first ?? dialog.current)?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  const keyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
    if (event.key !== "Tab") return;
    const items = controls();
    const first = items[0]; const last = items.at(-1);
    if (!first) { event.preventDefault(); dialog.current?.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first.focus(); }
    event.stopPropagation();
  };
  return <section {...props} ref={dialog} role="dialog" aria-modal="true" tabIndex={-1} onKeyDown={keyDown}>{children}</section>;
}
