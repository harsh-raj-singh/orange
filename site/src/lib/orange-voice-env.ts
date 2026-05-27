import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";

let cachedOpenAiKey: string | null | undefined;

export function getEnv(name: string) {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

function parseEnvValue(contents: string, key: string) {
  const direct = contents.trim();
  if (direct.startsWith("sk-")) {
    return direct;
  }

  const pattern = new RegExp(`^\\s*${key}\\s*=\\s*(.+?)\\s*$`, "m");
  const match = contents.match(pattern);
  if (!match) {
    return undefined;
  }

  return match[1].replace(/^['"]|['"]$/g, "").trim();
}

export async function getOpenAiApiKey() {
  if (cachedOpenAiKey !== undefined) {
    return cachedOpenAiKey;
  }

  const envKey = getEnv("OPENAI_API_KEY");
  if (envKey) {
    cachedOpenAiKey = envKey;
    return cachedOpenAiKey;
  }

  const home = homedir();
  const candidates = [
    getEnv("OPENAI_API_KEY_FILE"),
    getEnv("ORANGE_VOICE_OPENAI_KEY_FILE"),
    getEnv("SAARTHI_OPENAI_KEY_FILE"),
    path.join(home, "Desktop/files/orange/openai_api_key.txt"),
    path.join(home, "Desktop/files/orange/.env"),
    path.join(home, "Desktop/files/.env"),
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    try {
      const contents = await readFile(candidate, "utf8");
      const parsed = parseEnvValue(contents, "OPENAI_API_KEY");
      if (parsed) {
        cachedOpenAiKey = parsed;
        return cachedOpenAiKey;
      }
    } catch {
      // Local key files are optional.
    }
  }

  cachedOpenAiKey = null;
  return cachedOpenAiKey;
}
