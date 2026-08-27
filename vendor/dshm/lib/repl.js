import readline from "node:readline";
import { loadStore } from "./store.js";
import { runCommand, renderStatus, openBrowser } from "./commands.js";
import { startServer } from "./server.js";
import { c } from "./format.js";

function splitArgs(s) {
  const out = [];
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let m;
  while ((m = re.exec(s))) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

/** 实时刷新的状态面板（类似 top）。 */
export function runTop(home, opts) {
  const intervalMs = Math.max(500, (opts.watch ?? 2) * 1000);
  const draw = () => {
    try {
      const store = loadStore(home);
      process.stdout.write("\u001b[H\u001b[2J" + renderStatus(store) + "\n");
      process.stdout.write(
        c.dim(`每 ${(intervalMs / 1000).toFixed(1)}s 刷新 · Ctrl+C 退出`) + "\n"
      );
    } catch (e) {
      process.stdout.write(c.red("渲染失败: " + e.message) + "\n");
    }
  };
  process.stdout.write("\u001b[?25l"); // 隐藏光标
  draw();
  const timer = setInterval(draw, intervalMs);
  const onSig = () => {
    clearInterval(timer);
    process.stdout.write("\u001b[?25h\n");
    process.exit(0);
  };
  process.on("SIGINT", onSig);
  process.on("exit", () => process.stdout.write("\u001b[?25h"));
}

/** 交互式管理终端（REPL）。 */
export function runRepl(home, opts) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: c.bold("dshm") + "> ",
  });
  console.log(c.dim("DeepSeek Harness 管理终端 —— 输入 help 查看命令，quit 退出\n"));
  rl.prompt();
  rl.on("line", async (line) => {
    const tokens = splitArgs(line.trim());
    if (!tokens.length) {
      rl.prompt();
      return;
    }
    const cmd = tokens[0];
    if (cmd === "quit" || cmd === "exit" || cmd === "q") {
      rl.close();
      return;
    }
    if (cmd === "clear" || cmd === "cls") {
      process.stdout.write("\u001b[2J\u001b[H");
      rl.prompt();
      return;
    }
    try {
      const result = runCommand(home, tokens, opts);
      if (result && result.top) {
        runTop(home, opts);
        return; // top 独占终端，直到 Ctrl+C
      }
      if (result && result.web) {
        const info = await startServer(home, {
          host: opts.host ?? "127.0.0.1",
          port: opts.port ?? 8787,
        });
        console.log(c.green("✓ 管理界面已启动：") + c.bold(info.url));
        if (opts.open) openBrowser(info.url);
        rl.prompt();
        return;
      }
      const text = typeof result === "string" ? result : "";
      if (text) console.log(text);
    } catch (e) {
      console.log(c.red("✖ " + e.message));
    }
    rl.prompt();
  });
  rl.on("close", () => {
    console.log(c.dim("\n再见。"));
  });
}
