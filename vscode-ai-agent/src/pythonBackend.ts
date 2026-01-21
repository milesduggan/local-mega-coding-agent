import { spawn, ChildProcess } from "child_process";
import * as path from "path";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export class PythonBackend {
  private proc: ChildProcess;
  private buffer = "";
  private requestId = 0;
  private callbacks = new Map<number, (result: any, error?: string) => void>();
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

  private async call(method: string, params: any, timeoutMs: number = 180000): Promise<any> {
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
          resolve(result);
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
    return this.call("chat", { message, history }, 60000);  // 60s for chat
  }

  async normalizeTask(history: ChatMessage[], files: string[]): Promise<string> {
    return this.call("normalize_task", { history, files }, 60000);  // 60s
  }

  async execute(task: string, files: Record<string, string>): Promise<string> {
    return this.call("execute", { task, files }, 180000);  // 3min for code generation
  }

  async reviewDiff(task: string, diff: string): Promise<string> {
    return this.call("review", { task, diff }, 60000);  // 60s for review
  }

  // Legacy method for backwards compatibility
  async send(message: string, onReply: (text: string) => void) {
    try {
      const result = await this.chat(message, []);
      onReply(result);
    } catch (e: any) {
      onReply(`Error: ${e.message}`);
    }
  }

  dispose() {
    this.proc.kill();
  }
}
