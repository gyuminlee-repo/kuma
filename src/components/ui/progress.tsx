import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

const Progress = React.forwardRef<
  React.ComponentRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, max, ...props }, ref) => {
  const validMax = typeof max === "number" && Number.isFinite(max) && max > 0 ? max : 100;
  const validValue = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= validMax ? value : null;
  return (
  <ProgressPrimitive.Root
    ref={ref}
    value={validValue}
    max={validMax}
    className={cn(
      "relative h-2 w-full overflow-hidden rounded-full bg-primary/20",
      className,
    )}
    {...props}
  >
    <ProgressPrimitive.Indicator
      className="h-full w-full flex-1 bg-primary transition-all"
      style={{ transform: `translateX(-${100 - ((validValue ?? 0) / validMax) * 100}%)` }}
    />
  </ProgressPrimitive.Root>
  );
});
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
