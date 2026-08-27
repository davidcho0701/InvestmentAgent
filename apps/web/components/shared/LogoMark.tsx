/** 캔들스틱 모티프의 브랜드 아이콘. currentColor 를 써서 부모의 text-* 색을 그대로 따른다. */
export default function LogoMark({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <line
        x1="7"
        y1="3"
        x2="7"
        y2="21"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.55"
      />
      <rect x="4.5" y="9" width="5" height="7" rx="1" fill="currentColor" />
      <line
        x1="17"
        y1="2"
        x2="17"
        y2="20"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.55"
      />
      <rect x="14.5" y="5" width="5" height="10" rx="1" fill="currentColor" />
    </svg>
  );
}
