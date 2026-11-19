/* 渔业声学监测科研分析系统 · 轻量交互
   只做不干扰数据驱动视图的渐进增强；所有视觉表达优先交由 CSS 与布局完成。 */
(function () {
  "use strict";

  // 反馈条：出现后一段时间自动收起，避免长期占据视觉空间
  document.querySelectorAll(".flash").forEach(function (el) {
    window.setTimeout(function () {
      el.style.transition = "opacity .4s ease";
      el.style.opacity = "0";
      window.setTimeout(function () { el.style.display = "none"; }, 420);
    }, 7000);
  });

  // 口径收纳区：记住展开状态，避免反复查看时重复点击
  var notes = document.querySelectorAll("details.notes");
  if (notes.length && window.localStorage) {
    notes.forEach(function (d, i) {
      var key = "fishery:notes:" + i + ":" + location.pathname;
      try {
        if (window.localStorage.getItem(key) === "open") d.open = true;
        d.addEventListener("toggle", function () {
          window.localStorage.setItem(key, d.open ? "open" : "closed");
        });
      } catch (e) { /* 隐私模式下忽略 */ }
    });
  }

  // 窄屏横向导航：把当前项滚入可见区域
  var active = document.querySelector(".nav-item.active");
  if (active && active.scrollIntoView) {
    try { active.scrollIntoView({ block: "nearest", inline: "center" }); } catch (e) {}
  }

  // 拖放上传：所有带 data-upload-zone 的区域共用同一套交互，拖入即上传
  function isFileDrag(e) {
    var types = e.dataTransfer && e.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, "Files") !== -1;
  }

  document.addEventListener("dragover", function (e) {
    if (isFileDrag(e)) e.preventDefault();
  });
  document.addEventListener("drop", function (e) {
    if (!isFileDrag(e)) return;
    var inZone = e.target && e.target.closest && e.target.closest("[data-upload-zone]");
    if (!inZone) e.preventDefault();
  });

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function submitUploadZone(zone) {
    var form = zone.closest("form");
    if (!form) return;
    var action = zone.getAttribute("data-submit-action") || "";
    var buttons = Array.prototype.slice.call(form.querySelectorAll("button[type=submit]"));
    var button = action
      ? buttons.filter(function (b) { return b.getAttribute("name") === "action" && b.value === action; })[0]
      : buttons[0];
    if (button && form.requestSubmit) {
      form.requestSubmit(button);
      return;
    }
    if (button && button.getAttribute("name")) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = button.getAttribute("name");
      hidden.value = button.value;
      form.appendChild(hidden);
    }
    form.submit();
  }

  document.querySelectorAll("[data-upload-zone]").forEach(function (zone) {
    var input = zone.querySelector('input[type="file"]');
    var meta = zone.querySelector("[data-upload-status]");
    if (!input) return;

    function setStatus(text, selected) {
      if (!meta) return;
      meta.textContent = text;
      meta.classList.toggle("is-selected", !!selected);
    }

    function accepts(file) {
      var raw = zone.getAttribute("data-accept") || "";
      var tokens = raw.split(",").map(function (s) { return s.trim().toLowerCase(); }).filter(Boolean);
      if (!tokens.length) return true;
      var name = (file.name || "").toLowerCase();
      var type = (file.type || "").toLowerCase();
      return tokens.some(function (token) {
        if (token.charAt(0) === ".") return name.indexOf(token) === name.length - token.length;
        if (token.indexOf("/") !== -1 && token.slice(-2) === "/*") return type.indexOf(token.slice(0, -1)) === 0;
        return type === token || name.indexOf(token) === name.length - token.length;
      });
    }

    function applyFiles(files) {
      try {
        input.files = files;
        return true;
      } catch (e) {
        try {
          var transfer = new DataTransfer();
          Array.prototype.forEach.call(files, function (file) { transfer.items.add(file); });
          input.files = transfer.files;
          return true;
        } catch (ignored) {
          return false;
        }
      }
    }

    function describe(files) {
      if (!files || !files.length) return "拖入文件，或点击选择";
      if (files.length === 1) return files[0].name + " · " + formatSize(files[0].size);
      return "已选择 " + files.length + " 个文件（仅处理第一个）";
    }

    zone.addEventListener("dragenter", function (e) {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      zone.classList.add("is-dragging");
    });
    zone.addEventListener("dragover", function (e) {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      zone.classList.add("is-dragging");
    });
    zone.addEventListener("dragleave", function () {
      zone.classList.remove("is-dragging");
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("is-dragging");
      zone.classList.remove("is-invalid");
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      if (!accepts(files[0])) {
        zone.classList.add("is-invalid");
        setStatus("文件类型不支持：" + files[0].name, false);
        return;
      }
      if (!applyFiles(files)) {
        zone.classList.add("is-invalid");
        setStatus("当前浏览器不支持自动填入，请点击区域选择文件", false);
        return;
      }
      setStatus(describe(files), true);
      if (zone.hasAttribute("data-auto-submit")) {
        window.setTimeout(function () { submitUploadZone(zone); }, 80);
      }
    });

    input.addEventListener("change", function () {
      zone.classList.remove("is-invalid");
      setStatus(describe(input.files), input.files && input.files.length > 0);
    });
    zone.addEventListener("click", function (e) {
      if (e.target === input) return;
      input.click();
    });
    zone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
  });
})();
