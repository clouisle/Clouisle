"use client";

import { cn } from "@/lib/utils";
import { type CSSProperties, type ElementType, memo } from "react";

export type TextShimmerProps = {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
};

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
  spread = 2,
}: TextShimmerProps) => (
  <Component
    className={cn("shimmer", className)}
    style={
      {
        "--shimmer-duration": `${duration}s`,
        "--shimmer-spread": `${children.length * spread}px`,
      } as CSSProperties
    }
  >
    {children}
  </Component>
);

export const Shimmer = memo(ShimmerComponent);

