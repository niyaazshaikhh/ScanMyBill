"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { appendDashboardDebugRecord } from "@/lib/debugging";

type DashboardErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function DashboardError({ error, reset }: DashboardErrorProps) {
  useEffect(() => {
    appendDashboardDebugRecord({
      level: "error",
      source: "dashboard_boundary",
      title: "Dashboard rendering failed",
      message: error.message || "Unexpected dashboard error",
      details: {
        name: error.name,
        digest: error.digest ?? null,
        stack: error.stack ?? null,
      },
    });
  }, [error]);

  return (
    <div className="space-y-3 rounded-md border border-red-200 bg-red-50/80 p-4 dark:border-red-500/40 dark:bg-red-500/15">
      <h2 className="text-lg font-semibold text-red-800 dark:text-red-200">Dashboard encountered an error</h2>
      <p className="text-sm text-red-700 dark:text-red-200">
        The issue has been logged to Debug Console. You can retry safely.
      </p>
      <Button type="button" variant="outline" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
