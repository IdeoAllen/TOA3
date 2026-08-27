#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolveHome } from "../lib/home.js";
import { setColorEnabled, c } from "../lib/format.js";
import { runCommand, helpText, openBrowser } from "../lib/commands.js";
import { runRepl, runTop } from "../lib/repl.js";
import { startServer } from "../lib/server.js";

function readVersion() {
  try {
    const manifest = JSON.parse(
      readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
    );
    return typeof manifest.version === "string" ? manifest.version : "0.0.0";
  } catch {
    return "0.0.0";
  }
}

function parseArgs(argv) {
  const opts = { all: false, json: false, open: false, watch: 2, home: undefined, color: undefined, host: undefined, port: undefined, format: undefined, out: undefined, limit: undefined, reasoning: false };
  const positionals = [];
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === "--home") {
      opts.home = argv[++i];
      continue;
    }
    if (t.startsWith("--home=")) {
      opts.home = t.slice("--home=".length);
      continue;
    }
    if (t === "--format") {
      opts.format = argv[++i];
      continue;
    }
    if (t.startsWith("--format=")) {
      opts.format = t.slice("--format=".length);
      continue;
    }
    if (t === "--out") {
      opts.out = argv[++i];
      continue;
    }
    if (t.startsWith("--out=")) {
      opts.out = t.slice("--out=".length);
      continue;
    }
    if (t === "--limit") {
      opts.limit = Number(argv[++i]) || undefined;
      continue;
    }
    if (t.startsWith("--limit=")) {
      opts.limit = Number(t.slice("--limit=".length)) || undefined;
      continue;
    }
    if (t === "--reasoning") {
      opts.reasoning = true;
      continue;
    }
    if (t === "--host") {
      opts.host = argv[++i];
      continue;
    }
    if (t.startsWith("--host=")) {
      opts.host = t.slice("--host=".length);
      continue;
    }
    if (t === "--port") {
      opts.port = Number(argv[++i]) || undefined;
      continue;
    }
    if (t.startsWith("--port=")) {
      opts.port = Number(t.slice("--port=".length)) || undefined;
      continue;
    }
    if (t === "--watch") {
      opts.watch = Number(argv[++i]) || 2;
      continue;
    }
    if (t.startsWith("--watch=")) {
      opts.watch = Number(t.slice("--watch=".length)) || 2;
      continue;
    }
    if (t === "--json") {
      opts.json = true;
      continue;
    }
    if (t === "--all") {
      opts.all = true;
      continue;
    }
    if (t === "--open") {
      opts.open = true;
      continue;
    }
    if (t === "--no-color") {
      opts.color = false;
      continue;
    }
    if (t === "--color") {
      opts.color = true;
      continue;
    }
    if (t === "-h" || t === "--help") {
      opts.help = true;
      continue;
    }
    if (t === "-V" || t === "--version") {
      opts.version = true;
      continue;
    }
    if (t === "--") {
      positionals.push(...argv.slice(i + 1));
      break;
    }
    if (t.startsWith("-") && t !== "-") {
      throw new Error(`未知选项：${t}`);
    }
    positionals.push(t);
  }
  return { opts, positionals };
}

async function main() {
  const { opts, positionals } = parseArgs(process.argv.slice(2));
  setColorEnabled(opts.color ?? (!!process.stdout.isTTY && !process.env.NO_COLOR));

  if (opts.version) {
    console.log("dshm " + readVersion());
    process.exit(0);
  }
  const { home, source } = resolveHome(process.env, opts);
  if (source === "workbuddy") {
    console.log(c.dim("DSH 主目录（自动发现）：" + home));
  }
  if (opts.help) {
    console.log(helpText());
    process.exit(0);
  }
  if (positionals.length === 0) {
    if (process.stdin.isTTY && process.stdout.isTTY) {
      runRepl(home, opts);
    } else {
      console.log(helpText());
    }
    return;
  }
  try {
    const result = runCommand(home, positionals, opts);
    if (result && result.top) {
      runTop(home, opts);
      return;
    }
    if (result && result.web) {
      const info = await startServer(home, {
        host: opts.host ?? "127.0.0.1",
        port: opts.port ?? 8787,
      });
      console.log(c.green("✓ dshm 管理界面已启动"));
      console.log("  " + c.bold(info.url));
      console.log("  " + c.dim("Ctrl+C 停止"));
      if (opts.open) openBrowser(info.url);
      return; // 服务器保持事件循环存活
    }
    const text = typeof result === "string" ? result : "";
    if (text) console.log(text);
  } catch (e) {
    console.error(c.red("✖ " + e.message));
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(c.red("✖ " + e.message));
  process.exit(1);
});
