/* Mobile navigation toggle for the shared site header. Loaded with defer on every page. */
(function () {
  var header = document.querySelector(".site-header");
  var toggle = header && header.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;

  document.documentElement.classList.add("js");

  function setOpen(open, restoreFocus) {
    header.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open && restoreFocus) toggle.focus();
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  nav.addEventListener("click", function (event) {
    if (event.target.closest("a")) setOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") setOpen(false, true);
  });

  document.addEventListener("click", function (event) {
    if (toggle.getAttribute("aria-expanded") === "true" && !header.contains(event.target)) setOpen(false);
  });

  // Reset when the layout returns to desktop so the panel never stays "open" invisibly.
  var desktop = window.matchMedia("(min-width: 761px)");
  var onChange = function (event) { if (event.matches) setOpen(false); };
  if (desktop.addEventListener) desktop.addEventListener("change", onChange);
  else if (desktop.addListener) desktop.addListener(onChange);
})();
