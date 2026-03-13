'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';

type VerticalScrollNumberProps = {
  value: string | number;
  className?: string;
  durationMs?: number;
  staggerMs?: number;
};

type Direction = 'up' | 'down';

type StaticToken = {
  kind: 'static';
  key: string;
  char: string;
};

type DigitToken = {
  kind: 'digit';
  key: string;
  from: string;
  to: string;
  changed: boolean;
};

type Token = StaticToken | DigitToken;

function toDisplayValue(value: string | number): string {
  return typeof value === 'number' ? String(value) : value;
}

function toNumericValue(value: string): number {
  const cleaned = value.replace(/[^0-9.-]/g, '');
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isDigit(char: string): boolean {
  return /^[0-9]$/.test(char);
}

function buildTokens(previousValue: string, currentValue: string): Token[] {
  const previousDigits = previousValue.replace(/\D/g, '');
  const currentDigits = currentValue.replace(/\D/g, '');

  const maxDigits = Math.max(previousDigits.length, currentDigits.length);
  const paddedPreviousDigits = previousDigits.padStart(maxDigits, ' ');
  const paddedCurrentDigits = currentDigits.padStart(maxDigits, ' ');
  const currentOffset = maxDigits - currentDigits.length;

  let currentDigitIndex = 0;
  const tokens: Token[] = [];

  for (let index = 0; index < currentValue.length; index += 1) {
    const char = currentValue[index];
    if (!isDigit(char)) {
      tokens.push({
        kind: 'static',
        key: `static-${index}-${char}`,
        char,
      });
      continue;
    }

    const alignedDigitIndex = currentOffset + currentDigitIndex;
    const previousDigit = paddedPreviousDigits[alignedDigitIndex] || ' ';
    const currentDigit = paddedCurrentDigits[alignedDigitIndex] || char;
    const from = previousDigit === ' ' ? '0' : previousDigit;

    tokens.push({
      kind: 'digit',
      key: `digit-${index}-${alignedDigitIndex}-${from}-${currentDigit}`,
      from,
      to: currentDigit,
      changed: from !== currentDigit,
    });

    currentDigitIndex += 1;
  }

  return tokens;
}

function AnimatedDigit({
  from,
  to,
  direction,
  animate,
  durationMs,
  delayMs,
}: {
  from: string;
  to: string;
  direction: Direction;
  animate: boolean;
  durationMs: number;
  delayMs: number;
}) {
  const isUp = direction === 'up';
  const frames = isUp ? [from, to] : [to, from];
  const transform = isUp
    ? animate
      ? 'translate3d(0,-50%,0)'
      : 'translate3d(0,0%,0)'
    : animate
      ? 'translate3d(0,0%,0)'
      : 'translate3d(0,-50%,0)';

  return (
    <span className='relative inline-flex h-[1.35em] w-[0.68em] overflow-hidden align-middle [backface-visibility:hidden]'>
      <span
        className='flex flex-col will-change-transform'
        style={{
          transform,
          transitionProperty: 'transform',
          transitionDuration: `${durationMs}ms`,
          transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
          transitionDelay: `${delayMs}ms`,
        }}
      >
        <span className='block h-[1.35em] leading-[1.35em]'>{frames[0]}</span>
        <span className='block h-[1.35em] leading-[1.35em]'>{frames[1]}</span>
      </span>
    </span>
  );
}

export function VerticalScrollNumber({
  value,
  className,
  durationMs = 900,
  staggerMs = 24,
}: VerticalScrollNumberProps) {
  const nextValue = toDisplayValue(value);
  const [currentValue, setCurrentValue] = useState(nextValue);
  const [previousValue, setPreviousValue] = useState<string | null>(null);
  const [direction, setDirection] = useState<Direction>('up');
  const [animate, setAnimate] = useState(false);

  const timeoutRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
      if (rafRef.current) {
        window.cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (nextValue === currentValue) return;

    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    if (rafRef.current) {
      window.cancelAnimationFrame(rafRef.current);
    }

    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) {
      setPreviousValue(null);
      setCurrentValue(nextValue);
      setAnimate(false);
      return;
    }

    const previousNumeric = toNumericValue(currentValue);
    const nextNumeric = toNumericValue(nextValue);
    setDirection(nextNumeric >= previousNumeric ? 'up' : 'down');

    setPreviousValue(currentValue);
    setCurrentValue(nextValue);
    setAnimate(false);

    rafRef.current = window.requestAnimationFrame(() => {
      setAnimate(true);
    });

    timeoutRef.current = window.setTimeout(() => {
      setPreviousValue(null);
      setAnimate(false);
    }, durationMs);
  }, [currentValue, durationMs, nextValue]);

  const tokens = useMemo(() => {
    if (!previousValue) return null;
    return buildTokens(previousValue, currentValue);
  }, [currentValue, previousValue]);

  return (
    <span
      className={cn(
        'relative inline-flex h-[1.35em] items-center overflow-hidden align-middle tabular-nums',
        className,
      )}
    >
      {tokens === null
        ? currentValue
        : (() => {
            const totalDigits = tokens.reduce((count, token) => {
              return token.kind === 'digit' ? count + 1 : count;
            }, 0);
            let digitIndex = 0;

            return tokens.map((token) => {
              if (token.kind === 'static') {
                return (
                  <span key={token.key} className='block h-[1.35em] leading-[1.35em]'>
                    {token.char}
                  </span>
                );
              }

              const delayMs = Math.max(0, (totalDigits - digitIndex - 1) * staggerMs);
              digitIndex += 1;

              if (!token.changed) {
                return (
                  <span key={token.key} className='inline-flex h-[1.35em] w-[0.68em] leading-[1.35em]'>
                    {token.to}
                  </span>
                );
              }

              return (
                <AnimatedDigit
                  key={token.key}
                  from={token.from}
                  to={token.to}
                  direction={direction}
                  animate={animate}
                  durationMs={durationMs}
                  delayMs={delayMs}
                />
              );
            });
          })()}
    </span>
  );
}
