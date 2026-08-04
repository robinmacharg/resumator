import test from "node:test";
import assert from "node:assert/strict";

import { pollUntilDone, runWithStatusOperation } from "../async-workflow-utils.js";

test("pollUntilDone returns final status and emits ticks", async () => {
    const statuses = [
        { running: true, value: 1 },
        { running: true, value: 2 },
        { running: false, value: 3 },
    ];
    const seen = [];

    const result = await pollUntilDone({
        fetchStatus: async () => statuses.shift(),
        isRunning: (status) => status.running,
        onTick: (status) => seen.push(status.value),
        intervalMs: 0,
    });

    assert.equal(result.value, 3);
    assert.deepEqual(seen, [1, 2, 3]);
});

test("runWithStatusOperation emits start/success and returns result", async () => {
    const messages = [];

    const result = await runWithStatusOperation({
        setStatus: (message, isError = false) => messages.push({ message, isError }),
        startMessage: "Starting...",
        successMessage: (value) => `Done: ${value}`,
        errorPrefix: "Failed",
        operation: async () => "ok",
    });

    assert.equal(result, "ok");
    assert.deepEqual(messages, [
        { message: "Starting...", isError: false },
        { message: "Done: ok", isError: false },
    ]);
});

test("runWithStatusOperation emits error and calls onError", async () => {
    const messages = [];
    let seenError = null;

    const result = await runWithStatusOperation({
        setStatus: (message, isError = false) => messages.push({ message, isError }),
        startMessage: "Starting...",
        errorPrefix: "Failed",
        operation: async () => {
            throw new Error("boom");
        },
        onError: (error) => {
            seenError = error;
        },
    });

    assert.equal(result, null);
    assert.equal(seenError.message, "boom");
    assert.deepEqual(messages, [
        { message: "Starting...", isError: false },
        { message: "Failed: boom", isError: true },
    ]);
});
