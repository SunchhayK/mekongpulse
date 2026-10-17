import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Kantumruy_Pro } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

// Khmer coverage; falls back for any glyphs IBM Plex Sans does not carry.
const kantumruy = Kantumruy_Pro({
  subsets: ["khmer", "latin"],
  weight: ["400", "500", "600"],
  variable: "--font-kantumruy",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MekongPulse — Cambodia River Telemetry & Flood Guard",
  description:
    "Live Mekong, Bassac, and Tonle Sap telemetry, commune flood-risk tiers, and agronomic directives for Cambodia.",
};

export const viewport: Viewport = {
  themeColor: "#eef2f7",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} ${kantumruy.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
