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
})();
