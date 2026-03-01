'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { getAuthToken } from '@/lib/auth';

export function useAuthGuard() {
  const router = useRouter();

  useEffect(() => {
    const token = getAuthToken();
    if (token) return;

    router.replace('/signin');
  }, [router]);
}
