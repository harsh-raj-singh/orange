import { getOpenAiApiKey } from "@/lib/orange-voice-env";

const OPENAI_TIMEOUT_MS = 45_000;
const OPENAI_AUDIO_TIMEOUT_MS = 90_000;
const DEFAULT_LLM_MODEL = "gpt-4o-mini";

type ElementSummary = {
  tagName?: string;
  type?: string | null;
  role?: string | null;
  id?: string | null;
  className?: string | null;
  name?: string | null;
  innerText?: string | null;
  ariaLabel?: string | null;
  title?: string | null;
  placeholder?: string | null;
  href?: string | null;
  value?: string | null;
  selector?: string | null;
  private?: boolean;
  rect?: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
};

type PageSummary = {
  url?: string;
  title?: string;
  headings?: string[];
  visibleText?: string;
  viewport?: { width: number; height: number };
  scroll?: { x: number; y: number };
  cursor?: { x: number; y: number };
};

export type VoiceTurnContext = {
  siteId?: string;
  sessionId?: string;
  capturedAt?: string;
  page?: PageSummary;
  element?: ElementSummary;
  visibleControls?: ElementSummary[];
};

type OpenAiResponse = {
  output_text?: string;
  output?: Array<{
    content?: Array<{
      type?: string;
      text?: string;
    }>;
  }>;
  error?: { message?: string };
};

type OpenAiErrorResponse = {
  error?: { message?: string };
};

export type SpeechToTextResult = {
  text: string;
  duration_ms?: number;
  model: string;
};

export type TextToSpeechResult = {
  audio: ArrayBuffer;
  contentType: string;
  duration_ms?: number;
  model: string;
};

function envValue(...names: string[]) {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) {
      return value;
    }
  }

  return undefined;
}

function extractOutput(data: OpenAiResponse) {
  if (data.output_text) {
    return data.output_text.trim();
  }

  const text = data.output
    ?.flatMap((item) => item.content ?? [])
    .map((part) => part.text)
    .filter(Boolean)
    .join("\n")
    .trim();

  return text || "I heard you, but I could not form a useful answer yet.";
}

function compactVoiceContext(context: VoiceTurnContext, transcript: string) {
  return {
    user_request: transcript,
    page: context.page,
    element_under_cursor: context.element,
    visible_controls: context.visibleControls?.slice(0, 24) ?? [],
    instructions:
      "Answer as the Orange website voice guide for a non-technical visitor. Use the current page text, headings, element under the cursor, and visible controls. Support English, Hindi, and natural Hinglish, matching the user's language. Explain Orange clearly, answer doubts about the website, or describe the next safe visible step. Do not click, fill, submit, delete, purchase, or claim that you changed the page. Do not mention DOM, selectors, screenshots, or internal tools. Keep the answer under 80 words.",
  };
}

function getContentType(format: string) {
  if (format === "wav") return "audio/wav";
  if (format === "opus") return "audio/ogg";
  if (format === "aac") return "audio/aac";
  if (format === "flac") return "audio/flac";
  return "audio/mpeg";
}

async function parseOpenAiError(response: Response) {
  const data = (await response.clone().json().catch(() => ({}))) as OpenAiErrorResponse;
  if (data.error?.message) {
    return data.error.message;
  }

  const text = await response.text().catch(() => "");
  return text || `OpenAI request failed with ${response.status}`;
}

async function requireOpenAiKey() {
  const apiKey = await getOpenAiApiKey();
  if (!apiKey) {
    throw new Error("Missing OPENAI_API_KEY. Set it in .env.local or production environment variables.");
  }

  return apiKey;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shouldRetry(response: Response) {
  return response.status === 408 || response.status === 409 || response.status === 429 || response.status >= 500;
}

async function fetchOpenAI(makeRequest: () => Promise<Response>) {
  const delays = [350, 900];
  let lastError: unknown;

  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    try {
      const response = await makeRequest();
      if (!shouldRetry(response) || attempt === delays.length) {
        return response;
      }
    } catch (error) {
      lastError = error;
      if (error instanceof Error && (error.name === "AbortError" || error.name === "TimeoutError")) {
        throw error;
      }
      if (attempt === delays.length) {
        throw error;
      }
    }

    await sleep(delays[attempt]);
  }

  throw lastError instanceof Error ? lastError : new Error("OpenAI request failed.");
}

