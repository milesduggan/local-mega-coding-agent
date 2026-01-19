"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.PythonBackend = void 0;
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const readline = __importStar(require("readline"));
class PythonBackend {
    process = null;
    requestId = 0;
    pendingRequests = new Map();
    pythonPath;
    scriptPath;
    ready = false;
    readyPromise;
    readyResolve = null;
    constructor(pythonPath, projectRoot) {
        this.pythonPath = pythonPath;
        this.scriptPath = path.join(projectRoot, "scripts", "backend", "wrapper.py");
        this.readyPromise = new Promise((resolve) => {
            this.readyResolve = resolve;
        });
    }
    async start() {
        if (this.process) {
            return;
        }
        this.process = (0, child_process_1.spawn)(this.pythonPath, ["-u", this.scriptPath], {
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
    handleResponse(line) {
        try {
            const response = JSON.parse(line);
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
            }
            else {
                pending.resolve(response.result);
            }
        }
        catch (e) {
            console.error(`Failed to parse backend response: ${line}`);
        }
    }
    async sendRequest(method, params, timeoutMs = 120000) {
        if (!this.process || !this.process.stdin) {
            throw new Error("Backend not started");
        }
        if (!this.ready) {
            await this.readyPromise;
        }
        const id = ++this.requestId;
        const request = {
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
            this.process.stdin.write(json);
        });
    }
    async chat(message, history) {
        const result = await this.sendRequest("chat", { message, history });
        return result;
    }
    async execute(task, files) {
        const result = await this.sendRequest("execute", { task, files });
        return result;
    }
    async review(task, diff) {
        const result = await this.sendRequest("review", { task, diff });
        return result;
    }
    async normalizeTask(history) {
        const result = await this.sendRequest("normalize_task", { history });
        return result;
    }
    async ping() {
        const result = await this.sendRequest("ping", {}, 5000);
        return result;
    }
    stop() {
        if (this.process) {
            this.process.kill();
            this.process = null;
        }
    }
    isRunning() {
        return this.process !== null && this.ready;
    }
}
exports.PythonBackend = PythonBackend;
//# sourceMappingURL=pythonBackend.js.map