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
class PythonBackend {
    proc;
    buffer = "";
    requestId = 0;
    callbacks = new Map();
    ready = false;
    readyPromise;
    constructor(pythonPath, extensionPath) {
        // wrapper.py is in the extension's parent directory (local-ai-agent project root)
        const projectRoot = path.resolve(extensionPath, "..");
        const wrapperPath = path.join(projectRoot, "scripts", "backend", "wrapper.py");
        this.proc = (0, child_process_1.spawn)(pythonPath, [wrapperPath], {
            cwd: projectRoot,
            stdio: ["pipe", "pipe", "pipe"]
        });
        this.readyPromise = new Promise((resolve) => {
            const onReady = (data) => {
                const text = data.toString();
                if (text.includes('"result":"ready"')) {
                    this.ready = true;
                    resolve();
                }
            };
            this.proc.stdout?.once("data", onReady);
        });
        this.proc.stdout?.on("data", (data) => {
            this.buffer += data.toString();
            this.processBuffer();
        });
        this.proc.stderr?.on("data", (data) => {
            console.error("Python backend error:", data.toString());
        });
    }
    processBuffer() {
        const lines = this.buffer.split("\n");
        this.buffer = lines.pop() || "";
        for (const line of lines) {
            if (!line.trim())
                continue;
            try {
                const msg = JSON.parse(line);
                if (msg.id !== null && this.callbacks.has(msg.id)) {
                    const cb = this.callbacks.get(msg.id);
                    this.callbacks.delete(msg.id);
                    cb(msg.result, msg.error);
                }
            }
            catch (e) {
                console.error("Failed to parse JSON:", line);
            }
        }
    }
    async send(message, onReply) {
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
exports.PythonBackend = PythonBackend;
//# sourceMappingURL=pythonBackend.js.map