export async function transcribeAudioWithOpenAI(file: File): Promise<SpeechToTextResult> {
  const apiKey = await requireOpenAiKey();
  const model = envValue("ORANGE_VOICE_TRANSCRIBE_MODEL", "OPENAI_TRANSCRIBE_MODEL") || "gpt-4o-mini-transcribe";
  const started = performance.now();
  const form = new FormData();

  form.append("model", model);
  form.append("file", file, file.name || "orange-voice.webm");
  form.append("response_format", "json");
  form.append(
    "prompt",
    "The speaker may use English, Hindi, or Hinglish while asking for help understanding or navigating the Orange website. Preserve the user's language naturally.",
  );

  const response = await fetchOpenAI(() =>
    fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: form,
      signal: AbortSignal.timeout(OPENAI_AUDIO_TIMEOUT_MS),
    }),
  );

  if (!response.ok) {
    throw new Error(await parseOpenAiError(response));
  }

  const data = (await response.json()) as { text?: string };
  return {
    text: data.text?.trim() ?? "",
    duration_ms: Math.round(performance.now() - started),
    model,
  };
}

export async function synthesizeSpeechWithOpenAI(text: string): Promise<TextToSpeechResult> {
  const apiKey = await requireOpenAiKey();
  const model = envValue("ORANGE_VOICE_TTS_MODEL", "OPENAI_TTS_MODEL") || "gpt-4o-mini-tts";
  const voice = envValue("ORANGE_VOICE_TTS_VOICE", "OPENAI_TTS_VOICE") || "coral";
  const format = envValue("ORANGE_VOICE_TTS_FORMAT", "OPENAI_TTS_FORMAT") || "mp3";
  const started = performance.now();

  const response = await fetchOpenAI(() =>
    fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        voice,
        input: text,
        response_format: format,
        instructions:
          "Speak warmly and clearly as a helpful website guide. If the text is Hindi, pronounce it naturally in Hindi. If it is Hinglish, keep the mixed-language rhythm natural.",
      }),
      signal: AbortSignal.timeout(OPENAI_AUDIO_TIMEOUT_MS),
    }),
  );

  if (!response.ok) {
    throw new Error(await parseOpenAiError(response));
  }

  return {
    audio: await response.arrayBuffer(),
    contentType: response.headers.get("content-type") || getContentType(format),
    duration_ms: Math.round(performance.now() - started),
    model,
  };
}

export async function generateVoiceReply(transcript: string, context: VoiceTurnContext) {
  const apiKey = await requireOpenAiKey();
  const requestedModel = envValue("ORANGE_VOICE_MODEL", "SAARTHI_OPENAI_MODEL", "OPENAI_VOICE_MODEL") || DEFAULT_LLM_MODEL;

  async function requestReply(model: string) {
    return fetchOpenAI(() =>
      fetch("https://api.openai.com/v1/responses", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          input: [
            {
              role: "system",
              content:
                "You are Orange Voice, a calm in-page guide for the Orange website. Speak plainly. Help visitors understand Orange, the current section, and visible actions on the page. Reply in English, Hindi, or Hinglish based on the user's language.",
            },
            {
              role: "user",
              content: [
                {
                  type: "input_text",
                  text: JSON.stringify(compactVoiceContext(context, transcript), null, 2),
                },
              ],
            },
          ],
          max_output_tokens: 220,
        }),
        signal: AbortSignal.timeout(OPENAI_TIMEOUT_MS),
      }),
    );
  }

  let model = requestedModel;
  let response = await requestReply(model);
  let data = (await response.json().catch(() => ({}))) as OpenAiResponse;

  if (!response.ok && model !== DEFAULT_LLM_MODEL && data.error?.message?.includes("does not exist")) {
    model = DEFAULT_LLM_MODEL;
    response = await requestReply(model);
    data = (await response.json().catch(() => ({}))) as OpenAiResponse;
  }

  if (!response.ok) {
    throw new Error(data.error?.message || `OpenAI request failed with ${response.status}`);
  }

  return extractOutput(data);
}

export function getDefaultLlmModel() {
  return DEFAULT_LLM_MODEL;
}
