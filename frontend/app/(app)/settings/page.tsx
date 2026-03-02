"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";

export const dynamic = "force-dynamic";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";

type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "user";
  created_at: string;
};

export default function SettingsPage() {
  useAuthGuard();

  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    apiRequest<CurrentUser>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  return (
    <div className="space-y-5">
      <h2 className="font-[var(--font-space)] text-2xl font-semibold">
        Settings
      </h2>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Account and Access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="font-medium">Name:</span> {user?.full_name || "-"}
          </p>
          <p>
            <span className="font-medium">Email:</span> {user?.email || "-"}
          </p>
          <p>
            <span className="font-medium">Role:</span>{" "}
            <Badge variant="secondary">{user?.role || "user"}</Badge>
          </p>
        </CardContent>
      </Card>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Business Setup</CardTitle>
        </CardHeader>
        <CardContent>
          <Link
            href="/settings/personal_details"
            className="flex items-center justify-between rounded-md border border-border bg-background px-4 py-3 transition hover:bg-muted"
          >
            <div>
              <p className="text-sm font-medium">Personal Details</p>
              <p className="text-xs text-muted-foreground">
                Add Company Name and GST/IN to improve bill type identification.
              </p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
