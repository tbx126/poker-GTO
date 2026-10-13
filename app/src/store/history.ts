import type { Card } from "../engine/cards";
import type { Move } from "../engine/game";
import type { Feedback } from "../gto/coach";

/** 一手牌的完整记录：牌堆和动作序列足以重放整手牌。 */
export interface HandRecord {
  id: string;
  at: number;
  players: number;
  heroSeat: number;
  deck: Card[];
  moves: Move[];
  /** 键是 moves 的下标，只记录玩家自己的决策。 */
  feedback: Record<number, Feedback>;
  net: number;
}

export interface Settings {
  players: number;
  coach: boolean;
  hints: boolean;
  fourColor: boolean;
  speed: "slow" | "normal" | "fast";
}

export const DEFAULT_SETTINGS: Settings = {
  players: 6,
  coach: true,
  hints: false,
  fourColor: false,
  speed: "normal",
};

const HISTORY_KEY = "poker-history-v1";
const SETTINGS_KEY = "poker-settings-v1";
const MAX_HANDS = 500;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 存储不可用时只保留在内存里。
  }
}

export const loadHistory = () => read<HandRecord[]>(HISTORY_KEY, []);
export const saveHistory = (hands: HandRecord[]) => write(HISTORY_KEY, hands.slice(-MAX_HANDS));
export const loadSettings = () => ({ ...DEFAULT_SETTINGS, ...read<Partial<Settings>>(SETTINGS_KEY, {}) });
export const saveSettings = (s: Settings) => write(SETTINGS_KEY, s);
