/* 网页扩展示例 · 用户扩展 Web 面入口 */
(function () {
  "use strict";

  function render(root, toa) {
    root.innerHTML = ""
      + "<p>扩展 id：<code>" + toa.pluginId() + "</code></p>"
      + "<p>数据目录：<code>" + toa.dataDir() + "</code></p>"
      + "<button type=\"button\" id=\"btn-hello\">打个招呼</button>";
    document.getElementById("btn-hello").onclick = function () {
      toa.reportStatus("你好 · 网页扩展示例 网页扩展已就绪", "success");
    };
  }

  TOA.ready(function (toa) {
    var root = document.getElementById("app");
    if (!root) return;
    render(root, toa);
    var pal = TOA.parsePalette(toa.themePalette());
    if (pal.background) {
      document.body.style.background = pal.background;
      document.body.style.color = pal.text_primary || "#ccc";
    }
  });
})();
