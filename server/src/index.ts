import { Elysia } from "elysia";
import { join } from "path";

// ========================================
// Types
// ========================================

interface WebSocketData {
  id: string;
}

// Elysia WebSocket type
type ElysiaWebSocket = any; // Using any for Elysia's wrapped WebSocket

interface ParsedMessage {
  request_id?: string;
  result?: {
    screenshot?: string;
    url?: string;
    [key: string]: any;
  };
  [key: string]: any;
}

interface ResponseQueue {
  promise: Promise<ParsedMessage>;
  resolve: (value: ParsedMessage) => void;
  reject: (reason?: any) => void;
  timeout: NodeJS.Timeout;
}

// ========================================
// Global State
// ========================================

const clientList: ElysiaWebSocket[] = [];
const responseQueues = new Map<string, ResponseQueue>();

// ========================================
// Configuration
// ========================================

const TIMEOUT_MS = 300000; // 5 minutes
const PORT = 9999;
const SCREENSHOTS_DIR = "./screenshots";

// ========================================
// Helper Functions
// ========================================

function generateUUID(): string {
  return crypto.randomUUID();
}

function createTimestamp(): string {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace("T", "_")
    .split(".")[0];
}

function removeClient(ws: ElysiaWebSocket): void {
  const index = clientList.indexOf(ws);
  if (index > -1) {
    clientList.splice(index, 1);
  }
}

function createResponseQueue(requestId: string): Promise<ParsedMessage> {
  let resolveResponse: (value: ParsedMessage) => void;
  let rejectResponse: (reason?: any) => void;

  const responsePromise = new Promise<ParsedMessage>((resolve, reject) => {
    resolveResponse = resolve;
    rejectResponse = reject;
  });

  const timeout = setTimeout(() => {
    responseQueues.delete(requestId);
    rejectResponse(new Error("Request timed out"));
  }, TIMEOUT_MS);

  responseQueues.set(requestId, {
    promise: responsePromise,
    resolve: resolveResponse!,
    reject: rejectResponse!,
    timeout,
  });

  return responsePromise;
}

function cleanupResponseQueue(requestId: string): void {
  const queue = responseQueues.get(requestId);
  if (queue) {
    clearTimeout(queue.timeout);
    responseQueues.delete(requestId);
  }
}

async function broadcastToClients(message: object): Promise<number> {
  let successfulSend = 0;
  const clientsToRemove: ElysiaWebSocket[] = [];

  for (const client of clientList) {
    try {
      client.send(JSON.stringify(message));
      successfulSend++;
    } catch (error) {
      console.log("Error sending to client:", error);
      clientsToRemove.push(client);
    }
  }

  // Remove failed clients
  for (const client of clientsToRemove) {
    removeClient(client);
  }

  return successfulSend;
}

// ========================================
// Ensure Screenshots Directory Exists
// ========================================

async function ensureScreenshotsDir(): Promise<void> {
  try {
    await Bun.write(join(SCREENSHOTS_DIR, ".gitkeep"), "");
  } catch (error) {
    // Directory might already exist, that's fine
  }
}

ensureScreenshotsDir();

// ========================================
// Elysia App
// ========================================

