import type { Metadata, Viewport } from "next";
import { Kantumruy_Pro, Roboto, Roboto_Mono } from "next/font/google";
import "./globals.css";

const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-roboto",
  display: "swap",
});

const kantumruy = Kantumruy_Pro({
  subsets: ["khmer", "latin"],
  weight: ["400", "500", "600"],
  variable: "--font-kantumruy",
  display: "swap",
});

const robotoMono = Roboto_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-roboto-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MekongPulse — Cambodia River Telemetry & Flood Guard",
  description:
    "Live Mekong, Bassac, and Tonle Sap telemetry, commune flood-risk tiers, and agronomic directives for Cambodia.",
};

export const viewport: Viewport = {
  themeColor: "#0f1419",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${roboto.variable} ${kantumruy.variable} ${robotoMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
