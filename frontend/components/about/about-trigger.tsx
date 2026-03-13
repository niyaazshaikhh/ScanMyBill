"use client";

import { Button, type ButtonProps } from "@/components/ui/button";
import { openAboutModal } from "@/lib/about-modal";
import { cn } from "@/lib/utils";

type AboutTriggerProps = {
  label: string;
  className?: string;
  mode?: "text" | "button";
  buttonVariant?: ButtonProps["variant"];
  buttonSize?: ButtonProps["size"];
};

export function AboutTrigger({
  label,
  className,
  mode = "text",
  buttonVariant = "ghost",
  buttonSize = "default",
}: AboutTriggerProps) {
  if (mode === "button") {
    return (
      <Button
        type="button"
        variant={buttonVariant}
        size={buttonSize}
        onClick={openAboutModal}
        className={className}
      >
        {label}
      </Button>
    );
  }

  return (
    <button
      type="button"
      onClick={openAboutModal}
      className={cn("appearance-none bg-transparent p-0 text-inherit", className)}
    >
      {label}
    </button>
  );
}
