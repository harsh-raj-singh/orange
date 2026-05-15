import sharp from "sharp";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const outDir = new URL("../public/", import.meta.url);

function leaf(x, y, rotation, scale = 1) {
  return `
    <g transform="translate(${x} ${y}) rotate(${rotation}) scale(${scale})">
      <path d="M0 0 C46 -38 116 -28 150 15 C98 54 38 48 0 0Z" fill="url(#leafGrad)"/>
      <path d="M16 3 C58 2 100 11 137 19" fill="none" stroke="#c5d873" stroke-width="4" stroke-linecap="round" opacity=".7"/>
    </g>`;
}

function wholeOrange(x, y, r, id) {
  return `
    <g transform="translate(${x} ${y})">
      <circle r="${r}" fill="url(#orangeGrad${id})"/>
      <circle cx="${-r * 0.28}" cy="${-r * 0.32}" r="${r * 0.18}" fill="#ffd57a" opacity=".44"/>
      <circle cx="${r * 0.36}" cy="${r * 0.24}" r="${r * 0.58}" fill="#bd4c1f" opacity=".14"/>
      <path d="M${-r * 0.42} ${-r * 0.54} C${-r * 0.12} ${-r * 0.68} ${r * 0.36} ${-r * 0.62} ${r * 0.56} ${-r * 0.26}" fill="none" stroke="#ffe0a0" stroke-width="${r * 0.05}" stroke-linecap="round" opacity=".42"/>
    </g>`;
}

function slice(x, y, r, rotation = 0) {
  return `
    <g transform="translate(${x} ${y}) rotate(${rotation})">
      <circle r="${r}" fill="#f8f1d2"/>
      <circle r="${r * 0.86}" fill="#ffad23"/>
      <circle r="${r * 0.66}" fill="#f47e1f" opacity=".9"/>
      ${Array.from({ length: 10 })
        .map((_, i) => {
          const angle = (i * 36 * Math.PI) / 180;
          return `<path d="M0 0 L${Math.cos(angle) * r * 0.7} ${Math.sin(angle) * r * 0.7}" stroke="#ffd982" stroke-width="${r * 0.025}" opacity=".75"/>`;
        })
        .join("")}
      <circle r="${r * 0.18}" fill="#ffd982" opacity=".8"/>
    </g>`;
}

