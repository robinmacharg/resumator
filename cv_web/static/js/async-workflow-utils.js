/**
 * Architecture role:
 * - Layer: shared async workflow helpers.
 * - Responsibility: provide reusable polling and status-wrapped operation patterns.
 *
 * Plain-language purpose:
 * - This module removes repeated async control-flow boilerplate across features.
 */

import { sleep } from "./app-utils.js";

/**
 * Poll status until a running predicate becomes false.
 *
 * @template T
 * @param {{fetchStatus: () => Promise<T>, isRunning: (status: T) => boolean, onTick?: (status: T) => void | Promise<void>, intervalMs?: number}} options
 * @returns {Promise<T>}
 */
export async function pollUntilDone(options) {
    const { fetchStatus, isRunning, onTick, intervalMs = 1000 } = options;

    while (true) {
        const status = await fetchStatus();
        if (onTick) {
            await onTick(status);
        }

        if (!isRunning(status)) {
            return status;
        }

        await sleep(intervalMs);
    }
}

/**
 * Execute an async operation with standardized status messaging.
 *
 * @template T
 * @param {{setStatus: (message: string, isError?: boolean) => void, startMessage: string, successMessage?: string | ((result: T) => string | null | undefined), errorPrefix: string, operation: () => Promise<T>, onError?: (error: any) => void, onFinally?: () => void, rethrow?: boolean}} options
 * @returns {Promise<T | null>}
 */
export async function runWithStatusOperation(options) {
    const {
        setStatus,
        startMessage,
        successMessage,
        errorPrefix,
        operation,
        onError,
        onFinally,
        rethrow = false,
    } = options;

    setStatus(startMessage);

    try {
        const result = await operation();
        if (typeof successMessage === "function") {
            const message = successMessage(result);
            if (message) {
                setStatus(message);
            }
        } else if (typeof successMessage === "string" && successMessage) {
            setStatus(successMessage);
        }
        return result;
    } catch (err) {
        setStatus(`${errorPrefix}: ${err.message}`, true);
        if (onError) {
            onError(err);
        }
        if (rethrow) {
            throw err;
        }
        return null;
    } finally {
        if (onFinally) {
            onFinally();
        }
    }
}
