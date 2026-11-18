    function applyTheme(theme) {
      document.documentElement.setAttribute("data-theme", theme);
      document.getElementById("theme-label").textContent = theme === "dark" ? "Light mode" : "Dark mode";
    }
    applyTheme(document.documentElement.getAttribute("data-theme") || "light");

    document.getElementById("theme-toggle").addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") || "light";
      var next = current === "light" ? "dark" : "light";
      localStorage.setItem("aistore-theme", next);
      applyTheme(next);
    });

    var datacenterRain = (function () {
      var canvas = document.getElementById("datacenter-rain");
      var ctx = canvas.getContext("2d");
      var rafId = null;
      var columns = [];
      var chars = "01ABCDEF";
      var fontSize = 16;
      var w, h, dpr;

      function resize() {
        dpr = Math.min(window.devicePixelRatio || 1, 1.6);
        w = window.innerWidth;
        h = window.innerHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        var slots = Math.ceil(w / fontSize);
        columns = [];
        // Sparse: only ~1 in 5 slots gets an active falling glyph — texture, not a wall of text.
        for (var i = 0; i < slots; i++) {
          if (Math.random() < 0.2) {
            columns.push({ x: i * fontSize, y: Math.random() * -h, speed: 0.35 + Math.random() * 0.5, alpha: 0.1 + Math.random() * 0.14 });
          }
        }
      }

      function tick() {
        // Trailing fade instead of a hard clear — soft streaks, not a flat flicker.
        ctx.fillStyle = "rgba(3, 8, 5, 0.16)";
        ctx.fillRect(0, 0, w, h);
        ctx.font = fontSize + "px ui-monospace, Menlo, monospace";
        for (var i = 0; i < columns.length; i++) {
          var c = columns[i];
          var ch = chars[Math.floor(Math.random() * chars.length)];
          ctx.fillStyle = "rgba(57, 255, 143, " + c.alpha + ")";
          ctx.fillText(ch, c.x, c.y);
          c.y += c.speed * fontSize;
          if (c.y > h + fontSize) { c.y = Math.random() * -60; c.alpha = 0.1 + Math.random() * 0.14; }
        }
        rafId = requestAnimationFrame(tick);
      }

      var resizeTimer;
      function onResize() { clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 200); }

      return {
        start: function () {
          if (rafId || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
          resize();
          window.addEventListener("resize", onResize);
          document.addEventListener("visibilitychange", visHandler);
          rafId = requestAnimationFrame(tick);
        },
        stop: function () {
          if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
          window.removeEventListener("resize", onResize);
          document.removeEventListener("visibilitychange", visHandler);
          ctx.clearRect(0, 0, w || canvas.width, h || canvas.height);
        }
      };

      function visHandler() {
        if (document.hidden) { if (rafId) { cancelAnimationFrame(rafId); rafId = null; } }
        else if (document.documentElement.getAttribute("data-datacenter") === "on") { rafId = requestAnimationFrame(tick); }
      }
    })();

    function playBootSequence() {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      var lines = [
        "INITIALIZING GPU FABRIC...",
        "CHECKING POSTGRES CONNECTION...",
        "LOADING MODEL ADVISOR...",
        "CALIBRATING POWER TELEMETRY...",
        "DATACENTER MODE ONLINE"
      ];
      var overlay = document.createElement("div");
      overlay.className = "boot-sequence";
      overlay.setAttribute("aria-live", "polite");
      document.body.appendChild(overlay);

      lines.forEach(function (line, i) {
        setTimeout(function () {
          var el = document.createElement("div");
          el.className = "boot-line" + (i === lines.length - 1 ? " boot-line-final" : "");
          el.textContent = "> " + line;
          overlay.appendChild(el);
        }, i * 380);
      });

      setTimeout(function () {
        overlay.classList.add("boot-fade-out");
        setTimeout(function () { overlay.remove(); }, 500);
      }, lines.length * 380 + 700);
    }

    function applyDatacenterMode(on, isUserToggle) {
      document.documentElement.setAttribute("data-datacenter", on ? "on" : "off");
      var btn = document.getElementById("datacenter-toggle");
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      document.getElementById("datacenter-label").textContent = on ? "Datacenter mode: on" : "Datacenter mode";
      if (on) datacenterRain.start(); else datacenterRain.stop();
      if (on && isUserToggle) playBootSequence();
    }
    applyDatacenterMode(localStorage.getItem("aistore-datacenter") === "on", false);

    document.getElementById("datacenter-toggle").addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-datacenter") !== "on";
      localStorage.setItem("aistore-datacenter", next ? "on" : "off");
      applyDatacenterMode(next, true);
    });

    // ---- Explain Simply mascot: a small click-through cat, only active in Explain Simply mode ----
    // Defined BEFORE applySimpleMode below, since applySimpleMode calls mascotEnable/mascotDisable
    // synchronously on page load — if this ran after, the first call would throw (function not
    // yet assigned) and abort every remaining top-level statement in this script block.
    var mascotEnable, mascotDisable;
    (function () {
      var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var isMobile = window.matchMedia("(max-width: 700px)").matches;
      var catEl = null, ballEl = null;
      var timers = [];
      var running = false;
      var pos = { x: 0, y: 0 };
      var fleeCooldown = 0;

      function clearTimers() { timers.forEach(clearTimeout); timers = []; }
      function after(ms, fn) { var id = setTimeout(fn, ms); timers.push(id); return id; }
      // Long, randomized pause between activities — the cat mostly just sits there and only
      // moves roughly once a minute on its own (or immediately if a visitor's cursor lands on
      // it), so it reads as a quiet helper, never a distraction.
      function idleGap() { return 60000 + Math.random() * 15000; }
      function highlightExplain(el, on) { if (el) el.classList.toggle("mascot-pointed", on); }

      function bounds() {
        var header = document.querySelector("header");
        var headerH = header ? header.getBoundingClientRect().height : 70;
        return {
          minX: 16,
          maxX: Math.max(16, window.innerWidth - 76),
          minY: headerH + 20,
          maxY: Math.max(headerH + 40, window.innerHeight - 110)
        };
      }

      function randomPoint() {
        var b = bounds();
        return {
          x: b.minX + Math.random() * (b.maxX - b.minX),
          y: b.minY + Math.random() * (b.maxY - b.minY)
        };
      }

      function buildCat() {
        var wrap = document.createElement("div");
        wrap.className = "mascot-cat";
        wrap.id = "mascot-cat";
        wrap.setAttribute("aria-hidden", "true");
        wrap.innerHTML =
          '<button type="button" class="mascot-dismiss" title="Hide mascot" aria-label="Hide the Explain Simply mascot">&times;</button>' +
          '<div class="mascot-clip" id="mascot-clip">' +
          '<svg class="mascot-svg" viewBox="0 0 60 46" xmlns="http://www.w3.org/2000/svg">' +
          '<path class="mascot-line mascot-tail" d="M6 30 C -2 26, -1 14, 8 12"/>' +
          '<g class="mascot-legs">' +
          '<path class="mascot-line" d="M18 40 V45 M26 40 V45 M36 40 V45 M44 40 V45"/>' +
          "</g>" +
          '<ellipse class="mascot-fill mascot-body-group" cx="30" cy="34" rx="17" ry="9"/>' +
          '<g transform="translate(38,14)">' +
          '<circle class="mascot-fill" cx="8" cy="10" r="10"/>' +
          '<path class="mascot-fill" d="M1 4 L -3 -5 L 5 1 Z"/>' +
          '<path class="mascot-fill" d="M15 4 L 19 -5 L 11 1 Z"/>' +
          '<g class="mascot-eyes-open"><circle cx="5" cy="10" r="1.3" fill="var(--text)"/><circle cx="11" cy="10" r="1.3" fill="var(--text)"/></g>' +
          '<g class="mascot-eyes-closed"><path class="mascot-line" d="M3.5 10 q1.5 1.5 3 0 M9.5 10 q1.5 1.5 3 0"/></g>' +
          '<path class="mascot-line mascot-accent" d="M8 12.5 q-1.5 1.5 -3 0.3 M8 12.5 q1.5 1.5 3 0.3" style="stroke-width:1.1;"/>' +
          '<text class="mascot-zzz" x="20" y="-4" font-size="9" fill="var(--text-dim)" font-family="ui-monospace, Menlo, monospace">z</text>' +
          "</g>" +
          '<g class="mascot-paw" transform="translate(46,26)"><path class="mascot-line" d="M0 8 q6 -4 10 -10"/></g>' +
          "</svg>" +
          "</div>";
        document.body.appendChild(wrap);

        var ball = document.createElement("div");
        ball.className = "mascot-ball";
        ball.id = "mascot-ball";
        ball.setAttribute("aria-hidden", "true");
        document.body.appendChild(ball);

        wrap.querySelector(".mascot-dismiss").addEventListener("click", function (e) {
          e.stopPropagation();
          localStorage.setItem("aistore-mascot", "off");
          mascotDisable();
        });

        return { cat: wrap, ball: ball };
      }

      function moveTo(point, fast) {
        catEl.classList.toggle("mascot-fast-move", !!fast);
        catEl.style.left = point.x + "px";
        catEl.style.top = point.y + "px";
        pos = point;
      }

      function setState(state) {
        catEl.className = "mascot-cat mascot-visible state-" + state;
      }

      function showBallNear(point) {
        ballEl.style.left = (point.x + 44) + "px";
        ballEl.style.top = (point.y + 34) + "px";
        ballEl.classList.add("mascot-visible");
        after(900, function () {
          ballEl.style.left = (point.x + 30) + "px";
          ballEl.style.top = (point.y + 40) + "px";
        });
        after(2200, function () { ballEl.classList.remove("mascot-visible"); });
      }

      function walkTo(dest, onArrive) {
        var dx = dest.x - pos.x, dy = dest.y - pos.y;
        catEl.setAttribute("data-facing", dx < 0 ? "left" : "right");
        setState("walk");
        moveTo(dest, false);
        var dist = Math.sqrt(dx * dx + dy * dy);
        var duration = Math.min(1600, Math.max(500, dist * 3));
        after(duration, function () {
          setState("sit");
          if (onArrive) onArrive();
        });
      }

      function findVisible(selector) {
        var els = Array.prototype.slice.call(document.querySelectorAll(selector));
        var b = bounds();
        els = els.filter(function (el) {
          var r = el.getBoundingClientRect();
          return r.top > b.minY - 40 && r.bottom < window.innerHeight && r.width > 60;
        });
        return els.length ? els[Math.floor(Math.random() * els.length)] : null;
      }

      // Weighted so ~90% of what the cat does is calm/helpful (point at an explanation, stretch,
      // sleep, walk to a new spot) and only ~10% is purely playful (hide, jump, play ball) — a
      // clever helper that occasionally does something cute, not the main attraction.
      function nextActivity() {
        if (!running) return;
        var roll = Math.random();
        if (roll < 0.4) {
          var card = findVisible(".simple-explain, .term");
          if (card) {
            var r = card.getBoundingClientRect();
            walkTo({ x: Math.min(bounds().maxX, r.left + 10), y: Math.max(bounds().minY, r.top - 40) }, function () {
              setState("point");
              highlightExplain(card, true);
              after(1800, function () {
                highlightExplain(card, false);
                setState("sit");
                after(idleGap(), nextActivity);
              });
            });
          } else {
            walkTo(randomPoint(), function () { after(idleGap(), nextActivity); });
          }
        } else if (roll < 0.65) {
          walkTo(randomPoint(), function () {
            setState("stretch");
            after(1400, function () { setState("sit"); after(idleGap(), nextActivity); });
          });
        } else if (roll < 0.8) {
          walkTo(randomPoint(), function () {
            setState("sleep");
            after(3200, function () { setState("sit"); after(idleGap(), nextActivity); });
          });
        } else if (roll < 0.9) {
          walkTo(randomPoint(), function () { after(idleGap(), nextActivity); });
        } else if (roll < 0.95) {
          var box = findVisible(".card, .table-wrap, .configurator-panel");
          if (box) {
            var br = box.getBoundingClientRect();
            var target = { x: Math.max(bounds().minX, Math.min(bounds().maxX, br.left + 10)), y: Math.min(bounds().maxY + 60, br.bottom - 8) };
            walkTo(target, function () {
              var clip = document.getElementById("mascot-clip");
              clip.classList.add("mascot-hiding");
              after(1400, function () {
                clip.classList.remove("mascot-hiding");
                after(idleGap(), nextActivity);
              });
            });
          } else {
            walkTo(randomPoint(), function () { after(idleGap(), nextActivity); });
          }
        } else if (roll < 0.98) {
          walkTo(randomPoint(), function () {
            setState("jump");
            after(700, function () { setState("sit"); after(idleGap(), nextActivity); });
          });
        } else {
          walkTo(randomPoint(), function () {
            showBallNear(pos);
            after(2400, function () { after(idleGap(), nextActivity); });
          });
        }
      }

      function distanceToCat(clientX, clientY) {
        var r = catEl.getBoundingClientRect();
        var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        return Math.sqrt(Math.pow(clientX - cx, 2) + Math.pow(clientY - cy, 2));
      }

      // If the cursor lands right on the cat (e.g. it's sitting on top of text a visitor is
      // trying to read), it moves clear out of the way — to whichever screen edge is farthest
      // from the cursor — rather than a small step that might still be in the way.
      function edgeAwayFrom(clientX, clientY) {
        var b = bounds();
        var distLeft = clientX - b.minX;
        var distRight = b.maxX - clientX;
        var distTop = clientY - b.minY;
        var distBottom = b.maxY - clientY;
        var farthest = Math.max(distLeft, distRight, distTop, distBottom);
        var jitter = function (v, min, max) {
          return Math.max(min, Math.min(max, v + (Math.random() * 200 - 100)));
        };
        if (farthest === distLeft) return { x: b.minX, y: jitter(clientY, b.minY, b.maxY) };
        if (farthest === distRight) return { x: b.maxX, y: jitter(clientY, b.minY, b.maxY) };
        if (farthest === distTop) return { x: jitter(clientX, b.minX, b.maxX), y: b.minY };
        return { x: jitter(clientX, b.minX, b.maxX), y: b.maxY };
      }

      function onMouseMove(e) {
        if (!running) return;
        var now = Date.now();
        if (now < fleeCooldown) return;
        if (distanceToCat(e.clientX, e.clientY) < 48) {
          fleeCooldown = now + 2000;
          clearTimers();
          setState("startle");
          document.getElementById("mascot-ball") && ballEl.classList.remove("mascot-visible");
          after(120, function () {
            var dest = edgeAwayFrom(e.clientX, e.clientY);
            catEl.setAttribute("data-facing", dest.x < pos.x ? "left" : "right");
            setState("flee");
            moveTo(dest, true);
            after(450, function () {
              setState("sit");
              after(idleGap(), nextActivity);
            });
          });
        }
      }

      function startLoop() {
        var start = randomPoint();
        catEl.style.left = start.x + "px";
        catEl.style.top = start.y + "px";
        pos = start;
        setState("sit");
        after(1200, nextActivity);
      }

      mascotEnable = function () {
        if (reduceMotion || isMobile) return;
        if (localStorage.getItem("aistore-mascot") === "off") return;
        if (running) return;
        running = true;
        if (!catEl) {
          var built = buildCat();
          catEl = built.cat;
          ballEl = built.ball;
          document.addEventListener("mousemove", onMouseMove, { passive: true });
          window.addEventListener("resize", function () {
            if (catEl) {
              var b = bounds();
              pos.x = Math.min(pos.x, b.maxX);
              pos.y = Math.min(pos.y, b.maxY);
              catEl.style.left = pos.x + "px";
              catEl.style.top = pos.y + "px";
            }
          });
        }
        catEl.classList.add("mascot-visible");
        startLoop();
      };

      mascotDisable = function () {
        running = false;
        clearTimers();
        if (catEl) catEl.classList.remove("mascot-visible");
        if (ballEl) ballEl.classList.remove("mascot-visible");
      };
    })();

    function applySimpleMode(on) {
      document.documentElement.setAttribute("data-simple", on ? "on" : "off");
      var btn = document.getElementById("simple-toggle");
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      document.getElementById("simple-label").textContent = on ? "Explain simply: on" : "Explain simply";
      if (on) { mascotEnable(); } else { mascotDisable(); }
    }
    applySimpleMode(localStorage.getItem("aistore-simple") === "on");

    document.getElementById("simple-toggle").addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-simple") !== "on";
      localStorage.setItem("aistore-simple", next ? "on" : "off");
      applySimpleMode(next);
    });

    // One-time nudge so first-time visitors know the smiley icon reveals plain-language
    // explanations. Shows once ever (per browser), auto-hides, dismisses on any click/scroll.
    (function () {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      if (localStorage.getItem("aistore-simple-hint-seen") === "1") return;
      if (localStorage.getItem("aistore-simple") === "on") return;
      var hint = document.getElementById("simple-discovery-hint");
      if (!hint) return;
      var dismissed = false;
      function dismiss() {
        if (dismissed) return;
        dismissed = true;
        hint.classList.remove("show");
        localStorage.setItem("aistore-simple-hint-seen", "1");
        document.removeEventListener("click", dismiss);
        document.removeEventListener("scroll", dismiss);
      }
      setTimeout(function () {
        if (localStorage.getItem("aistore-simple") === "on") return;
        hint.classList.add("show");
        setTimeout(dismiss, 6000);
        document.addEventListener("click", dismiss);
        document.addEventListener("scroll", dismiss, { passive: true, once: true });
      }, 1600);
    })();

    var navToggle = document.getElementById("nav-toggle");
    var mainNav = document.getElementById("main-nav");
    if (navToggle && mainNav) {
      navToggle.addEventListener("click", function () {
        var isOpen = mainNav.classList.toggle("open");
        navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        closeNavMore();
      });
    }

    // "More" dropdown — houses the four less-essential nav links at medium (laptop) widths.
    var navMoreToggle = document.getElementById("nav-more-toggle");
    var navMoreMenu = document.getElementById("nav-more-menu");
    function closeNavMore() {
      if (!navMoreMenu) return;
      navMoreMenu.classList.remove("open");
      navMoreToggle.setAttribute("aria-expanded", "false");
    }
    if (navMoreToggle && navMoreMenu) {
      navMoreToggle.addEventListener("click", function (e) {
        e.stopPropagation();
        var isOpen = navMoreMenu.classList.toggle("open");
        navMoreToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      });
      document.addEventListener("click", function (e) {
        if (!navMoreMenu.contains(e.target) && e.target !== navMoreToggle) closeNavMore();
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && navMoreMenu.classList.contains("open")) {
          closeNavMore();
          navMoreToggle.focus();
        }
      });
      window.addEventListener("resize", closeNavMore);
    }

    document.querySelectorAll(
      "main .card, main .table-wrap, main h1, main h2, main .stat-chip, main .learn-item, main .faq-item, main .spec-table"
    ).forEach(function (el) {
      el.classList.add("reveal");
    });

    // Safety net: no matter what — no scrolling, JS timing, or a bot that never fires the
    // IntersectionObserver — every ".reveal" element must end up visible on its own within ~1s.
    // Content must never depend on a real user scrolling to become visible.
    setTimeout(function () {
      document.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("visible"); });
    }, 900);

    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1, rootMargin: "0px 0px -40px 0px" });
      document.querySelectorAll(".reveal").forEach(function (el) { observer.observe(el); });
    } else {
      document.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("visible"); });
    }

    var floatingCta = document.getElementById("floating-cta");
    var headerEl = document.querySelector("header");
    window.addEventListener("scroll", function () {
      if (floatingCta) {
        if (window.scrollY > 300) floatingCta.classList.add("visible");
        else floatingCta.classList.remove("visible");
      }
      if (headerEl) {
        if (window.scrollY > 40) headerEl.classList.add("scrolled");
        else headerEl.classList.remove("scrolled");
      }
    }, { passive: true });

    document.querySelectorAll("a.btn, button.btn, a.btn-secondary, button.btn-secondary").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        var rect = btn.getBoundingClientRect();
        var ripple = document.createElement("span");
        var size = Math.max(rect.width, rect.height) * 1.4;
        ripple.className = "ripple";
        ripple.style.width = ripple.style.height = size + "px";
        ripple.style.left = (e.clientX - rect.left - size / 2) + "px";
        ripple.style.top = (e.clientY - rect.top - size / 2) + "px";
        btn.appendChild(ripple);
        setTimeout(function () { ripple.remove(); }, 600);
      });
    });

    document.addEventListener("click", function (e) {
      var clickedTerm = e.target.closest(".term");
      document.querySelectorAll(".tooltip-bubble.open").forEach(function (bubble) {
        var owner = bubble.closest(".term");
        if (owner !== clickedTerm) bubble.classList.remove("open");
      });
      if (clickedTerm) {
        var bubble = clickedTerm.querySelector(".tooltip-bubble");
        if (bubble) bubble.classList.toggle("open");
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll(".tooltip-bubble.open").forEach(function (b) { b.classList.remove("open"); });
        closeLightbox();
        if (document.getElementById("quickview-overlay").classList.contains("open")) closeQuickView();
      }
    });

    var lightboxOverlay = document.getElementById("lightbox-overlay");
    var lightboxImg = document.getElementById("lightbox-img");

    function openLightbox(src, alt) {
      lightboxImg.src = src;
      lightboxImg.alt = alt || "";
      lightboxOverlay.classList.add("open");
    }

    function closeLightbox() {
      lightboxOverlay.classList.remove("open");
      setTimeout(function () { lightboxImg.src = ""; }, 300);
    }

    document.querySelectorAll(".product-photo img, .hero-photo img").forEach(function (img) {
      img.addEventListener("click", function (e) {
        e.stopPropagation();
        openLightbox(img.currentSrc || img.src, img.alt);
      });
    });

    function wireImageSkeletons(scope) {
      scope.querySelectorAll(".product-photo img, .thumb img").forEach(function (img) {
        var container = img.closest(".product-photo, .thumb");
        function markLoaded() {
          img.classList.add("img-loaded");
          if (container) container.classList.add("img-ready");
        }
        function markFailed() {
          if (container) container.classList.add("img-ready");
        }
        if (img.complete && img.naturalWidth > 0) {
          markLoaded();
        } else if (img.complete) {
          markFailed();
        } else {
          img.addEventListener("load", markLoaded);
          img.addEventListener("error", markFailed);
          setTimeout(function () {
            if (!img.classList.contains("img-loaded")) markFailed();
          }, 2500);
        }
      });
    }
    wireImageSkeletons(document);

    (function () {
      var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var detailsEls = document.querySelectorAll("details");
      if (!detailsEls.length) return;

      detailsEls.forEach(function (details) {
        var summary = details.querySelector("summary");
        var body = details.querySelector(":scope > div");
        if (!summary || !body) return;
        details.dataset.animating = "false";

        summary.addEventListener("click", function (e) {
          e.preventDefault();
          if (details.dataset.animating === "true") return;

          if (reduceMotion) { details.open = !details.open; return; }

          body.style.overflow = "hidden";

          if (!details.open) {
            details.dataset.animating = "true";
            details.open = true;
            var targetHeight = body.offsetHeight;
            var anim = body.animate(
              [{ height: "0px", opacity: 0.3 }, { height: targetHeight + "px", opacity: 1 }],
              { duration: 240, easing: "cubic-bezier(0.16, 1, 0.3, 1)", fill: "both" }
            );
            anim.onfinish = function () {
              anim.cancel();
              body.style.height = "auto";
              body.style.overflow = "";
              details.dataset.animating = "false";
            };
          } else {
            details.dataset.animating = "true";
            var startHeight = body.offsetHeight;
            var closeAnim = body.animate(
              [{ height: startHeight + "px", opacity: 1 }, { height: "0px", opacity: 0.3 }],
              { duration: 200, easing: "cubic-bezier(0.7, 0, 0.84, 0)", fill: "both" }
            );
            closeAnim.onfinish = function () {
              closeAnim.cancel();
              details.open = false;
              body.style.height = "";
              body.style.overflow = "";
              details.dataset.animating = "false";
            };
          }
        });
      });
    })();

    document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
    lightboxOverlay.addEventListener("click", function (e) {
      if (e.target === lightboxOverlay) closeLightbox();
    });

    var quickviewOverlay = document.getElementById("quickview-overlay");
    var quickviewBody = document.getElementById("quickview-body");
    var quickviewLastFocus = null;

    function openQuickView(slug) {
      var source = document.getElementById("qv-source-" + slug);
      if (!source || !quickviewBody) return;
      quickviewBody.innerHTML = source.innerHTML;
      var titleEl = quickviewBody.querySelector(".qv-name");
      if (titleEl) titleEl.id = "quickview-title";
      wireImageSkeletons(quickviewBody);
      quickviewLastFocus = document.activeElement;
      quickviewOverlay.classList.add("open");
      document.getElementById("quickview-close").focus();
    }

    function closeQuickView() {
      quickviewOverlay.classList.remove("open");
      if (quickviewLastFocus) quickviewLastFocus.focus();
      setTimeout(function () { quickviewBody.innerHTML = ""; }, 300);
    }

    document.addEventListener("click", function (e) {
      var trigger = e.target.closest(".quickview-btn");
      if (trigger) openQuickView(trigger.dataset.slug);
    });

    if (quickviewOverlay) {
      document.getElementById("quickview-close").addEventListener("click", closeQuickView);
      quickviewOverlay.addEventListener("click", function (e) {
        if (e.target === quickviewOverlay) closeQuickView();
      });
    }

    (function () {
      var overlay = document.getElementById("cmdk-overlay");
      var input = document.getElementById("cmdk-input");
      var resultsEl = document.getElementById("cmdk-results");
      var trigger = document.getElementById("cmdk-trigger");
      if (!overlay || !input) return;

      var products = [];
      try { products = JSON.parse(document.getElementById("nav-products-data").textContent); } catch (e) { /* no product data */ }
      var pages = window.APP_PAGES || [];
      var items = pages.concat(products.map(function (p) {
        return { name: p.name, sub: p.category + " — view full specification", href: "/product/" + p.slug };
      }));

      var activeIndex = 0;
      var visibleItems = [];

      function render(query) {
        var q = (query || "").trim().toLowerCase();
        visibleItems = !q ? items : items.filter(function (it) {
          return it.name.toLowerCase().indexOf(q) !== -1 || it.sub.toLowerCase().indexOf(q) !== -1;
        });
        activeIndex = 0;

        if (!visibleItems.length) {
          resultsEl.innerHTML = '<div class="cmdk-empty">No matches. Try a product name or page.</div>';
          return;
        }

        resultsEl.innerHTML = visibleItems.map(function (it, i) {
          return '<div class="cmdk-item' + (i === 0 ? ' active' : '') + '" data-href="' + it.href + '" role="option">' +
            '<span>' + it.name + '</span><span class="cmdk-item-sub">' + it.sub + '</span></div>';
        }).join("");

        resultsEl.querySelectorAll(".cmdk-item").forEach(function (el, i) {
          el.addEventListener("click", function () { window.location.href = visibleItems[i].href; });
          el.addEventListener("mouseenter", function () { setActive(i); });
        });
      }

      function setActive(i) {
        activeIndex = i;
        resultsEl.querySelectorAll(".cmdk-item").forEach(function (el, idx) {
          el.classList.toggle("active", idx === i);
        });
      }

      function openPalette() {
        overlay.classList.add("open");
        input.value = "";
        render("");
        setTimeout(function () { input.focus(); }, 20);
      }

      function closePalette() {
        overlay.classList.remove("open");
      }

      if (trigger) trigger.addEventListener("click", openPalette);
      overlay.addEventListener("click", function (e) { if (e.target === overlay) closePalette(); });
      input.addEventListener("input", function () { render(input.value); });

      input.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(activeIndex + 1, visibleItems.length - 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(activeIndex - 1, 0)); }
        else if (e.key === "Enter") { e.preventDefault(); if (visibleItems[activeIndex]) window.location.href = visibleItems[activeIndex].href; }
        else if (e.key === "Escape") { closePalette(); }
      });

      document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
          e.preventDefault();
          overlay.classList.contains("open") ? closePalette() : openPalette();
        } else if (e.key === "Escape" && overlay.classList.contains("open")) {
          closePalette();
        }
      });
    })();

    document.querySelectorAll(".more-specs-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var panel = document.getElementById(btn.dataset.target);
        if (!panel) return;
        var isOpen = panel.classList.toggle("open");
        btn.classList.toggle("open", isOpen);
        btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
        btn.querySelector(".toggle-text").textContent = isOpen ? "Hide full specs" : "Show full specs";
      });
    });
