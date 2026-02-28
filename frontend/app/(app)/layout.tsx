import { AdminShell } from '@/components/layout/admin-shell';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}