'use client';

import { useEffect, useRef, useState } from 'react';

const ROOT_CURSOR_CLASS = 'custom-cursor-enabled';
type CursorMode = 'default' | 'text' | 'pointer' | 'not-allowed' | 'grab' | 'grabbing' | 'move';

const TEXT_INPUT_TYPES = new Set(['text', 'search', 'email', 'url', 'tel', 'password', 'number']);

function isEditableInput(element: Element): boolean {
  if (element instanceof HTMLTextAreaElement) {
    return !element.disabled && !element.readOnly;
  }

  if (element instanceof HTMLInputElement) {
    const inputType = (element.type || 'text').toLowerCase();
    return TEXT_INPUT_TYPES.has(inputType) && !element.disabled && !element.readOnly;
  }

  if (element instanceof HTMLElement && element.isContentEditable) {
    return true;
  }

  return false;
}

function resolveClassCursorMode(target: Element, isMouseDown: boolean): CursorMode | null {
  let current: Element | null = target;
  while (current) {
    if (current instanceof HTMLElement) {
      const classes = current.classList;
      if (classes.contains('cursor-not-allowed')) return 'not-allowed';
      if (classes.contains('cursor-grabbing')) return 'grabbing';
      if (classes.contains('cursor-grab')) return isMouseDown ? 'grabbing' : 'grab';
      if (classes.contains('cursor-pointer')) return 'pointer';
      if (classes.contains('cursor-text')) return 'text';
      if (classes.contains('cursor-move') || classes.contains('cursor-all-scroll')) return 'move';
    }
    current = current.parentElement;
  }
  return null;
}

function resolveCursorMode(target: EventTarget | null, isMouseDown: boolean): CursorMode {
  if (!(target instanceof Element)) {
    return 'default';
  }

  const classMode = resolveClassCursorMode(target, isMouseDown);
  if (classMode) {
    return classMode;
  }

  if (target.closest('[disabled], [aria-disabled="true"]')) {
    return 'not-allowed';
  }

  const editableCandidate = target.closest('textarea, input, [contenteditable], [contenteditable="true"]');
  if (editableCandidate && isEditableInput(editableCandidate)) {
    return 'text';
  }

  if (target.closest('[draggable="true"], [data-draggable="true"], [data-rbd-drag-handle-draggable-id], [role="slider"]')) {
    return isMouseDown ? 'grabbing' : 'grab';
  }

  if (target.closest('a[href], button, [role="button"], [role="link"], summary, label[for], input[type="button"], input[type="submit"], input[type="reset"], input[type="checkbox"], input[type="radio"], select, option')) {
    return 'pointer';
  }

  return 'default';
}

function CursorIcon({ mode }: { mode: CursorMode }) {
  if (mode === 'text') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M6 2h4v2H8v16h2v2H6v-2h2V4H6zM14 2h4v2h-2v16h2v2h-4v-2h2V4h-2zM10 11h4v2h-4z' fill='currentColor' />
      </svg>
    );
  }

  if (mode === 'pointer') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M8 2a1 1 0 00-1 1v7H6V6a1 1 0 00-2 0v8.2a2.2 2.2 0 00.77 1.67l5.26 4.52A2.2 2.2 0 0011.47 21H15a2 2 0 002-2V9a1 1 0 10-2 0v2h-1V7a1 1 0 10-2 0v4h-1V5a1 1 0 00-1-1 1 1 0 00-1 1v6H8V3a1 1 0 00-1-1z' fill='currentColor' />
      </svg>
    );
  }

  if (mode === 'not-allowed') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M12 2a10 10 0 100 20 10 10 0 000-20zm6.1 13.45L8.55 5.9a8 8 0 019.55 9.55zM5.9 8.55l9.55 9.55A8 8 0 015.9 8.55z' fill='currentColor' />
      </svg>
    );
  }

  if (mode === 'grab') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M8 2a1 1 0 00-1 1v5H6V5a1 1 0 10-2 0v8.2a3 3 0 001.05 2.28l3.7 3.18A3 3 0 0010.7 20H14a3 3 0 003-3V8a1 1 0 10-2 0v3h-1V6a1 1 0 10-2 0v5h-1V5a1 1 0 10-2 0v6H8V3a1 1 0 00-1-1z' fill='currentColor' />
      </svg>
    );
  }

  if (mode === 'grabbing') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M6 8a2 2 0 012-2h1V4a1 1 0 112 0v2h1V3a1 1 0 112 0v3h1V4a1 1 0 112 0v2h1a2 2 0 012 2v6a6 6 0 01-6 6h-2a6 6 0 01-4.8-2.4L4.4 12.4A2 2 0 016 9.2V8z' fill='currentColor' />
      </svg>
    );
  }

  if (mode === 'move') {
    return (
      <svg viewBox='0 0 24 24' className='h-full w-full'>
        <path d='M11 2h2v4h3l-4 4-4-4h3zM18 11h4v2h-4v3l-4-4 4-4zM11 18v4h2v-4h3l-4-4-4 4zM2 11h4V8l4 4-4 4v-3H2z' fill='currentColor' />
      </svg>
    );
  }

  return (
    <svg viewBox='0 0 24 24' className='h-full w-full'>
      <path d='M2 2v20l6.8-6.2 3.1 7L15 21l-3.2-7H22z' fill='currentColor' />
    </svg>
  );
}

