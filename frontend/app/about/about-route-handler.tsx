"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { openAboutModal } from "@/lib/about-modal";
import { getAuthToken } from "@/lib/auth";

export function AboutRouteHandler() {
  const router = useRouter();

  useEffect(() => {
    openAboutModal();
    router.replace(getAuthToken() ? "/dashboard" : "/");
  }, [router]);

  return null;
}
