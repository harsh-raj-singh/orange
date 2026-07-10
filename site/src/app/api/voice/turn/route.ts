import { json, optionsResponse } from "@/lib/orange-voice-cors";
import {
  generateVoiceReply,
  getDefaultLlmModel,
  synthesizeSpeechWithOpenAI,
  transcribeAudioWithOpenAI,
  type VoiceTurnContext,
} from "@/lib/orange-voice-openai";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_AUDIO_BYTES = 15 * 1024 * 1024;
const MAX_REQUEST_BYTES = 18 * 1024 * 1024;
const MAX_TEXT_CHARS = 1200;

type TextVoiceRequest = {
  question?: unknown;
  text?: unknown;
  context?: unknown;
};

function allowedOrigins() {
  return (process.env.ORANGE_VOICE_ALLOWED_ORIGINS || process.env.SAARTHI_ALLOWED_ORIGINS || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function isAllowedOrigin(request: Request) {
  const origins = allowedOrigins();
  if (!origins.length) {
    return true;
  }

  const origin = request.headers.get("origin");
  return !origin || origins.includes(origin);
}

export function OPTIONS() {
  return optionsResponse();
}

function parseContext(value: unknown): VoiceTurnContext {
  if (value && typeof value === "object") {
    return value as VoiceTurnContext;
  }

  if (typeof value !== "string") {
    return {};
  }

  try {
    return JSON.parse(value) as VoiceTurnContext;
  } catch {
    return {};
  }
}

function normalizeQuestion(value: unknown) {
  return typeof value === "string" ? value.trim().slice(0, MAX_TEXT_CHARS) : "";
}

async function answerTurn(transcript: string, context: VoiceTurnContext, asrModel: string) {
  const reply = await generateVoiceReply(transcript, context);
  const speech = await synthesizeSpeechWithOpenAI(reply);

  return json({
    ok: true,
    transcript,
    reply,
    audio: {
      contentType: speech.contentType,
      base64: Buffer.from(speech.audio).toString("base64"),
    },
    models: {
      asr: asrModel,
      tts: speech.model,
      llm: process.env.ORANGE_VOICE_MODEL?.trim() || getDefaultLlmModel(),
    },
  });
}

export async function POST(request: Request) {
  try {
    if (!isAllowedOrigin(request)) {
      return json({ ok: false, error: "This origin is not allowed to use Orange Voice." }, { status: 403 });
    }

    const contentLength = Number(request.headers.get("content-length") || 0);
    if (contentLength > MAX_REQUEST_BYTES) {
      return json({ ok: false, error: "Voice request is too large." }, { status: 413 });
    }

    const contentType = request.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      let body: TextVoiceRequest;
      try {
        body = (await request.json()) as TextVoiceRequest;
      } catch {
        return json({ ok: false, error: "Text question payload must be valid JSON." }, { status: 400 });
      }

      const question = normalizeQuestion(body.question ?? body.text);
      if (!question) {
        return json({ ok: false, error: "Type a question for Orange." }, { status: 400 });
      }

      return answerTurn(question, parseContext(body.context), "typed");
    }

    let form: FormData;
    try {
      form = await request.formData();
    } catch {
      return json({ ok: false, error: "Invalid voice upload." }, { status: 400 });
    }

    const audio = form.get("audio");
    const context = parseContext(form.get("context"));

    if (!(audio instanceof File)) {
      return json({ ok: false, error: "Missing audio recording." }, { status: 400 });
    }

    if (audio.size > MAX_AUDIO_BYTES) {
      return json({ ok: false, error: "Audio recording is too large." }, { status: 413 });
    }

    const transcript = await transcribeAudioWithOpenAI(audio);
    if (!transcript.text) {
      return json(
        {
          ok: false,
          error: "I could not hear enough speech. Please try again closer to the microphone.",
        },
        { status: 400 },
      );
    }

    return answerTurn(transcript.text, context, transcript.model);
  } catch (error) {
    return json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Orange Voice could not process that voice turn.",
      },
      { status: 500 },
    );
  }
}
