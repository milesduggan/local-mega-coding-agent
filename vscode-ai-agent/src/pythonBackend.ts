import * as vscode from "vscode";
import { spawn, ChildProcess } from "child_process";
import * as path from "path";

export class PythonBackend {
  private proc: ChildProcess;
  private buffer = "";
  private requestId = 0;
  private callbacks = new Map<number, (result: any, error?: string) => void>();
  private ready = false;
  private readyPromise: Promise<void>;

  constructor(pythonPath: string, extensionPath: string) {
    // wrapper.py is in the extension's parent directory (local-ai-agent project root)
    const projectRoot = path.resolve(extensionPath, "..");
    const wrapperPath = path.join(projectRoot, "scripts", "backend", "wrapper.py");

    this.proc = spawn(pythonPath, [wrapperPath], {
      cwd: projectRoot,
      stdio: ["pipe", "pipe", "pipe"]
    });

    this.readyPromise = new Promise((resolve) => {
      const onReady = (data: Buffer) => {
        const text = data.toString();
        if (text.includes('"result":"ready"')) {
          this.ready = true;
          resolve();
        }
      };
      this.proc.stdout?.once("data", onReady);
    });

    this.proc.stdout?.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      this.processBuffer();
    });

    this.proc.stderr?.on("data", (data: Buffer) => {
      console.error("Python backend error:", data.toString());
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

  async send(message: string, onReply: (text: string) => void) {
    await this.readyPromise;

    const id = ++this.requestId;
    this.callbacks.set(id, (result, error) => {
      onReply(error || result);
    });

    const request = {
      jsonrpc: "2.0",
      id,
      method: "chat",
      params: { message, history: [] }
    };

    this.proc.stdin?.write(JSON.stringify(request) + "\n");
  }

  dispose() {
    this.proc.kill();
  }
}
