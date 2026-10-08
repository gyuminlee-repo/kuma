export interface SpinnerProps {
  size?: "sm" | "md";
  className?: string;
}

const SIZE_MAP = {
  sm: 16,
  md: 24,
} as const;

export function Spinner({ size = "md", className }: SpinnerProps) {
  const px = SIZE_MAP[size];
  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={["animate-spin text-muted-foreground", className].filter(Boolean).join(" ")}
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="47"
        strokeDashoffset="12"
        opacity="0.25"
      />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
