import type { ZsumSettings } from "./settings";

export interface CostEstimate {
  pending_cards: number;
  cost_usd: number;
  cost_display: string;
}

export function estimateCost(
  pendingCards: number,
  settings: ZsumSettings
): CostEstimate {
  const perCard =
    (settings.tokensPerCardIn * settings.costPerMTokenIn) / 1e6 +
    (settings.tokensPerCardOut * settings.costPerMTokenOut) / 1e6;
  const total = pendingCards * perCard;
  return {
    pending_cards: pendingCards,
    cost_usd: total,
    cost_display: `~$${total.toFixed(2)}`,
  };
}
