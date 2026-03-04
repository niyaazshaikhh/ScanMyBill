'use client';

import { X } from 'lucide-react';

import { Button, type ButtonProps } from '@/components/ui/button';

type PopupWindowProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: ButtonProps['variant'];
  loading?: boolean;
  onConfirm: () => void;
  onCancel?: () => void;
};

export function PopupWindow({
  open,
  title,
  message,
  confirmLabel = 'OK',
  cancelLabel,
  confirmVariant = 'default',
  loading = false,
  onConfirm,
  onCancel,
}: PopupWindowProps) {
  if (!open) return null;

  const canCancel = Boolean(cancelLabel && onCancel);
  const closeAction = onCancel || onConfirm;

  return (
    <div
      className='fixed inset-0 z-[80] grid place-items-center bg-black/40 px-4 py-6'
      onClick={closeAction}
      role='presentation'
    >
      <div
        className='w-full max-w-sm rounded-lg border border-border bg-background shadow-xl'
        onClick={(event) => event.stopPropagation()}
        role='dialog'
        aria-modal='true'
        aria-label={title}
      >
        <div className='flex items-start justify-between border-b border-border px-4 py-3'>
          <p className='font-semibold'>{title}</p>
          <button
            type='button'
            onClick={closeAction}
            className='rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground'
            aria-label='Close popup'
            disabled={loading}
          >
            <X className='h-4 w-4' />
          </button>
        </div>
        <div className='space-y-4 px-4 py-3'>
          <p className='text-sm text-muted-foreground'>{message}</p>
          <div className='flex justify-end gap-2'>
            {canCancel ? (
              <Button type='button' variant='outline' onClick={onCancel} disabled={loading}>
                {cancelLabel}
              </Button>
            ) : null}
            <Button type='button' variant={confirmVariant} onClick={onConfirm} disabled={loading}>
              {loading ? 'Please wait...' : confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
