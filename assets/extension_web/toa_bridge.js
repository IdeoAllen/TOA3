/**
 * TOA 用户扩展 WebView 桥（本地 file:// 页引入本文件 + qrc:///qtwebchannel/qwebchannel.js）
 *
 * 用法:
 *   TOA.ready(function (toa) {
 *     toa.reportStatus('你好', 'success');
 *   });
 */
(function (global) {
  "use strict";

  var _readyQueue = [];
  var _toa = null;

  function flushReady() {
    if (!_toa) return;
    while (_readyQueue.length) {
      try {
        _readyQueue.shift()(_toa);
      } catch (e) {
        console.error("[TOA]", e);
      }
    }
  }

  function initChannel() {
    if (typeof QWebChannel === "undefined" || !global.qt || !global.qt.webChannelTransport) {
      setTimeout(initChannel, 50);
      return;
    }
    new QWebChannel(global.qt.webChannelTransport, function (channel) {
      _toa = channel.objects.toa;
      flushReady();
    });
  }

  global.TOA = {
    ready: function (fn) {
      if (typeof fn !== "function") return;
      if (_toa) {
        fn(_toa);
        return;
      }
      _readyQueue.push(fn);
    },
    /** 解析 themePalette JSON 为对象 */
    parsePalette: function (jsonText) {
      try {
        return JSON.parse(jsonText || "{}");
      } catch (e) {
        return {};
      }
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initChannel);
  } else {
    initChannel();
  }
})(window);
