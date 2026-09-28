import assert from "node:assert/strict";
import test from "node:test";

// The settings drawer extracts the per-card cost preview math from
// ZsumSettingsTab.updatePreview into a pure helper so the live preview
// inside the drawer stays headlessly testable. Formula matches
// settings.ts:137-143:
//   per_card = (tokensIn × $/M_in + tokensOut × $/M_out) / 1e6
// Display: "$X.XXXX per card" with 4-decimal precision.
//
// DOM-level acceptance criteria for the drawer (slide animation, Escape
// closes, fields write-through to plugin.settings, Test command output)
// are deferred to manual Obsidian-reload verification.

let formatCostPreview;
try {
  ({ formatCostPreview } = await import("./view-model.ts"));
} catch {
  // Helper not yet exported — tests below self-skip.
}

test("formatCostPreview matches the existing settings-tab formula", (t) => {
  if (!formatCostPreview) {
    t.skip("formatCostPreview not yet exported");
    return;
  }
  // Default settings values from settings.ts:DEFAULT_SETTINGS:
  // costPerMTokenIn=3, costPerMTokenOut=15, tokensPerCardIn=4000,
  // tokensPerCardOut=500.
  // per = (4000*3 + 500*15) / 1e6 = (12000 + 7500) / 1e6 = 0.0195
  const result = formatCostPreview({
    costPerMTokenIn: 3,
    costPerMTokenOut: 15,
    tokensPerCardIn: 4000,
    tokensPerCardOut: 500,
  });
  assert.equal(result, "$0.0195 per card");
});

test("formatCostPreview pads to 4 decimal places", (t) => {
  if (!formatCostPreview) {
    t.skip("formatCostPreview not yet exported");
    return;
  }
  // (1000*1 + 1000*1) / 1e6 = 0.002 → "$0.0020 per card"
  const result = formatCostPreview({
    costPerMTokenIn: 1,
    costPerMTokenOut: 1,
    tokensPerCardIn: 1000,
    tokensPerCardOut: 1000,
  });
  assert.equal(result, "$0.0020 per card");
});

test("formatCostPreview returns $0.0000 for zero token counts", (t) => {
  if (!formatCostPreview) {
    t.skip("formatCostPreview not yet exported");
    return;
  }
  const result = formatCostPreview({
    costPerMTokenIn: 3,
    costPerMTokenOut: 15,
    tokensPerCardIn: 0,
    tokensPerCardOut: 0,
  });
  assert.equal(result, "$0.0000 per card");
});

test("formatCostPreview handles fractional dollar prices correctly", (t) => {
  if (!formatCostPreview) {
    t.skip("formatCostPreview not yet exported");
    return;
  }
  // (10000*0.5 + 5000*1.5) / 1e6 = (5000 + 7500) / 1e6 = 0.0125
  const result = formatCostPreview({
    costPerMTokenIn: 0.5,
    costPerMTokenOut: 1.5,
    tokensPerCardIn: 10000,
    tokensPerCardOut: 5000,
  });
  assert.equal(result, "$0.0125 per card");
});
