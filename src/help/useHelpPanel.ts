import { useCallback, useEffect, useState } from "react";
import { OPEN_HELP_EVENT } from "./events";

function topicOf(event: Event): string | null {
  if (!(event instanceof CustomEvent)) return null;
  const detail: unknown = event.detail;
  if (typeof detail !== "object" || detail === null || !("topic" in detail)) return null;
  return typeof detail.topic === "string" ? detail.topic : null;
}

/** Help panel state shared by both tabs. Tab changes never touch it. */
export function useHelpPanel() {
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("kuro-index");

  useEffect(() => {
    const onOpen = (event: Event) => {
      const next = topicOf(event);
      if (next === null) return;
      setTopic(next);
      setOpen(true);
    };
    window.addEventListener(OPEN_HELP_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_HELP_EVENT, onOpen);
  }, []);

  const close = useCallback(() => setOpen(false), []);

  return { open, topic, setTopic, close };
}
