import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-sm px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        solid: "bg-ink text-panel hover:bg-rail",
        outline: "border border-ink/40 bg-transparent text-ink hover:bg-ink/5",
        danger: "border border-stop text-stop hover:bg-stop/10",
      },
    },
    defaultVariants: { variant: "solid" },
  },
);

export function Button({ className, variant, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>) {
  return <button className={cn(button({ variant }), className)} {...props} />;
}

export const buttonClass = (variant: VariantProps<typeof button>["variant"] = "solid") => button({ variant });