const app = new Elysia()
  // ========================================
  // WebSocket Route
  // ========================================
  .ws("/ws", {
    open(ws) {
      console.log("WebSocket client connected");
      clientList.push(ws);
    },

    message(ws, message) {
      try {
        const parsedData: ParsedMessage =
          typeof message === "string" ? JSON.parse(message) : message;

        if (parsedData.request_id) {
          const requestId = parsedData.request_id;
          const responseQueue = responseQueues.get(requestId);

          if (responseQueue) {
            cleanupResponseQueue(requestId);
            responseQueue.resolve(parsedData);
          }
        }
      } catch (e) {
        console.error("Error processing WebSocket message:", e);
      }
    },

    close(ws) {
      console.log("WebSocket client disconnected");
      removeClient(ws);
    },
  })

  // ========================================
  // POST /fetch - Extract HTML data
  // ========================================
  .post("/fetch", async ({ body, set }) => {
    console.log("Extracting data");

    const { url } = body as { url: string };

    if (!url) {
      set.status = 400;
      return { error: "URL is required" };
    }

    const requestId = generateUUID();
    const responsePromise = createResponseQueue(requestId);

    console.log("Sending to clients");
    const successfulSend = await broadcastToClients({
      type: "extractHtml",
      url,
      request_id: requestId,
    });

    console.log(`Successfully sent to ${successfulSend} clients`);

    if (successfulSend === 0) {
      cleanupResponseQueue(requestId);
      set.status = 500;
      return { error: "No client available" };
    }

    console.log(`Waiting for data for request ${requestId}`);

    try {
      const parsedData = await responsePromise;
      return parsedData.result;
    } catch (error) {
      if (error instanceof Error && error.message === "Request timed out") {
        set.status = 504;
        return { error: "Request timed out" };
      }
      throw error;
    }
  })

  // ========================================
  // POST /screenshot - Capture screenshot
  // ========================================
  .post("/screenshot", async ({ body, set }) => {
    console.log("Taking screenshot");

    const { url } = body as { url: string };

    if (!url) {
      set.status = 400;
      return { error: "URL is required" };
    }

    const requestId = generateUUID();
    const responsePromise = createResponseQueue(requestId);

    console.log("Sending screenshot request to clients");
    const successfulSend = await broadcastToClients({
      type: "captureScreenshot",
      url,
      request_id: requestId,
    });

    console.log(`Successfully sent to ${successfulSend} clients`);

    if (successfulSend === 0) {
      cleanupResponseQueue(requestId);
      set.status = 500;
      return { error: "No client available" };
    }

    console.log(`Waiting for screenshot data for request ${requestId}`);

    try {
      const parsedData = await responsePromise;
      const result = parsedData.result || {};

      if (!result.screenshot) {
        set.status = 500;
        return { error: "No screenshot data received" };
      }

      // Generate filename
      const timestamp = createTimestamp();
      const filename = `screenshot_${timestamp}_${requestId.slice(0, 8)}.png`;
      const filepath = join(SCREENSHOTS_DIR, filename);

      try {
        // Remove data:image/png;base64, prefix if present
        let imageData = result.screenshot;
        if (imageData.startsWith("data:image")) {
          imageData = imageData.split(",")[1];
        }

        // Decode base64 and save
        const buffer = Buffer.from(imageData, "base64");
        await Bun.write(filepath, buffer);

        return {
          success: true,
          screenshot_path: filepath,
          filename,
          url: result.url || url,
        };
      } catch (e) {
        console.error("Failed to save screenshot:", e);
        set.status = 500;
        return {
          error: `Failed to save screenshot: ${e instanceof Error ? e.message : String(e)}`,
        };
      }
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === "Screenshot request timed out"
      ) {
        set.status = 504;
        return { error: "Screenshot request timed out" };
      }
      throw error;
    }
  })

  // ========================================
  // GET /screenshot/:filename - Get screenshot file
  // ========================================
  .get("/screenshot/:filename", async ({ params, set }) => {
    const { filename } = params;

    try {
      const screenshotPath = join(SCREENSHOTS_DIR, filename);
      const file = Bun.file(screenshotPath);

      if (!(await file.exists())) {
        set.status = 404;
        return { error: "Screenshot not found" };
      }

      return file;
    } catch (e) {
      console.error("Failed to retrieve screenshot:", e);
      set.status = 500;
      return {
        error: `Failed to retrieve screenshot: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
  })

  // ========================================
  // GET /screenshots - List all screenshots
  // ========================================
  .get("/screenshots", async ({ set }) => {
    try {
      const dir = Bun.file(SCREENSHOTS_DIR);

      if (!(await dir.exists())) {
        return { screenshots: [] };
      }

      const glob = new Bun.Glob("*.png");
      const screenshots = [];

      for await (const filename of glob.scan(SCREENSHOTS_DIR)) {
        const filepath = join(SCREENSHOTS_DIR, filename);
        const file = Bun.file(filepath);
        const stats = await file.stat();

        screenshots.push({
          filename,
          created: stats.ctime.toISOString(),
          size: stats.size,
        });
      }

      // Sort by creation time, newest first
      screenshots.sort((a, b) => {
        return new Date(b.created).getTime() - new Date(a.created).getTime();
      });

      return { screenshots };
    } catch (e) {
      console.error("Failed to list screenshots:", e);
      set.status = 500;
      return {
        error: `Failed to list screenshots: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
  })

  .listen(PORT);

console.log(
  `🦊 Elysia is running at ${app.server?.hostname}:${app.server?.port}`,
);
