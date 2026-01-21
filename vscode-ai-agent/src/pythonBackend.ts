import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as vscode from "vscode";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export class PythonBackend {
  private proc: ChildProcess;
  private buffer = "";
  private requestId = 0;
  private callbacks = new Map<number, (result: unknown, error?: string) => void>();
  private ready = false;
  private readyPromise: Promise<void>;
  private lastError: string = "";

  constructor(pythonPath: string, extensionPath: string) {
    const projectRoot = path.resolve(extensionPath, "..");
    const wrapperPath = path.join(projectRoot, "scripts", "backend", "wrapper.py");

    this.proc = spawn(pythonPath, [wrapperPath], {
      cwd: projectRoot,
      stdio: ["pipe", "pipe", "pipe"]
    });

    this.readyPromise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Backend failed to start within 30s. Last error: ${this.lastError || "none"}`));
      }, 30000);

      const onReady = (data: Buffer) => {
        const text = data.toString();
        if (text.includes('"result":"ready"')) {
          this.ready = true;
          clearTimeout(timeout);
          resolve();
        }
      };
      this.proc.stdout?.once("data", onReady);

      this.proc.on("exit", (code) => {
        clearTimeout(timeout);
        if (!this.ready) {
          reject(new Error(`Backend exited with code ${code}. Error: ${this.lastError || "none"}`));
        }
      });
    });

    this.proc.stdout?.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      this.processBuffer();
    });

    this.proc.stderr?.on("data", (data: Buffer) => {
      this.lastError = data.toString();
      console.error("Python backend error:", data.toString());
    });

    this.proc.on("exit", (code) => {
      // Reject all pending callbacks
      for (const cb of this.callbacks.values()) {
        cb(null, `Backend process exited unexpectedly (code ${code})`);
      }
      this.callbacks.clear();
    });
  }

  private processBuffer() {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.id !== null && this.callbacks.has(msg.id)) {
          const cb = this.callbacks.get(msg.id)!;
          this.callbacks.delete(msg.id);
          cb(msg.result, msg.error);
        }
      } catch (e) {
        console.error("Failed to parse JSON:", line);
      }
    }
  }

  /**
   * Get timeout value from VSCode configuration.
   * Falls back to defaults if not configured.
   */
  private getTimeout(operation: "chat" | "normalize" | "execute" | "review" | "warmup"): number {
    const config = vscode.workspace.getConfiguration("ai-agent");
    const defaultTimeouts: Record<string, number> = {
      chat: 60000,
      normalize: 60000,
      execute: 180000,
      review: 60000,
      warmup: 120000
    };
    return config.get<number>(`timeouts.${operation}`) ?? defaultTimeouts[operation];
  }

  private async call<T>(method: string, params: Record<string, unknown>, timeoutMs: number = 180000): Promise<T> {
    await this.readyPromise;

    return new Promise((resolve, reject) => {
      const id = ++this.requestId;

      const timeout = setTimeout(() => {
        this.callbacks.delete(id);
        reject(new Error(`Request timed out after ${timeoutMs / 1000}s (method: ${method})`));
      }, timeoutMs);

      this.callbacks.set(id, (result, error) => {
        clearTimeout(timeout);
        if (error) {
          reject(new Error(error));
        } else {
          resolve(result as T);
        }
      });

      const request = {
        jsonrpc: "2.0",
        id,
        method,
        params
      };

      this.proc.stdin?.write(JSON.stringify(request) + "\n");
    });
  }

  async chat(message: string, history: ChatMessage[]): Promise<string> {
    return this.call("chat", { message, history }, this.getTimeout("chat"));
  }

  async normalizeTask(history: ChatMessage[], files: string[]): Promise<string> {
    return this.call("normalize_task", { history, files }, this.getTimeout("normalize"));
  }

  async execute(task: string, files: Record<string, string>): Promise<string> {
    return this.call("execute", { task, files }, this.getTimeout("execute"));
  }

  async reviewDiff(task: string, diff: string): Promise<string> {
    return this.call("review", { task, diff }, this.getTimeout("review"));
  }

  /**
   * Pre-load models into memory to eliminate first-request latency.
   * @param models Which models to warm up: 'critic', 'executor', or 'all'
   * @returns Object with success status for each model
   */
  async warmUp(models: "all" | "critic" | "executor" = "all"): Promise<{ critic?: boolean; executor?: boolean }> {
    return this.call("warm_up", { models }, this.getTimeout("warmup"));
  }

  /**
   * Validate file content syntax before writing to disk.
   * Defense-in-depth: catches any syntax errors that escaped earlier validation.
   * @param files Map of filename to content
   * @returns Validation result with any errors
   */
  async validateFiles(files: Record<string, string>): Promise<{ valid: boolean; errors: Record<string, string> }> {
    return this.call("validate", { files }, 10000);  // 10s timeout for validation
  }

  /**
   * Unload models to free memory.
   * @param models Which models to unload: 'critic', 'executor', or 'all'
   * @returns Object indicating which models were unloaded
   */
  async unloadModels(models: "all" | "critic" | "executor" = "all"): Promise<{ critic?: boolean; executor?: boolean }> {
    return this.call("unload", { models }, 10000);  // 10s timeout
  }

  /**
   * Get current model status including load state and idle time.
   * @returns Status object for all models plus configuration
   */
  async getModelStatus(): Promise<{
    critic: { loaded: boolean; idle_seconds: number | null; model_path: string };
    executor: { loaded: boolean; idle_seconds: number | null; model_path: string };
    config: { idle_timeout_minutes: number; auto_unload_enabled: boolean };
  }> {
    return this.call("model_status", {}, 5000);  // 5s timeout
  }

  // Legacy method for backwards compatibility
  async send(message: string, onReply: (text: string) => void) {
    try {
      const result = await this.chat(message, []);
      onReply(result);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e);
      onReply(`Error: ${message}`);
    }
  }

  dispose() {
    this.proc.kill();
  }
}
