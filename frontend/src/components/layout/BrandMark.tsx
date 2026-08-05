export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-lockup" aria-label="MathGraph AI">
      <span className="brand-badge" aria-hidden="true">
        <svg className="brand-symbol" viewBox="0 0 48 48">
          <path d="M4 34c7-18 13-22 19-4 4 12 8 4 13-6" />
          <path d="M5 32c9-7 19-4 29-11" />
          <path d="m36 9 1.5 5.5L43 16l-5.5 1.5L36 23l-1.5-5.5L29 16l5.5-1.5L36 9Z" className="spark" />
        </svg>
      </span>
      {!compact && <span>MathGraph AI</span>}
    </div>
  );
}
