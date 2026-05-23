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
    const bufferCanvas = document.createElement("canvas");
    const bufferContext = bufferCanvas.getContext("2d", { alpha: true });
    if (!bufferContext) {
      return;
    }
    const offscreenContext = bufferContext;

    let intervalId = 0;
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
      const noiseSize = 160;
      bufferCanvas.width = noiseSize;
      bufferCanvas.height = noiseSize;
      const image = offscreenContext.createImageData(noiseSize, noiseSize);
      const data = image.data;

      for (let index = 0; index < data.length; index += 4) {
        const value = Math.random() * 255;
        data[index] = value;
        data[index + 1] = value;
        data[index + 2] = value;
        data[index + 3] = 16;
      }

      offscreenContext.putImageData(image, 0, 0);
      drawingContext.clearRect(0, 0, width, height);
      drawingContext.imageSmoothingEnabled = false;
      drawingContext.drawImage(bufferCanvas, 0, 0, width, height);
    }

    resize();
    draw();
    intervalId = window.setInterval(draw, 220);
    window.addEventListener("resize", resize);

    return () => {
      window.clearInterval(intervalId);
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
