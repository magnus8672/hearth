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
    const update = () => { if (following.current) element.scrollTop = element.scrollHeight; };
    const scroll = () => {
      following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 60;
      setAtBottom(following.current);
    };
    update();
    element.addEventListener('scroll', scroll);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    return () => { observer.disconnect(); element.removeEventListener('scroll', scroll); };
  }, [conversation, revision]);
  return { transcript, atBottom, followLatest };
}
