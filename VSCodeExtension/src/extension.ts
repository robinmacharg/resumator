import * as http from "node:http";
import { URL } from "node:url";
import * as vscode from "vscode";

type GenerateRequest = {
    prompt: string;
    systemPrompt?: string;
};

type BridgeResponse = {
    ok: boolean;
    output?: string;
    error?: string;
};

let server: http.Server | null = null;
let outputChannel: vscode.OutputChannel | null = null;

type BridgeRuntimeConfig = {
    port: number;
    autoStart: boolean;
    apiKey: string;
};

type ModelAvailability = {
    ready: boolean;
    reason: string;
};

function readConfiguredApiKey(): string {
    const config = vscode.workspace.getConfiguration("cvBridge");
    return (config.get<string>("apiKey", "") || "").trim();
}

function parseBooleanEnv(raw: string | undefined, fallback: boolean): boolean {
    if (!raw) {
        return fallback;
    }
    const value = raw.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(value)) {
        return true;
    }
    if (["0", "false", "no", "off"].includes(value)) {
        return false;
    }
    return fallback;
}

function parsePortEnv(raw: string | undefined, fallback: number): number {
    if (!raw) {
        return fallback;
    }
    const value = Number.parseInt(raw, 10);
    if (!Number.isFinite(value) || value <= 0 || value > 65535) {
        return fallback;
    }
    return value;
}

function resolveRuntimeConfig(): BridgeRuntimeConfig {
    const config = vscode.workspace.getConfiguration("cvBridge");
    const configuredPort = config.get<number>("port", 8766);
    const configuredAutoStart = config.get<boolean>("autoStart", true);

    return {
        port: parsePortEnv(process.env.CV_BRIDGE_PORT, configuredPort),
        autoStart: parseBooleanEnv(process.env.CV_BRIDGE_AUTOSTART, configuredAutoStart),
        apiKey: (process.env.CV_BRIDGE_API_KEY || readConfiguredApiKey()).trim(),
    };
}

function isAuthorizedRequest(req: http.IncomingMessage, runtime: BridgeRuntimeConfig): boolean {
    const configured = runtime.apiKey;
    if (!configured) {
        return true;
    }
    const incoming = String(req.headers["x-api-key"] || "").trim();
    return incoming.length > 0 && incoming === configured;
}

function json(res: http.ServerResponse, statusCode: number, body: unknown): void {
    const payload = JSON.stringify(body);
    res.writeHead(statusCode, {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": Buffer.byteLength(payload),
        "Cache-Control": "no-store",
    });
    res.end(payload);
}

function logLine(message: string): void {
    outputChannel?.appendLine(`[${new Date().toISOString()}] ${message}`);
}

async function getModelAvailability(): Promise<ModelAvailability> {
    const lm = (vscode as unknown as { lm?: typeof vscode.lm }).lm;
    if (!lm) {
        return {
            ready: false,
            reason: "VS Code language model API is unavailable in this build.",
        };
    }

    try {
        const models = await lm.selectChatModels({ vendor: "copilot" });
        if (!models.length) {
            return {
                ready: false,
                reason: "No Copilot chat model available. Check sign-in, license, and policy settings.",
            };
        }
        return { ready: true, reason: "" };
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown model-selection error";
        return {
            ready: false,
            reason: message,
        };
    }
}

async function runCopilotPrompt(prompt: string, systemPrompt?: string): Promise<string> {
    const availability = await getModelAvailability();
    if (!availability.ready) {
        throw new Error(availability.reason);
    }

    const lm = (vscode as unknown as { lm?: typeof vscode.lm }).lm;
    if (!lm) {
        throw new Error("VS Code language model API is unavailable in this build.");
    }

    const models = await lm.selectChatModels({ vendor: "copilot" });
    const model = models[0];
    const messages: vscode.LanguageModelChatMessage[] = [];

    if (systemPrompt && systemPrompt.trim().length > 0) {
        messages.push(
            vscode.LanguageModelChatMessage.User(`System instruction: ${systemPrompt.trim()}`),
        );
    }
    messages.push(vscode.LanguageModelChatMessage.User(prompt));

    const response = await model.sendRequest(
        messages,
        {},
        new vscode.CancellationTokenSource().token,
    );

    let output = "";
    for await (const fragment of response.text) {
        output += fragment;
    }

    return output.trim();
}

