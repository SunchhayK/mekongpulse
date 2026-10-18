// Minimal inline icons (no icon-font dependency; works offline).

const base = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** Roundel brand mark: stacked river waves on navy, with a sky accent dot. */
export function BrandMark({ size = 38 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="11" fill="var(--navy)" />
      <path
        d="M8 15.5c3 0 3-2.6 6-2.6s3 2.6 6 2.6 3-2.6 6-2.6 3 2.6 6 2.6"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M8 23.5c3 0 3-2.6 6-2.6s3 2.6 6 2.6 3-2.6 6-2.6 3 2.6 6 2.6"
        fill="none"
        stroke="#7cc7f2"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M8 31.5c3 0 3-2.6 6-2.6s3 2.6 6 2.6 3-2.6 6-2.6 3 2.6 6 2.6"
        fill="none"
        stroke="#3f5f94"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function WaveIcon() {
  return (
    <svg {...base} width={22} height={22}>
      <path d="M2 12c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3" />
      <path d="M2 18c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3" />
    </svg>
  );
}

export function MapPinIcon() {
  return (
    <svg {...base}>
      <path d="M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

export function MapIcon() {
  return (
    <svg {...base}>
      <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z" />
      <path d="M9 4v14M15 6v14" />
    </svg>
  );
}

export function SearchIcon() {
  return (
    <svg {...base}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export function PlayIcon() {
  return (
    <svg {...base} width={22} height={22} fill="currentColor" stroke="none">
      <path d="M8 5.5v13l11-6.5-11-6.5z" />
    </svg>
  );
}

export function PauseIcon() {
  return (
    <svg {...base} width={22} height={22} fill="currentColor" stroke="none">
      <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
    </svg>
  );
}

export function VolumeIcon() {
  return (
    <svg {...base} width={16} height={16}>
      <path d="M11 5 6 9H3v6h3l5 4V5z" />
      <path d="M15 9a4 4 0 0 1 0 6M17.5 6.5a8 8 0 0 1 0 11" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg {...base}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function InfoIcon() {
  return (
    <svg {...base}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7.5v.5" />
    </svg>
  );
}

export function AlertIcon() {
  return (
    <svg {...base}>
      <path d="M12 3.5 2.5 20h19L12 3.5z" />
      <path d="M12 10v4.5M12 17.4v.1" />
    </svg>
  );
}

export function RefreshIcon() {
  return (
    <svg {...base} width={18} height={18}>
      <path d="M20 11a8 8 0 1 0-2.5 6.5" />
      <path d="M20 5v6h-6" />
    </svg>
  );
}

export function ShareIcon() {
  return (
    <svg {...base} width={18} height={18}>
      <path d="M12 3v12" />
      <path d="m7.5 7.5 4.5-4.5 4.5 4.5" />
      <path d="M5 13v6.5h14V13" />
    </svg>
  );
}

export function ArrowLeftIcon() {
  return (
    <svg {...base} width={18} height={18}>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </svg>
  );
}

export function SendIcon() {
  return (
    <svg {...base} width={18} height={18}>
      <path d="M4 11.5 20 4l-6 16-3.5-7L4 11.5z" />
    </svg>
  );
}
