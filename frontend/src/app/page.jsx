'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getUser } from '@/lib/auth';

export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    if (getUser()) router.replace('/dashboard');
    else router.replace('/login');
  }, [router]);
  return null;
}