async function handleGenerate(body: GenerateRequest): Promise<BridgeResponse> {
    if (!body || typeof body.prompt !== "string" || body.prompt.trim().length === 0) {
        return {
            ok: false,
            error: "Request must include a non-empty string field: prompt",
        };
    }

    const output = await runCopilotPrompt(body.prompt, body.systemPrompt);
    return {
        ok: true,
        output,
    };
}

function parseBody(req: http.IncomingMessage): Promise<unknown> {
    return new Promise((resolve, reject) => {
        let raw = "";

        req.on("data", (chunk) => {
            raw += chunk;
            if (raw.length > 1_000_000) {
                reject(new Error("Payload too large (limit 1MB)."));
            }
        });

        req.on("end", () => {
            if (!raw.trim()) {
                resolve({});
                return;
            }
            try {
                resolve(JSON.parse(raw));
            } catch {
                reject(new Error("Invalid JSON body."));
            }
        });

        req.on("error", (error) => reject(error));
    });
}

function createServer(runtime: BridgeRuntimeConfig): http.Server {
    return http.createServer(async (req, res) => {
        try {
            const url = new URL(req.url || "/", "http://127.0.0.1");

            if (!isAuthorizedRequest(req, runtime)) {
                json(res, 401, {
                    ok: false,
                    error: "Unauthorized. Provide x-api-key header.",
                });
                return;
            }

            if (req.method === "GET" && url.pathname === "/health") {
                const availability = await getModelAvailability();
                json(res, 200, {
                    ok: availability.ready,
                    status: availability.ready ? "up" : "degraded",
                    modelReady: availability.ready,
                    reason: availability.reason || undefined,
                });
                return;
            }

            if (req.method === "POST" && url.pathname === "/generate") {
                const body = (await parseBody(req)) as GenerateRequest;
                const result = await handleGenerate(body);
                json(res, result.ok ? 200 : 400, result);
                return;
            }

            json(res, 404, {
                ok: false,
                error: "Not found. Use GET /health or POST /generate",
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unexpected server error";
            logLine(`Request failed: ${message}`);
            json(res, 500, { ok: false, error: message });
        }
    });
}

async function startServer(context: vscode.ExtensionContext, runtime: BridgeRuntimeConfig): Promise<void> {
    if (server) {
        logLine("Server is already running.");
        return;
    }

    const port = runtime.port;

    server = createServer(runtime);

    await new Promise<void>((resolve, reject) => {
        server?.once("error", reject);
        server?.listen(port, "127.0.0.1", () => resolve());
    });

    context.subscriptions.push({
        dispose: () => {
            if (!server) {
                return;
            }
            server.close();
            server = null;
            logLine("Server disposed.");
        },
    });

    const apiKeyEnabled = runtime.apiKey.length > 0;
    logLine(
        `Server started on http://127.0.0.1:${port} (api key: ${apiKeyEnabled ? "enabled" : "disabled"})`,
    );
    void vscode.window.showInformationMessage(`CV Bridge started on port ${port}`);
}

async function stopServer(): Promise<void> {
    if (!server) {
        logLine("Stop requested but server is not running.");
        return;
    }

    await new Promise<void>((resolve) => {
        server?.close(() => resolve());
    });

    server = null;
    logLine("Server stopped.");
    void vscode.window.showInformationMessage("CV Bridge stopped");
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    outputChannel = vscode.window.createOutputChannel("CV Bridge");
    context.subscriptions.push(outputChannel);
    const runtime = resolveRuntimeConfig();

    context.subscriptions.push(
        vscode.commands.registerCommand("cvBridge.start", async () => {
            try {
                await startServer(context, runtime);
            } catch (error) {
                const message = error instanceof Error ? error.message : "Unable to start server";
                logLine(`Start failed: ${message}`);
                void vscode.window.showErrorMessage(`CV Bridge start failed: ${message}`);
            }
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("cvBridge.stop", async () => {
            try {
                await stopServer();
            } catch (error) {
                const message = error instanceof Error ? error.message : "Unable to stop server";
                logLine(`Stop failed: ${message}`);
                void vscode.window.showErrorMessage(`CV Bridge stop failed: ${message}`);
            }
        }),
    );

    const autoStart = runtime.autoStart;
    if (autoStart) {
        try {
            await startServer(context, runtime);
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unable to auto-start server";
            logLine(`Auto-start failed: ${message}`);
        }
    }
}

export async function deactivate(): Promise<void> {
    await stopServer();
}
