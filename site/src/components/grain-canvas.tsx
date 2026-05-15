"use client";

import { useEffect, useRef } from "react";

export default function GrainCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const currentCanvas = canvas;
    const context = currentCanvas.getContext("2d", { alpha: true });
    if (!context) {
      return;
    }
    const drawingContext = context;

    let frame = 0;
    let animationFrame = 0;
    let width = 0;
    let height = 0;

    function resize() {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(currentCanvas.clientWidth * pixelRatio));
      height = Math.max(1, Math.floor(currentCanvas.clientHeight * pixelRatio));
      currentCanvas.width = width;
      currentCanvas.height = height;
    }

    function draw() {
      frame += 1;
      if (frame % 3 === 0) {
        const image = drawingContext.createImageData(width, height);
        const data = image.data;

        for (let index = 0; index < data.length; index += 4) {
          const value = Math.random() * 255;
          data[index] = value;
          data[index + 1] = value;
          data[index + 2] = value;
          data[index + 3] = 18;
        }

        drawingContext.putImageData(image, 0, 0);
      }

      animationFrame = window.requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.03] mix-blend-multiply"
    />
  );
}
