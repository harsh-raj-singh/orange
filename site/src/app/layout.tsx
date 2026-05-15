import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import SiteMotion from "@/components/site-motion";
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
  title: "Orange | Memory Fabric for Agentic Engineering",
  description:
    "Orange captures developer sessions from agentic tools and retrieves graph-backed context when future agents need it.",
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
      </body>
    </html>
  );
}