export function CustomCursor() {
  const cursorRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const pointRef = useRef({ x: -100, y: -100 });
  const isMouseDownRef = useRef(false);
  const [isVisible, setIsVisible] = useState(false);
  const [mode, setMode] = useState<CursorMode>('default');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQuery = window.matchMedia('(hover: hover) and (pointer: fine)');
    if (!mediaQuery.matches) return;

    document.documentElement.classList.add(ROOT_CURSOR_CLASS);

    const applyPosition = () => {
      frameRef.current = null;
      const cursor = cursorRef.current;
      if (!cursor) return;

      cursor.style.transform = `translate3d(${pointRef.current.x}px, ${pointRef.current.y}px, 0)`;
    };

    const schedulePosition = () => {
      if (frameRef.current !== null) return;
      frameRef.current = window.requestAnimationFrame(applyPosition);
    };

    const onMouseMove = (event: MouseEvent) => {
      pointRef.current = { x: event.clientX + 1, y: event.clientY + 1 };
      setIsVisible(true);
      setMode(resolveCursorMode(event.target, isMouseDownRef.current));
      schedulePosition();
    };

    const onMouseLeave = () => {
      setIsVisible(false);
    };

    const onDocumentMouseOut = (event: MouseEvent) => {
      if (event.relatedTarget === null) {
        setIsVisible(false);
      }
    };

    const onPointerLeave = () => {
      setIsVisible(false);
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        setIsVisible(false);
      }
    };

    const onMouseDown = (event: MouseEvent) => {
      isMouseDownRef.current = true;
      setMode(resolveCursorMode(event.target, true));
    };

    const onMouseUp = (event: MouseEvent) => {
      isMouseDownRef.current = false;
      setMode(resolveCursorMode(event.target, false));
    };

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    window.addEventListener('mouseleave', onMouseLeave);
    window.addEventListener('blur', onMouseLeave);
    window.addEventListener('pointerleave', onPointerLeave);
    window.addEventListener('mousedown', onMouseDown, { passive: true });
    window.addEventListener('mouseup', onMouseUp, { passive: true });
    document.addEventListener('mouseout', onDocumentMouseOut);
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseleave', onMouseLeave);
      window.removeEventListener('blur', onMouseLeave);
      window.removeEventListener('pointerleave', onPointerLeave);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('mouseout', onDocumentMouseOut);
      document.removeEventListener('visibilitychange', onVisibilityChange);

      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
      }

      document.documentElement.classList.remove(ROOT_CURSOR_CLASS);
    };
  }, []);

  return (
    <div
      ref={cursorRef}
      className={`custom-cursor custom-cursor-${mode} ${isVisible ? 'custom-cursor-visible' : ''}`}
      aria-hidden='true'
    >
      <CursorIcon mode={mode} />
    </div>
  );
}
