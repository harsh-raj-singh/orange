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
  title: "Orange | Persistent memory for coding agents",
  description:
    "Orange preserves decisions, failed attempts, fixes, and evidence from one agent session so the next agent can continue with context.",
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
