/**
 * Convert a `/solve/preflop` payload into the ScenarioStrategy shape
 * the existing heatmap expects.
 */

import type { ActionKey, HandStrategy } from "./actions";
import type { ScenarioStrategy } from "./mockData";
import type { PreflopPanel, PreflopResponse } from "./api";
import { handLabel } from "./hands";

/** 169 hand-class labels in the same enumeration order as engine.hand_class.all_classes(). */
function allClassLabels(): string[] {
  return Array.from({ length: 169 }, (_, i) => {
    // Rebuild row/col from grid order then convert to canonical "AA"/"AKs"/"AKo".
    const row = Math.floor(i / 13);
    const col = i % 13;
    return handLabel(row, col);
  });
}

const FALLBACK_KIND: ActionKey = "check_call";

function panelStrategy(panel: PreflopPanel, classLabels: string[]): Record<string, HandStrategy> {
  const out: Record<string, HandStrategy> = {};
  for (const label of classLabels) {
    const probs = panel.by_class[label];
    const hs: HandStrategy = {};
    if (!probs) {
      out[label] = hs;
      continue;
    }
    panel.actions.forEach((_, i) => {
      const kind = (panel.action_kinds[i] as ActionKey) ?? FALLBACK_KIND;
      hs[kind] = (hs[kind] ?? 0) + probs[i];
    });
    out[label] = hs;
  }
  return out;
}

/** Sum of class probability * (1 - P(fold | class)) — unweighted approximation. */
function panelVpip(panel: PreflopPanel): number {
  const foldIdx = panel.actions.indexOf("fold");
  if (foldIdx < 0) return 1.0;
  // Class combo weights: pairs 6, suited 4, offsuit 12 (sum 1326).
  const labels = Object.keys(panel.by_class);
  let totalCombos = 0;
  let nonfoldCombos = 0;
  for (const label of labels) {
    const combos = label.length === 2 ? 6 : label.endsWith("s") ? 4 : 12;
    totalCombos += combos;
    const probs = panel.by_class[label];
    nonfoldCombos += combos * (1 - probs[foldIdx]);
  }
  return nonfoldCombos / Math.max(totalCombos, 1);
}

export function panelToScenario(panel: PreflopPanel): ScenarioStrategy {
  const labels = allClassLabels();
  return {
    title: panel.title,
    subtitle: panel.subtitle,
    vpip: panelVpip(panel),
    meta: {
      history: panel.history,
      actions: panel.actions,
      action_kinds: panel.action_kinds,
    },
    strategy: panelStrategy(panel, labels),
  };
}

export function responseToScenarios(r: PreflopResponse): {
  oop: ScenarioStrategy;
  ip: ScenarioStrategy;
} {
  const bb = r.panels.find((p) => p.side === "BB");
  const sb = r.panels.find((p) => p.side === "SB");
  if (!bb || !sb) throw new Error("preflop response missing SB or BB panel");
  return { oop: panelToScenario(bb), ip: panelToScenario(sb) };
}

