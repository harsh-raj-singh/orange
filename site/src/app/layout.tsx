import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import SiteMotion from "@/components/site-motion";
import OrangeVoiceWidget from "@/components/orange-voice-widget";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "https://site-sage-eta-18.vercel.app",
  ),
  title: "Orange | Memory for every AI you use",
  description:
    "Orange remembers the decisions, fixes, and context your team would otherwise lose—so every AI conversation can begin ahead.",
  openGraph: {
    title: "Orange | Your AI should remember what matters.",
    description:
      "One shared memory for the AI tools your team already uses.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Orange — Your AI should remember what matters." }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Orange | Your AI should remember what matters.",
    description: "One shared memory for the AI tools your team already uses.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="min-h-full antialiased">
        <SiteMotion />
        {children}
        <OrangeVoiceWidget />
      </body>
    </html>
  );
}
