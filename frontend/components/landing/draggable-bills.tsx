'use client';

import { type CSSProperties, useEffect, useRef, useState } from 'react';

type BillCard = {
  id: number;
  title: string;
  amount: string;
  insight: string;
  aiScore: string;
  left: number;
  top: number;
  rotate: number;
  color: string;
};

const initialCards: BillCard[] = [
  {
    id: 1,
    title: 'Shree Ganesh Tools',
    amount: 'Rs 12,460',
    insight: 'GST fields matched',
    aiScore: 'AI 98%',
    left: 12,
    top: 12,
    rotate: -8,
    color: 'bg-gradient-to-br from-amber-50 to-amber-100'
  },
  {
    id: 2,
    title: 'City Medico',
    amount: 'Rs 5,140',
    insight: 'Vendor auto-detected',
    aiScore: 'AI 96%',
    left: 44,
    top: 30,
    rotate: 6,
    color: 'bg-gradient-to-br from-lime-50 to-lime-100'
  },
  {
    id: 3,
    title: 'Apex Supplies',
    amount: 'Rs 8,920',
    insight: 'Tax split suggested',
    aiScore: 'AI 97%',
    left: 22,
    top: 56,
    rotate: -3,
    color: 'bg-gradient-to-br from-sky-50 to-sky-100'
  }
];

export function DraggableBills() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [cards, setCards] = useState(initialCards);
  const [activeId, setActiveId] = useState<number | null>(null);
  const pointerRafRef = useRef<number | null>(null);
  const pendingPointerRef = useRef<{ id: number; clientX: number; clientY: number } | null>(null);

  const updatePosition = (id: number, clientX: number, clientY: number) => {
    const box = containerRef.current?.getBoundingClientRect();
    if (!box) return;

    const leftPercent = ((clientX - box.left) / box.width) * 100;
    const topPercent = ((clientY - box.top) / box.height) * 100;

    setCards((prev) =>
      prev.map((card) =>
        card.id === id
          ? {
              ...card,
              left: Math.max(4, Math.min(78, leftPercent)),
              top: Math.max(8, Math.min(72, topPercent))
            }
          : card
      )
    );
  };

  const queuePositionUpdate = (id: number, clientX: number, clientY: number) => {
    pendingPointerRef.current = { id, clientX, clientY };
    if (pointerRafRef.current !== null) return;

    pointerRafRef.current = window.requestAnimationFrame(() => {
      pointerRafRef.current = null;
      const pending = pendingPointerRef.current;
      if (!pending) return;
      updatePosition(pending.id, pending.clientX, pending.clientY);
      pendingPointerRef.current = null;
    });
  };

  useEffect(() => {
    return () => {
      if (pointerRafRef.current !== null) {
        window.cancelAnimationFrame(pointerRafRef.current);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className='hero-grid relative h-[320px] w-full overflow-hidden rounded-3xl border border-amber-200 bg-white/70 p-4 shadow-lg backdrop-blur sm:h-[380px]'
    >
      <div className='pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-sky-200/40 blur-2xl' />
      <div className='pointer-events-none absolute -bottom-14 -left-10 h-40 w-40 rounded-full bg-orange-200/45 blur-2xl' />

      <div className='pointer-events-none absolute inset-x-4 top-4 z-10 flex items-center justify-between text-[11px] font-semibold'>
        <span className='inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-emerald-700'>
          <span className='h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-600' />
          AI Engine Live
        </span>
        <span className='rounded-full border border-orange-300 bg-orange-50 px-2.5 py-1 text-orange-700'>
          Made for Indian MSMEs
        </span>
      </div>

      {cards.map((card) => (
        <div
          key={card.id}
          role='button'
          tabIndex={0}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            setActiveId(card.id);
          }}
          onPointerMove={(event) => {
            if (activeId === card.id) {
              queuePositionUpdate(card.id, event.clientX, event.clientY);
            }
          }}
          onPointerUp={(event) => {
            event.currentTarget.releasePointerCapture(event.pointerId);
            setActiveId(null);
          }}
          onPointerCancel={(event) => {
            event.currentTarget.releasePointerCapture(event.pointerId);
            setActiveId(null);
          }}
          style={{
            left: `${card.left}%`,
            top: `${card.top}%`
          }}
          className='absolute w-48 -translate-x-1/2 -translate-y-1/2 touch-none select-none transition-[left,top] duration-150 ease-out'
        >
          <div
            style={
              {
                '--bill-rotate': `${card.rotate}deg`,
                '--bill-float-delay': `${card.id * 0.35}s`,
                '--bill-float-duration': `${6.5 + card.id * 0.9}s`,
              } as CSSProperties
            }
            className={`invoice-float w-full cursor-grab rounded-xl border border-stone-300 ${card.color} p-4 shadow-md active:cursor-grabbing ${
              activeId === card.id ? 'invoice-float-dragging' : ''
            }`}
          >
            <p className='text-xs font-medium text-stone-600'>AI Processed Bill</p>
            <h4 className='mt-1 text-sm font-semibold text-stone-800'>{card.title}</h4>
            <p className='mt-2 text-lg font-bold text-stone-900'>{card.amount}</p>
            <div className='mt-2 flex items-center justify-between gap-2 text-[11px] text-stone-600'>
              <span>{card.insight}</span>
              <span className='rounded-full bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-700'>
                {card.aiScore}
              </span>
            </div>
            <p className='mt-1 text-xs text-stone-500'>Drag to organize MSME workflow</p>
          </div>
        </div>
      ))}
    </div>
  );
}
