# Orange Public Site

A standalone Next.js App Router site for Orange, the developer memory fabric for agentic engineering systems.

## Run Locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Production Check

```bash
npm run build
```

## Voice Guide

The site includes the Saarthi-powered Orange Voice widget globally. It loads
`/orange-voice-widget.js`, captures a short mic turn after the user presses the
button, and posts audio plus safe visible-page context to `POST /api/voice/turn`.
If the browser blocks microphone access, the same widget can send a typed
question to that endpoint with the current page context. While Orange is
speaking, the widget shows a `Stop voice` control that immediately pauses and
clears the current audio.

Required environment:

```bash
OPENAI_API_KEY=
```

Optional overrides:

```bash
ORANGE_VOICE_MODEL=gpt-4o-mini
ORANGE_VOICE_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
ORANGE_VOICE_TTS_MODEL=gpt-4o-mini-tts
ORANGE_VOICE_TTS_VOICE=coral
ORANGE_VOICE_TTS_FORMAT=mp3
ORANGE_VOICE_ALLOWED_ORIGINS=
```

## Assets

The local PNG brand textures live in `public/`. Regenerate them with:

```bash
node scripts/make-assets.mjs
```
