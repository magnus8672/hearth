import { useCallback, useLayoutEffect, useRef, useState } from 'react';

/** Follow from the pre-update scroll position, including delayed images and resizing. */
export function useTranscript(conversation: string, revision: unknown) {
  const transcript = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const followLatest = useCallback(() => {
    following.current = true; setAtBottom(true);
    const element = transcript.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, []);
  useLayoutEffect(() => { followLatest(); }, [conversation, followLatest]);
  useLayoutEffect(() => {
    const element = transcript.current;
    if (!element) return;
    let contentHeight = element.scrollHeight, viewportHeight = element.clientHeight;
    const update = () => {
      element.style.setProperty('--transcript-height', `${element.clientHeight}px`);
      if (following.current) element.scrollTop = element.scrollHeight;
      contentHeight = element.scrollHeight; viewportHeight = element.clientHeight;
      setAtBottom(contentHeight - element.scrollTop - viewportHeight < 60);
    };
    // Inspecting a receipt or thinking trace is intentional scrollback. Pause before
    // the disclosure changes height so the observer cannot pull its heading away.
    const inspect = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest('summary')) {
        following.current = false;
        requestAnimationFrame(() => setAtBottom(element.scrollHeight - element.scrollTop - element.clientHeight < 60));
      }
    };
    const scroll = () => {
      // Reflow can clamp scrollTop before ResizeObserver runs. That is not the
      // reader scrolling away from the bottom (for example after hiding a pane).
      if (contentHeight !== element.scrollHeight || viewportHeight !== element.clientHeight) { update(); return; }
      following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 60;
      setAtBottom(following.current);
    };
    update();
    element.addEventListener('scroll', scroll);
    element.addEventListener('click', inspect, true);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    return () => { observer.disconnect(); element.removeEventListener('scroll', scroll); element.removeEventListener('click', inspect, true); };
  }, [conversation, revision]);
  return { transcript, atBottom, followLatest };
}
