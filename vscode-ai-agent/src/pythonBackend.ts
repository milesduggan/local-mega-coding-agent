import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as readline from "readline";

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | null;
  result?: unknown;
  error?: string | null;
}

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
};

export class PythonBackend {
  private process: ChildProcess | null = null;
  private requestId = 0;
  private pendingRequests: Map<number, PendingRequest> = new Map();
  private pythonPath: string;
  private scriptPath: string;
  private ready = false;
  private readyPromise: Promise<void>;
  private readyResolve: (() => void) | null = null;

  constructor(pythonPath: string, projectRoot: string) {
    this.pythonPath = pythonPath;
    this.scriptPath = path.join(
      projectRoot,
      "scripts",
      "backend",
      "wrapper.py"
    );

    this.readyPromise = new Promise((resolve) => {
      this.readyResolve = resolve;
    });
  }

  async start(): Promise<void> {
    if (this.process) {
      return;
    }

    this.process = spawn(this.pythonPath, ["-u", this.scriptPath], {
      cwd: path.dirname(path.dirname(this.scriptPath)),
      stdio: ["pipe", "pipe", "pipe"],
    });

    if (!this.process.stdout || !this.process.stdin) {
      throw new Error("Failed to create subprocess pipes");
    }

    const rl = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity,
    });

    rl.on("line", (line) => {
      this.handleResponse(line);
    });

    this.process.stderr?.on("data", (data) => {
      console.error(`[Python Backend Error]: ${data}`);
    });

    this.process.on("close", (code) => {
      console.log(`Python backend exited with code ${code}`);
      this.process = null;
      this.ready = false;

      // Reject all pending requests
      for (const [id, pending] of this.pendingRequests) {
        clearTimeout(pending.timeout);
        pending.reject(new Error("Backend process terminated"));
        this.pendingRequests.delete(id);
      }
    });

    this.process.on("error", (err) => {
      console.error(`Failed to start Python backend: ${err}`);
    });

    // Wait for ready signal
    await this.readyPromise;
  }

  private handleResponse(line: string): void {
    try {
      const response: JsonRpcResponse = JSON.parse(line);

      // Check for ready signal
      if (response.id === null && response.result === "ready") {
        this.ready = true;
        this.readyResolve?.();
        return;
      }

      if (response.id === null) {
        // Notification or error without id
        if (response.error) {
          console.error(`[Backend Error]: ${response.error}`);
        }
        return;
      }

      const pending = this.pendingRequests.get(response.id);
      if (!pending) {
        console.warn(`Received response for unknown request id: ${response.id}`);
        return;
      }

      clearTimeout(pending.timeout);
      this.pendingRequests.delete(response.id);

      if (response.error) {
        pending.reject(new Error(response.error));
      } else {
        pending.resolve(response.result);
      }
    } catch (e) {
      console.error(`Failed to parse backend response: ${line}`);
    }
  }

  async sendRequest(
    method: string,
    params: Record<string, unknown>,
    timeoutMs = 120000
  ): Promise<unknown> {
    if (!this.process || !this.process.stdin) {
      throw new Error("Backend not started");
    }

    if (!this.ready) {
      await this.readyPromise;
    }

    const id = ++this.requestId;
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id,
      method,
      params,
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Request timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      this.pendingRequests.set(id, { resolve, reject, timeout });

      const json = JSON.stringify(request) + "\n";
      this.process!.stdin!.write(json);
    });
  }

  async chat(
    message: string,
    history: Array<{ role: string; content: string }>
  ): Promise<string> {
    const result = await this.sendRequest("chat", { message, history });
    return result as string;
  }

  async execute(
    task: string,
    files: Record<string, string>
  ): Promise<string> {
    const result = await this.sendRequest("execute", { task, files });
    return result as string;
  }

  async review(task: string, diff: string): Promise<string> {
    const result = await this.sendRequest("review", { task, diff });
    return result as string;
  }

  async normalizeTask(
    history: Array<{ role: string; content: string }>
  ): Promise<string> {
    const result = await this.sendRequest("normalize_task", { history });
    return result as string;
  }

  async ping(): Promise<string> {
    const result = await this.sendRequest("ping", {}, 5000);
    return result as string;
  }

  stop(): void {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }

  isRunning(): boolean {
    return this.process !== null && this.ready;
  }
}
