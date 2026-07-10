"use client";

import { usePathname } from "next/navigation";
import Script from "next/script";

export default function OrangeVoiceWidget() {
  const pathname = usePathname();

  if (pathname !== "/") {
    return null;
  }

  return (
    <Script
      src="/orange-voice-widget.js"
      strategy="afterInteractive"
      data-site-id="orange-site"
      data-assistant-name="Orange Voice"
      data-cta-label="Ask Orange"
    />
  );
}
