import assert from "node:assert/strict";
import test from "node:test";

import { getCancelSignal } from "./runner.ts";

test("Windows cancel uses no signal", () => {
  assert.equal(getCancelSignal("win32"), undefined);
});

test("POSIX cancel uses SIGTERM", () => {
  assert.equal(getCancelSignal("darwin"), "SIGTERM");
  assert.equal(getCancelSignal("linux"), "SIGTERM");
});
