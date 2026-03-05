'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type InstallChoice = {
  outcome: 'accepted' | 'dismissed';
  platform: string;
};

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<InstallChoice>;
};

function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') return false;
  const navigatorAsStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone;
  return window.matchMedia('(display-mode: standalone)').matches || Boolean(navigatorAsStandalone);
}

type InstallAppButtonProps = {
  className?: string;
};

export function InstallAppButton({ className }: InstallAppButtonProps) {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [isInstalling, setIsInstalling] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    setInstalled(isStandaloneMode());

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
    };

    const onAppInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  if (installed || !deferredPrompt) {
    return null;
  }

  return (
    <Button
      type='button'
      size='sm'
      className={cn('whitespace-nowrap', className)}
      disabled={isInstalling}
      onClick={async () => {
        if (!deferredPrompt) return;
        setIsInstalling(true);
        try {
          await deferredPrompt.prompt();
          await deferredPrompt.userChoice;
        } finally {
          setDeferredPrompt(null);
          setIsInstalling(false);
        }
      }}
    >
      {isInstalling ? 'Installing...' : 'Install App'}
    </Button>
  );
}
