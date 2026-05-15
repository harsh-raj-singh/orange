"use client";

import { useEffect } from "react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import "lenis/dist/lenis.css";

gsap.registerPlugin(ScrollTrigger);

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function SiteMotion() {
  useEffect(() => {
    const reducedMotion = prefersReducedMotion();
    const lenis = reducedMotion
      ? null
      : new Lenis({
          lerp: 0.085,
          smoothWheel: true,
          anchors: true,
        });

    const updateLenis = (time: number) => {
      lenis?.raf(time * 1000);
    };

    if (lenis) {
      lenis.on("scroll", ScrollTrigger.update);
      gsap.ticker.add(updateLenis);
      gsap.ticker.lagSmoothing(0);
    }

    const handleScroll = () => {
      document.documentElement.toggleAttribute("data-scrolled", window.scrollY > 50);
    };

    const handlePointerMove = (event: PointerEvent) => {
      document.documentElement.style.setProperty("--cursor-x", `${event.clientX}px`);
      document.documentElement.style.setProperty("--cursor-y", `${event.clientY}px`);
    };

    handleScroll();
    const scrollPoll = window.setInterval(handleScroll, 150);
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("pointermove", handlePointerMove, { passive: true });

    if (!reducedMotion) {
      let media: ReturnType<typeof gsap.matchMedia> | null = null;
      let refreshTimer = 0;
      const ctx = gsap.context(() => {
        gsap.fromTo(
          "[data-hero-word]",
          { yPercent: 120, opacity: 0, rotateX: -18 },
          {
            yPercent: 0,
            opacity: 1,
            rotateX: 0,
            duration: 0.85,
            ease: "power3.out",
            stagger: 0.075,
            delay: 0.1,
          },
        );

        gsap.fromTo(
          "[data-ping-card]",
          { y: 34, opacity: 0, scale: 0.96 },
          { y: 0, opacity: 1, scale: 1, duration: 0.9, ease: "power3.out", delay: 0.38 },
        );

        const score = document.querySelector<HTMLElement>("[data-score-target]");
        if (score) {
          const state = { value: 0 };
          const target = Number(score.dataset.scoreTarget ?? "0.91");
          score.textContent = "0.00";
          gsap.to(state, {
            value: target,
            duration: 1.15,
            delay: 0.74,
            ease: "power2.out",
            onUpdate: () => {
              score.textContent = state.value.toFixed(2);
            },
          });
        }

        gsap.fromTo(
          "[data-ping-line]",
          { y: 14, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.42, ease: "power2.out", stagger: 0.08, delay: 0.78 },
        );

        gsap.fromTo(
          "[data-hero-metric]",
          { y: 22, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.6, ease: "power2.out", stagger: 0.08, delay: 1.0 },
        );

        gsap.to("[data-hero-glow]", {
          x: 42,
          y: -28,
          scale: 1.08,
          duration: 7,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
        });

        gsap.utils.toArray<HTMLElement>("[data-line-reveal]").forEach((line) => {
          gsap.fromTo(
            line,
            { yPercent: 110, opacity: 0 },
            {
              yPercent: 0,
              opacity: 1,
              duration: 0.8,
              ease: "power3.out",
              scrollTrigger: {
                trigger: line.closest("section") ?? line,
                start: "top 78%",
              },
            },
          );
        });

        gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((element) => {
          gsap.fromTo(
            element,
            { y: 24, opacity: 0 },
            {
              y: 0,
              opacity: 1,
              duration: 0.72,
              ease: "power2.out",
              scrollTrigger: {
                trigger: element,
                start: "top 84%",
              },
            },
          );
        });

        gsap.fromTo(
          "[data-bento-card]",
          { y: 30, opacity: 0, scale: 0.98 },
          {
            y: 0,
            opacity: 1,
            scale: 1,
            duration: 0.72,
            ease: "power3.out",
            stagger: 0.15,
            scrollTrigger: {
              trigger: "[data-bento-grid]",
              start: "top 78%",
            },
          },
        );

        gsap.utils.toArray<HTMLElement>("[data-count-to]").forEach((counter) => {
          const target = Number(counter.dataset.countTo ?? "0");
          const decimals = Number(counter.dataset.countDecimals ?? "0");
          const prefix = counter.dataset.countPrefix ?? "";
          const suffix = counter.dataset.countSuffix ?? "";
          const state = { value: 0 };

          gsap.to(state, {
            value: target,
            duration: 1.2,
            ease: "power2.out",
            scrollTrigger: {
              trigger: counter,
              start: "top 86%",
              once: true,
            },
            onUpdate: () => {
              counter.textContent = `${prefix}${state.value.toFixed(decimals)}${suffix}`;
            },
          });
        });

        gsap.utils.toArray<HTMLElement>("[data-type-code]").forEach((block) => {
          const source = block.textContent ?? "";
          block.dataset.typed = "false";
          ScrollTrigger.create({
            trigger: block,
            start: "top 82%",
            once: true,
            onEnter: () => {
              if (block.dataset.typed === "true") {
                return;
              }
              block.dataset.typed = "true";
              block.textContent = "";
              let index = 0;
              const typeNext = () => {
                block.textContent = source.slice(0, index);
                index += 1;
                if (index <= source.length) {
                  window.setTimeout(typeNext, source[index - 1] === "\n" ? 80 : 18);
                }
              };
              typeNext();
            },
          });
        });

        const story = document.querySelector<HTMLElement>("[data-scroll-story]");
        const storyTrack = document.querySelector<HTMLElement>("[data-story-track]");
        const storyViewport = document.querySelector<HTMLElement>("[data-story-viewport]");
        if (story && storyTrack && storyViewport) {
          media = gsap.matchMedia();
          media.add("(min-width: 1024px)", () => {
            const tween = gsap.to(storyTrack, {
              x: () => -(storyTrack.scrollWidth - storyViewport.clientWidth),
              ease: "none",
              scrollTrigger: {
                trigger: story,
                pin: true,
                scrub: 1,
                start: "top top",
                end: () => `+=${storyTrack.scrollWidth}`,
                invalidateOnRefresh: true,
              },
            });

            return () => tween.kill();
          });
        }

        gsap.utils.toArray<HTMLElement>("[data-story-type]").forEach((line) => {
          gsap.fromTo(
            line,
            { width: 0 },
            {
              width: "100%",
              duration: 1.4,
              ease: "steps(36)",
              scrollTrigger: {
                trigger: line,
                start: "top 72%",
              },
            },
          );
        });
      });

      refreshTimer = window.setTimeout(() => ScrollTrigger.refresh(), 250);

      return () => {
        window.clearTimeout(refreshTimer);
        window.clearInterval(scrollPoll);
        media?.revert();
        ctx.revert();
        window.removeEventListener("scroll", handleScroll);
        window.removeEventListener("pointermove", handlePointerMove);
        gsap.ticker.remove(updateLenis);
        lenis?.destroy();
      };
    }

    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("pointermove", handlePointerMove);
      window.clearInterval(scrollPoll);
      gsap.ticker.remove(updateLenis);
      lenis?.destroy();
    };
  }, []);

  return <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-50 cursor-glow" />;
}
