export function BrandMark({
  size = 28,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`brand-mark ${className}`.trim()}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <svg viewBox="0 0 28 28" fill="none" width={size} height={size}>
        <rect width="28" height="28" rx="7" fill="currentColor" />
        <path
          d="M5 14h3.2l1.6-4.2 2.4 9.4L15.4 8l1.8 6H23"
          stroke="#fff"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