function svgShell(width, height, body) {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <defs>
        <radialGradient id="orangeGrad1" cx="35%" cy="28%" r="78%">
          <stop offset="0" stop-color="#ffe28a"/>
          <stop offset=".42" stop-color="#ff9f1c"/>
          <stop offset="1" stop-color="#b64b18"/>
        </radialGradient>
        <radialGradient id="orangeGrad2" cx="32%" cy="26%" r="80%">
          <stop offset="0" stop-color="#ffe7a4"/>
          <stop offset=".5" stop-color="#f28c18"/>
          <stop offset="1" stop-color="#9d4319"/>
        </radialGradient>
        <radialGradient id="orangeGrad3" cx="38%" cy="30%" r="78%">
          <stop offset="0" stop-color="#fff0ad"/>
          <stop offset=".45" stop-color="#ffb12e"/>
          <stop offset="1" stop-color="#c65a1f"/>
        </radialGradient>
        <linearGradient id="leafGrad" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#84a94b"/>
          <stop offset=".52" stop-color="#315f43"/>
          <stop offset="1" stop-color="#173629"/>
        </linearGradient>
        <linearGradient id="paper" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#f6e9cc"/>
          <stop offset=".55" stop-color="#d8bd8a"/>
          <stop offset="1" stop-color="#a8753d"/>
        </linearGradient>
        <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="30" stdDeviation="26" flood-color="#241507" flood-opacity=".36"/>
        </filter>
        <filter id="texture" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency=".82" numOctaves="2" stitchTiles="stitch"/>
          <feColorMatrix type="saturate" values=".15"/>
          <feComponentTransfer>
            <feFuncA type="table" tableValues="0 .13"/>
          </feComponentTransfer>
        </filter>
      </defs>
      ${body}
    </svg>`;
}

const hero = svgShell(
  1800,
  1200,
  `
    <rect width="1800" height="1200" fill="#1b251b"/>
    <path d="M0 820 C320 690 540 810 870 690 C1220 563 1480 640 1800 520 L1800 1200 L0 1200Z" fill="#714421"/>
    <path d="M0 760 C330 620 620 702 920 612 C1270 508 1510 530 1800 392 L1800 1200 L0 1200Z" fill="#2b5a42" opacity=".78"/>
    <rect x="0" y="0" width="1800" height="1200" filter="url(#texture)" opacity=".5"/>
    ${leaf(1060, 260, -16, 1.5)}
    ${leaf(1250, 365, 22, 1.18)}
    ${leaf(1385, 560, -28, 1.2)}
    <g filter="url(#shadow)">
      ${wholeOrange(1190, 650, 184, 1)}
      ${wholeOrange(1428, 725, 148, 2)}
      ${wholeOrange(1018, 812, 130, 3)}
      ${slice(1322, 500, 128, -18)}
      ${slice(1558, 532, 102, 20)}
    </g>
    <path d="M1045 996 C1220 1100 1470 1090 1648 982" fill="none" stroke="#f1d18e" stroke-width="15" stroke-linecap="round" opacity=".32"/>
  `,
);

const box = svgShell(
  1200,
  960,
  `
    <rect width="1200" height="960" fill="#265347"/>
    <rect x="0" y="0" width="1200" height="960" filter="url(#texture)" opacity=".36"/>
    <g transform="translate(145 250)" filter="url(#shadow)">
      <path d="M90 240 L860 80 L1010 460 L222 710Z" fill="url(#paper)"/>
      <path d="M90 240 L222 710 L40 548 Z" fill="#9b6335"/>
      <path d="M222 710 L1010 460 L866 640 L340 820Z" fill="#80512d"/>
      <path d="M860 80 L1010 460 L1100 268 L958 18Z" fill="#b9824b"/>
    </g>
    <g filter="url(#shadow)">
      ${wholeOrange(455, 410, 116, 1)}
      ${wholeOrange(610, 360, 104, 2)}
      ${wholeOrange(760, 455, 126, 3)}
      ${wholeOrange(565, 545, 122, 2)}
      ${slice(842, 320, 88, 16)}
      ${leaf(565, 232, -12, .82)}
      ${leaf(713, 245, 34, .7)}
    </g>
    <path d="M250 735 C430 810 710 792 920 668" fill="none" stroke="#f4d69c" stroke-width="12" stroke-linecap="round" opacity=".26"/>
  `,
);

const detail = svgShell(
  1000,
  780,
  `
    <rect width="1000" height="780" fill="#fffaf0"/>
    <rect x="0" y="0" width="1000" height="780" filter="url(#texture)" opacity=".4"/>
    <path d="M0 575 C260 510 430 640 700 520 C840 458 918 406 1000 390 L1000 780 L0 780Z" fill="#265347"/>
    <g filter="url(#shadow)">
      ${slice(358, 384, 202, -12)}
      ${slice(580, 300, 156, 18)}
      ${wholeOrange(710, 512, 132, 1)}
      ${wholeOrange(244, 560, 118, 2)}
      ${leaf(610, 138, 6, .9)}
      ${leaf(736, 215, -28, .72)}
    </g>
  `,
);

await mkdir(outDir, { recursive: true });
await Promise.all([
  sharp(Buffer.from(hero))
    .png()
    .toFile(fileURLToPath(new URL("orange-hero.png", outDir))),
  sharp(Buffer.from(box))
    .png()
    .toFile(fileURLToPath(new URL("orange-box.png", outDir))),
  sharp(Buffer.from(detail))
    .png()
    .toFile(fileURLToPath(new URL("orange-detail.png", outDir))),
]);
