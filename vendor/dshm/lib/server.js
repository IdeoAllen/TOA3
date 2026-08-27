import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";
import { loadStore, setSessionArchived } from "./store.js";
import { statusSnapshot, goalInfo, sessionUri, resolveSession, WEB_URL, renderMarkdown } from "./commands.js";
import { searchAll, trendSeries, transcriptOfSession } from "./logs.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = readFileSync(join(__dirname, "web", "index.html"), "utf8");

function shortId(id) {
  return id ? id.replace(/^session-/, "").slice(0, 8) : "";
}

function send(res, code, body, contentType = "application/json; charset=utf-8") {
  res.writeHead(code, {
    "content-type": contentType,
    "cache-control": "no-store",
  });
  res.end(typeof body === "string" ? body : JSON.stringify(body, null, 2));
}

function overview(home) {
  const store = loadStore(home);
  const snap = statusSnapshot(store);
  const sessions = store.sessions.map((s) => ({
    id: s.id,
    shortId: shortId(s.id),
    title: s.title,
    workspace: s.wsTitle,
    cwd: s.cwd,
    turns: s.turns,
    steps: s.steps,
    inputTokens: s.inputTokens,
    outputTokens: s.outputTokens,
    cacheReadTokens: s.cacheReadTokens,
    contextPct: s.contextPct,
    contextUsed: s.contextUsed,
    contextWindow: s.contextWindow,
    archived: s.archived,
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
    goal: goalInfo(s.goal),
  }));
  const workspaces = store.workspaces.map((w) => ({
    id: w.id,
    title: w.title,
    path: w.path,
    sessions: w.sessionIds.length,
    createdAt: w.createdAt,
    updatedAt: w.updatedAt,
  }));
  // 保留 snap 里的计数（workspaces/sessions 是数字），数组另起键名避免覆盖。
  return { ...snap, sessionList: sessions, workspaceList: workspaces };
}

function detail(store, id) {
  const r = resolveSession(store, id);
  if (!r) return null;
  if (r.ambiguous) return { ambiguous: r.ambiguous.map((s) => s.id) };
  const s = r;
  return {
    id: s.id,
    shortId: shortId(s.id),
    title: s.title,
    workspace: s.wsTitle,
    cwd: s.cwd,
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
    archived: s.archived,
    stats: s.stats,
    tokenUsage: s.tokenUsage,
    contextPressure: s.contextPressure,
    contextBreakdown: s.contextBreakdown,
    permissions: s.permissions,
    goal: goalInfo(s.goal),
    todos: s.todos,
    plan: s.plan,
    resumeUri: sessionUri(s.id),
    webUrl: WEB_URL(),
  };
}

export function startServer(home, opts = {}) {
  const host = opts.host ?? "127.0.0.1";
  const port = opts.port ?? 8787;
  const server = createServer((req, res) => {
    const u = new URL(req.url, `http://${host}:${port}`);
    const path = u.pathname;
    try {
      if (req.method === "GET" && path === "/") {
        send(res, 200, INDEX_HTML, "text/html; charset=utf-8");
        return;
      }
      if (req.method === "GET" && path === "/api/overview") {
        send(res, 200, overview(home));
        return;
      }
      if (req.method === "GET" && path === "/api/session") {
        const d = detail(loadStore(home), u.searchParams.get("id"));
        if (!d) {
          send(res, 404, { error: "session not found" });
          return;
        }
        send(res, 200, d);
        return;
      }
      if (req.method === "GET" && path === "/api/search") {
        const q = u.searchParams.get("q") ?? "";
        const results = searchAll(home, q, {
          limit: 50,
          includeArchived: u.searchParams.get("all") === "true",
          includeReasoning: u.searchParams.get("reasoning") === "true",
        });
        send(res, 200, results);
        return;
      }
      if (req.method === "GET" && path === "/api/trend") {
        const r = resolveSession(loadStore(home), u.searchParams.get("id"));
        if (!r || r.ambiguous) {
          send(res, 404, { error: "session not found" });
          return;
        }
        const series = trendSeries(home, r.id);
        send(res, 200, series ?? []);
        return;
      }
      if (req.method === "GET" && path === "/api/export") {
        const id = u.searchParams.get("id");
        const format = u.searchParams.get("format") ?? "md";
        const r = resolveSession(loadStore(home), id);
        if (!r || r.ambiguous) {
          send(res, 404, { error: "session not found" });
          return;
        }
        const t = transcriptOfSession(home, r.id);
        if (!t) {
          send(res, 404, { error: "no log" });
          return;
        }
        let body;
        let type;
        let filename;
        if (format === "json") {
          body =
            JSON.stringify(
              { sessionId: r.id, title: t.title ?? r.title, workspace: r.wsTitle, cwd: r.cwd, header: t.header, messages: t.messages },
              null,
              2
            ) + "\n";
          type = "application/json; charset=utf-8";
          filename = r.id + ".json";
        } else {
          body = renderMarkdown(r, t);
          type = "text/markdown; charset=utf-8";
          filename = r.id + ".md";
        }
        res.writeHead(200, {
          "content-type": type,
          "content-disposition": `attachment; filename="${filename}"`,
          "cache-control": "no-store",
        });
        res.end(body);
        return;
      }
      if (req.method === "POST" && path === "/api/archive") {
        const id = u.searchParams.get("id");
        const archived = u.searchParams.get("archived") === "true";
        const r = resolveSession(loadStore(home), id);
        if (!r || r.ambiguous) {
          send(res, 404, { error: "session not found or ambiguous" });
          return;
        }
        setSessionArchived(home, r.id, archived);
        send(res, 200, { ok: true, id: r.id, archived });
        return;
      }
      send(res, 404, { error: "not found" });
    } catch (e) {
      send(res, 500, { error: e.message });
    }
  });
  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(port, host, () => {
      resolve({ url: `http://${host}:${port}`, server });
    });
  });
}
