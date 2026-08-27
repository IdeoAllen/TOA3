import { readFileSync, existsSync, readdirSync, copyFileSync, mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { zstdDecompressSync } from "node:zlib";
import { loadStore } from "./store.js";

// ---------------------------------------------------------------------------
// 会话日志（session.jsonl.zstd）读取层。Harness 用「一个 header frame + 每批
// append 一个 frame」的 Zstandard 帧拼接存储；Node 的 zstd 只解第一个 frame，
// 因此按 magic 字节切帧后逐个解压。JSONL 内关键事件：
//   - user/message（source.kind === 'user' 为人类输入）
//   - assistant/message（含 data.message.content 与 data.usage 每步 token）
// ---------------------------------------------------------------------------

const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]); // zstd frame magic

/** 解压一个 .jsonl.zstd（或透传 .jsonl）。 */
export function readSessionLog(filePath) {
  const buf = readFileSync(filePath);
  if (!filePath.endsWith(".zstd")) return buf.toString("utf8");
  const offs = [0];
  let i = 4;
  while ((i = buf.indexOf(MAGIC, i)) !== -1) {
    offs.push(i);
    i += 4;
  }
  offs.push(buf.length);
  let out = "";
  for (let k = 0; k < offs.length - 1; k++) {
    out += zstdDecompressSync(buf.subarray(offs[k], offs[k + 1])).toString("utf8");
  }
  return out;
}

/** 在 $DSH_HOME/sessions/<项目目录>/<会话目录>/ 下定位某个会话的日志文件。 */
export function findSessionLog(home, sessionId) {
  const root = join(home, "sessions");
  let projects;
  try {
    projects = readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const proj of projects) {
    if (!proj.isDirectory()) continue;
    const projDir = join(root, proj.name);
    let subs;
    try {
      subs = readdirSync(projDir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const s of subs) {
      if (!s.isDirectory() || s.name !== sessionId) continue;
      const z = join(projDir, s.name, "session.jsonl.zstd");
      if (existsSync(z)) return z;
      const plain = join(projDir, s.name, "session.jsonl");
      if (existsSync(plain)) return plain;
    }
  }
  return null;
}

/** 解压并按行解析为事件数组（损坏行跳过）。 */
export function parseEvents(filePath) {
  const text = readSessionLog(filePath);
  const events = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      events.push(JSON.parse(line));
    } catch {
      /* skip corrupt tail */
    }
  }
  return events;
}

// ---- 文本提取 ----
function blocks(content, type) {
  return Array.isArray(content) ? content.filter((b) => b && b.type === type) : [];
}
function joinBlocks(content, type) {
  return blocks(content, type)
    .map((b) => (typeof b.text === "string" ? b.text : ""))
    .join("\n")
    .trim();
}
function toolCallsOf(content) {
  return blocks(content, "tool-call").map((b) => ({
    id: b.id ?? null,
    name: b.name ?? null,
    arguments: b.arguments ?? b.args ?? b.input ?? null,
  }));
}

/**
 * 把一个会话的事件流折叠成有序的「可读消息」序列（供导出/搜索）。
 */
export function transcript(events) {
  const header = events.find((e) => e.type === "session") ?? null;
  let title = null;
  const messages = [];
  for (const e of events) {
    if (e.type === "session/title" && e.data?.title) title = e.data.title;
    if (e.type === "user/message" && e.data?.source?.kind === "user") {
      const text = joinBlocks(e.data.content, "text");
      if (!text) continue;
      messages.push({ role: "user", time: e.time, text });
    } else if (e.type === "assistant/message") {
      const content = e.data?.message?.content ?? [];
      const text = joinBlocks(content, "text");
      const reasoning = joinBlocks(content, "reasoning");
      const toolCalls = toolCallsOf(content);
      if (!text && !reasoning && toolCalls.length === 0) continue;
      messages.push({
        role: "assistant",
        time: e.time,
        turn: e.data?.turn ?? null,
        step: e.data?.step ?? null,
        text,
        reasoning,
        toolCalls,
        model: e.data?.message?.source?.model ?? null,
        provider: e.data?.message?.source?.provider ?? null,
        usage: e.data?.usage ?? null,
      });
    }
  }
  return { header, title, messages };
}

/** 定位 + 解析 + 折叠某个会话。 */
export function transcriptOfSession(home, sessionId) {
  const path = findSessionLog(home, sessionId);
  if (!path) return null;
  return { path, ...transcript(parseEvents(path)) };
}

/**
 * 跨会话全文搜索。query 大小写不敏感；默认只搜用户与助手文本，
 * `includeReasoning` 时也搜推理内容。返回带上下文片段的命中列表。
 */
export function searchAll(home, query, { limit = 20, includeArchived = false, includeReasoning = false } = {}) {
  const store = loadStore(home);
  const needle = query.toLowerCase();
  const results = [];
  for (const s of store.sessions) {
    if (!includeArchived && s.archived) continue;
    if (results.length >= limit) break;
    const path = findSessionLog(home, s.id);
    if (!path) continue;
    let t;
    try {
      t = transcript(parseEvents(path));
    } catch {
      continue;
    }
    for (const m of t.messages) {
      if (results.length >= limit) break;
      const haystacks = [m.text];
      if (includeReasoning && m.role === "assistant" && m.reasoning) haystacks.push(m.reasoning);
      for (const text of haystacks) {
        if (!text) continue;
        const idx = text.toLowerCase().indexOf(needle);
        if (idx === -1) continue;
        const radius = 90;
        const start = Math.max(0, idx - radius);
        const end = Math.min(text.length, idx + needle.length + radius);
        results.push({
          sessionId: s.id,
          shortId: s.id.replace(/^session-/, "").slice(0, 8),
          workspace: s.wsTitle,
          title: t.title ?? s.title,
          role: m.role,
          time: m.time,
          model: m.model,
          snippet: (start > 0 ? "…" : "") + text.slice(start, end) + (end < text.length ? "…" : ""),
        });
        break;
      }
    }
  }
  return results;
}

/**
 * 某个会话的每步 token 用量时间序列（来自 assistant/message 的 usage）。
 */
export function trendSeries(home, sessionId) {
  const path = findSessionLog(home, sessionId);
  if (!path) return null;
  const events = parseEvents(path);
  const points = [];
  for (const e of events) {
    if (e.type !== "assistant/message") continue;
    const u = e.data?.usage ?? null;
    if (!u) continue;
    points.push({
      time: e.time,
      turn: e.data?.turn ?? null,
      step: e.data?.step ?? null,
      inputTokens: u.inputTokens ?? 0,
      outputTokens: u.outputTokens ?? 0,
      cacheReadTokens: u.cacheReadTokens ?? 0,
      cacheWriteTokens: u.cacheWriteTokens ?? 0,
      reasoningTokens: u.reasoningTokens ?? 0,
    });
  }
  return points;
}
