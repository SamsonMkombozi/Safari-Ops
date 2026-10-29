/**
 * Safari-Ops — shared UI helpers
 *
 * Loaded by layouts/admin.php on every admin page (it was referenced
 * there but never actually existed — a silent 404 on every page load).
 * Holds the small pieces of behavior that individual admin/*.php pages
 * were each re-implementing slightly differently: a toast() notification
 * function, and open/close wiring for the .admin-modal-overlay component
 * in admin/css/admin.css. A page can still define its own toast()/
 * openModal()/closeModal() if it needs custom behavior — a later
 * function declaration on the same page simply shadows these.
 */
(function () {
  'use strict';

  // ── Toast notifications ─────────────────────────────────────
  // Uses .toast-container / .toast / .toast--ok / .toast--err from
  // admin.css. Creates the container on first use if the page didn't
  // already add one (most pages that want toasts include
  // <div class="toast-container"></div> once in their markup).
  function toastContainer() {
    var el = document.querySelector('.toast-container');
    if (!el) {
      el = document.createElement('div');
      el.className = 'toast-container';
      document.body.appendChild(el);
    }
    return el;
  }

  window.toast = window.toast || function (msg, type) {
    var t = document.createElement('div');
    t.className = 'toast' + (type === 'ok' ? ' toast--ok' : type === 'err' ? ' toast--err' : '');
    t.textContent = msg;
    toastContainer().appendChild(t);
    setTimeout(function () { t.remove(); }, 3500);
  };

  // ── Focus trap ────────────────────────────────────────────────
  // Confines Tab/Shift+Tab cycling within `container` while it's the
  // active modal — Tab on the last focusable element wraps to the
  // first, Shift+Tab on the first wraps to the last, so keyboard focus
  // can never silently land on the page behind the modal while it's
  // open. Returns a function that removes the trap.
  function trapFocusWithin(container) {
    function focusables() {
      return Array.prototype.slice.call(
        container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
      ).filter(function (el) { return el.offsetParent !== null; });
    }
    function onKey(e) {
      if (e.key !== 'Tab') return;
      var items = focusables();
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    container.addEventListener('keydown', onKey);
    return function () { container.removeEventListener('keydown', onKey); };
  }

  // ── Modal open/close ─────────────────────────────────────────
  // Toggles the 'open' class on an .admin-modal-overlay by id. Also
  // wires every .admin-modal-overlay already in the page (event
  // delegation, so modals added dynamically later still work) so that
  // clicking the backdrop or pressing Escape closes whichever modal is
  // currently open — a page doesn't have to wire that itself.
  window.openModal = window.openModal || function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('open');
  };
  window.closeModal = window.closeModal || function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('open');
  };

  document.addEventListener('click', function (e) {
    if (e.target.classList && e.target.classList.contains('admin-modal-overlay') && e.target.classList.contains('open')) {
      e.target.classList.remove('open');
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.admin-modal-overlay.open').forEach(function (el) {
      el.classList.remove('open');
    });
  });

  // ── Modal accessibility (ARIA + focus management) ────────────
  // This does NOT live inside openModal()/closeModal() above, because
  // only 1 of the ~19 admin/agent-portal files with a modal (
  // currency_rates.php) actually calls those — every other one defines
  // its own page-local openXModal()/closeXModal() that just toggles the
  // 'open' class directly (confirmed by reading every one of them), so
  // accessibility behavior that only lived in the two shared functions
  // above would silently cover almost none of the real modals. Watching
  // the class itself, however it gets toggled, covers all of them
  // uniformly with zero per-page markup or script changes, and will
  // keep covering any future modal/open-function without needing to
  // remember to wire it in.
  //
  // On the 'open' class appearing: sets role="dialog", aria-modal, and
  // aria-labelledby (pointing at the modal's own .admin-modal-title,
  // id generated on first use if it doesn't already have one); moves
  // focus into the dialog if nothing inside it already has focus by the
  // time this runs (a few pages, e.g. admin/leads.php's openAddModal(),
  // already focus a specific field themselves — this only ever adds a
  // fallback, never overrides a deliberate choice); and traps Tab
  // cycling inside the dialog while open.
  // On 'open' disappearing: removes the trap and restores focus to
  // whatever had it before the modal opened.
  var modalA11yState = new WeakMap(); // overlay el -> {removeTrap, prevFocus}

  // Tracks focus continuously, outside the observer callback, because the
  // callback itself only fires async (a microtask after the class change)
  // — by then, a page that focuses a field synchronously right after its
  // own classList.add('open') (several do) has already moved focus
  // *into* the modal, so reading document.activeElement at observer-fire
  // time would wrongly capture that field as "where focus came from"
  // instead of the actual trigger element outside the modal.
  var lastExternalFocus = null;
  document.addEventListener('focusin', function (e) {
    if (!e.target.closest('.admin-modal-overlay.open')) lastExternalFocus = e.target;
  }, true);

  function modalOpened(el) {
    var dialog = el.querySelector('.admin-modal');
    if (dialog) {
      if (!dialog.hasAttribute('role')) dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');
      var titleEl = dialog.querySelector('.admin-modal-title');
      if (titleEl) {
        if (!titleEl.id) titleEl.id = (el.id || ('modal-' + Math.random().toString(36).slice(2))) + '-title';
        dialog.setAttribute('aria-labelledby', titleEl.id);
      }
    }
    modalA11yState.set(el, {
      removeTrap: dialog ? trapFocusWithin(dialog) : function () {},
      prevFocus: lastExternalFocus || document.activeElement
    });
    setTimeout(function () {
      if (dialog && dialog.contains(document.activeElement)) return; // page already focused something itself
      var target = dialog && (
        dialog.querySelector('input:not([type=hidden]):not([disabled]), select, textarea') ||
        dialog.querySelector('.admin-modal-close') ||
        dialog
      );
      if (target) {
        if (target === dialog && !target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
        target.focus();
      }
    }, 30);
  }

  function modalClosed(el) {
    var state = modalA11yState.get(el);
    if (!state) return;
    state.removeTrap();
    if (state.prevFocus && state.prevFocus.focus) state.prevFocus.focus();
    modalA11yState.delete(el);
  }

  function observeModal(el) {
    if (el._a11yModalObserved) return;
    // confirmDialog()/promptDialog() overlays already implement this
    // exact same behavior inline (they're created already-open and torn
    // down via .remove(), not the open-class toggle this observer
    // watches for) — skip them so they aren't handled twice.
    if (el.classList.contains('confirm-dialog-overlay')) return;
    el._a11yModalObserved = true;
    var wasOpen = el.classList.contains('open');
    if (wasOpen) modalOpened(el);
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        if (m.attributeName !== 'class') return;
        var isOpen = el.classList.contains('open');
        if (isOpen === wasOpen) return;
        wasOpen = isOpen;
        if (isOpen) modalOpened(el); else modalClosed(el);
      });
    }).observe(el, { attributes: true, attributeFilter: ['class'] });
  }

  document.querySelectorAll('.admin-modal-overlay').forEach(observeModal);
  // Covers overlays added to the DOM after this script runs too.
  new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      (m.addedNodes || []).forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (node.classList && node.classList.contains('admin-modal-overlay')) observeModal(node);
        if (node.querySelectorAll) node.querySelectorAll('.admin-modal-overlay').forEach(observeModal);
      });
    });
  }).observe(document.body, { childList: true, subtree: true });

  // ── Confirm-before-change for status <select> dropdowns ──────
  // A status/stage <select> that fires its change immediately (no
  // separate "Save" step) needs its own confirm — and, on Cancel, needs
  // to visibly snap back to the value it actually still holds server-side,
  // or the dropdown shows a status that was never saved. The select
  // carries that known-good value in data-prev (set server-side on page
  // load, and updated here after every confirmed, successfully-saved
  // change) so repeated changes always revert to the last real state,
  // not just whatever was on the page when it first loaded.
  // ── Custom confirm dialog ─────────────────────────────────────
  // Replaces window.confirm() everywhere in the panel with a dialog
  // styled to match (and themed by, in dark mode) the rest of the UI —
  // native confirm() can't be restyled at all. Since a real DOM dialog
  // can't block like window.confirm() does, this is Promise-based; every
  // call site awaits it instead of reading a synchronous return value.
  var ICONS = {
    danger:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l10 18H2Z"/><line x1="12" y1="9" x2="12" y2="14"/><circle cx="12" cy="17.2" r=".6" fill="currentColor" stroke="none"/></svg>',
    default: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5"/><circle cx="12" cy="17" r=".6" fill="currentColor" stroke="none"/></svg>'
  };

  window.confirmDialog = window.confirmDialog || function (message, opts) {
    opts = opts || {};
    var danger = !!opts.danger;
    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'admin-modal-overlay confirm-dialog-overlay open';
      overlay.setAttribute('role', 'presentation');
      overlay.innerHTML =
        '<div class="admin-modal confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirmDialogTitle">' +
          '<div class="confirm-dialog-icon confirm-dialog-icon--' + (danger ? 'danger' : 'default') + '">' + ICONS[danger ? 'danger' : 'default'] + '</div>' +
          '<div class="confirm-dialog-title" id="confirmDialogTitle"></div>' +
          '<div class="confirm-dialog-message"></div>' +
          '<div class="confirm-dialog-actions">' +
            '<button type="button" class="admin-btn admin-btn--outline confirm-dialog-cancel"></button>' +
            '<button type="button" class="admin-btn ' + (danger ? 'admin-btn--danger' : 'admin-btn--primary') + ' confirm-dialog-ok"></button>' +
          '</div>' +
        '</div>';
      // Set via textContent, not innerHTML — message/labels can contain
      // user-entered data (names, refs), and must never be interpreted
      // as markup.
      overlay.querySelector('.confirm-dialog-title').textContent = opts.title || (danger ? 'Are you sure?' : 'Please confirm');
      overlay.querySelector('.confirm-dialog-message').textContent = message;
      overlay.querySelector('.confirm-dialog-cancel').textContent = opts.cancelLabel || 'Cancel';
      overlay.querySelector('.confirm-dialog-ok').textContent = opts.confirmLabel || (danger ? 'Delete' : 'Confirm');
      document.body.appendChild(overlay);

      var prevFocus = document.activeElement;
      var removeFocusTrap = trapFocusWithin(overlay.querySelector('.confirm-dialog'));
      function cleanup(result) {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
        removeFocusTrap();
        if (prevFocus && prevFocus.focus) prevFocus.focus();
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup(false);
      }
      overlay.querySelector('.confirm-dialog-cancel').addEventListener('click', function () { cleanup(false); });
      overlay.querySelector('.confirm-dialog-ok').addEventListener('click', function () { cleanup(true); });
      overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) cleanup(false); });
      document.addEventListener('keydown', onKey);
      overlay.querySelector('.confirm-dialog-ok').focus();
    });
  };

  // ── Prompt-for-a-value dialog ──────────────────────────────────
  // Replaces window.prompt() the same way confirmDialog() replaces
  // window.confirm() above — native prompt() can't be restyled and (in
  // some embedded contexts) doesn't work at all. Resolves to the entered
  // string, or null on Cancel/Escape/backdrop click. Used wherever a
  // status change needs a number or short text captured alongside it
  // (e.g. "Deposit Paid" needing the actual amount received).
  window.promptDialog = window.promptDialog || function (message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'admin-modal-overlay confirm-dialog-overlay open';
      overlay.setAttribute('role', 'presentation');
      overlay.innerHTML =
        '<div class="admin-modal confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="promptDialogTitle">' +
          '<div class="confirm-dialog-icon confirm-dialog-icon--default">' + ICONS.default + '</div>' +
          '<div class="confirm-dialog-title" id="promptDialogTitle"></div>' +
          '<div class="confirm-dialog-message"></div>' +
          '<input class="admin-input confirm-dialog-input" style="margin-top:1rem;width:100%;box-sizing:border-box">' +
          '<div class="confirm-dialog-actions">' +
            '<button type="button" class="admin-btn admin-btn--outline confirm-dialog-cancel"></button>' +
            '<button type="button" class="admin-btn admin-btn--primary confirm-dialog-ok"></button>' +
          '</div>' +
        '</div>';
      overlay.querySelector('.confirm-dialog-title').textContent = opts.title || 'Enter a value';
      overlay.querySelector('.confirm-dialog-message').textContent = message;
      overlay.querySelector('.confirm-dialog-cancel').textContent = opts.cancelLabel || 'Cancel';
      overlay.querySelector('.confirm-dialog-ok').textContent = opts.confirmLabel || 'Save';
      var input = overlay.querySelector('.confirm-dialog-input');
      input.type = opts.inputType || 'text';
      if (opts.inputType === 'number') {
        input.step = opts.step || 'any';
        if (opts.min != null) input.min = opts.min;
      }
      if (opts.placeholder) input.placeholder = opts.placeholder;
      if (opts.value != null) input.value = opts.value;
      document.body.appendChild(overlay);

      var prevFocus = document.activeElement;
      var removeFocusTrap = trapFocusWithin(overlay.querySelector('.confirm-dialog'));
      function cleanup(result) {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
        removeFocusTrap();
        if (prevFocus && prevFocus.focus) prevFocus.focus();
        resolve(result);
      }
      function submit() {
        var val = input.value.trim();
        if (opts.required !== false && !val) { input.focus(); return; }
        cleanup(val);
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup(null);
        else if (e.key === 'Enter' && document.activeElement === input) { e.preventDefault(); submit(); }
      }
      overlay.querySelector('.confirm-dialog-cancel').addEventListener('click', function () { cleanup(null); });
      overlay.querySelector('.confirm-dialog-ok').addEventListener('click', submit);
      overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) cleanup(null); });
      document.addEventListener('keydown', onKey);
      setTimeout(function () { input.focus(); input.select(); }, 30);
    });
  };

  // ── Confirm-before-change for status <select> dropdowns ──────
  // A status/stage <select> that fires its change immediately (no
  // separate "Save" step) needs its own confirm — and, on Cancel, needs
  // to visibly snap back to the value it actually still holds server-side,
  // or the dropdown shows a status that was never saved. The select
  // carries that known-good value in data-prev (set server-side on page
  // load, and updated here after every confirmed, successfully-saved
  // change) so repeated changes always revert to the last real state,
  // not just whatever was on the page when it first loaded.
  window.confirmStatusChange = window.confirmStatusChange || async function (sel, message, opts) {
    var ok = await window.confirmDialog(message, opts);
    if (!ok && sel.dataset.prev !== undefined) sel.value = sel.dataset.prev;
    return ok;
  };

  // ── Confirm-before-submit for plain <form onsubmit="return
  //    confirmSubmitGuard(event, this, '...')">  patterns — covers every
  //    delete/destructive form in the panel that used to be
  //    onsubmit="return confirm('...')". Always returns false (blocking
  //    the native submit); submits manually once the dialog resolves true.
  window.confirmSubmitGuard = window.confirmSubmitGuard || function (e, form, message, opts) {
    e.preventDefault();
    window.confirmDialog(message, opts).then(function (ok) { if (ok) form.submit(); });
    return false;
  };

  // ── Confirm-before-navigate for plain <a onclick="return
  //    confirmNavGuard(event, this.href, '...')"> links (e.g. "send this
  //    email now?"). Always returns false; navigates manually on confirm.
  window.confirmNavGuard = window.confirmNavGuard || function (e, href, message, opts) {
    e.preventDefault();
    window.confirmDialog(message, opts).then(function (ok) { if (ok) window.location.href = href; });
    return false;
  };

  // ── Row actions menu (the kebab/⋮ button in every table's Actions
  //    column) ────────────────────────────────────────────────────
  // One delegated listener handles every .admin-row-actions on the page,
  // so a table needs no per-page JS beyond the markup itself: a
  // .admin-row-actions wrapper holding a .admin-row-actions-toggle button
  // and a .admin-row-actions-menu panel of .admin-row-actions-item
  // links/buttons/forms. The panel is positioned as `position: fixed`
  // from the toggle's own getBoundingClientRect() — not CSS-relative —
  // because a table's horizontally scrolling .admin-table-wrap would
  // otherwise clip a relatively-positioned dropdown for any row near its
  // edge. Only one menu is ever open at a time.
  (function () {
    var openWrap = null;

    // ARIA roles for the dropdown — the toggle button already carries
    // aria-haspopup/aria-expanded from its own markup; this is the one
    // piece a screen reader needs to announce the panel as a menu rather
    // than an unlabeled group of links. Applied once per menu (idempotent,
    // safe to call again) rather than requiring every page that renders
    // this markup to set it itself.
    function ensureMenuRoles(menu) {
      if (!menu || menu.getAttribute('role') === 'menu') return;
      menu.setAttribute('role', 'menu');
      menu.querySelectorAll('.admin-row-actions-item').forEach(function (item) {
        item.setAttribute('role', 'menuitem');
      });
    }
    document.querySelectorAll('.admin-row-actions-menu').forEach(ensureMenuRoles);

    // A11Y-8: previously ensureMenuRoles() set correct menu/menuitem
    // roles but nothing moved focus into the menu on open, restored it
    // to the toggle on close, or let arrow keys move between items — a
    // half-implemented ARIA menu pattern (a screen reader would announce
    // "menu", then nothing worked the way that announcement promises).
    function closeMenu(restoreFocus) {
      if (!openWrap) return;
      var menu = openWrap.querySelector('.admin-row-actions-menu');
      var toggle = openWrap.querySelector('.admin-row-actions-toggle');
      if (menu) menu.style.display = 'none';
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'false');
        if (restoreFocus) toggle.focus();
      }
      openWrap = null;
    }

    function menuItems(wrap) {
      return Array.prototype.slice.call(wrap.querySelectorAll('.admin-row-actions-item'));
    }

    function openMenu(wrap) {
      closeMenu(false);
      var toggle = wrap.querySelector('.admin-row-actions-toggle');
      var menu   = wrap.querySelector('.admin-row-actions-menu');
      if (!toggle || !menu) return;
      ensureMenuRoles(menu);

      menu.style.display = 'block';
      var tRect  = toggle.getBoundingClientRect();
      var menuH  = menu.offsetHeight;
      var menuW  = menu.offsetWidth;
      var openUp   = (tRect.bottom + menuH + 8) > window.innerHeight;
      var openLeft = (tRect.right - menuW) >= 4;

      menu.style.top    = openUp ? '' : (tRect.bottom + 4) + 'px';
      menu.style.bottom = openUp ? (window.innerHeight - tRect.top + 4) + 'px' : '';
      menu.style.left   = openLeft ? (tRect.right - menuW) + 'px' : tRect.left + 'px';

      toggle.setAttribute('aria-expanded', 'true');
      openWrap = wrap;

      var items = menuItems(wrap);
      if (items.length) items[0].focus();
    }

    document.addEventListener('click', function (e) {
      var toggle = e.target.closest('.admin-row-actions-toggle');
      if (toggle) {
        e.stopPropagation();
        var wrap = toggle.closest('.admin-row-actions');
        if (openWrap === wrap) closeMenu(false); else openMenu(wrap);
        return;
      }
      if (openWrap && !openWrap.contains(e.target)) closeMenu(false);
    });
    document.addEventListener('keydown', function (e) {
      if (!openWrap) return;
      if (e.key === 'Escape') { closeMenu(true); return; }
      var items = menuItems(openWrap);
      if (!items.length) return;
      var idx = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        items[idx < 0 || idx === items.length - 1 ? 0 : idx + 1].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        items[idx <= 0 ? items.length - 1 : idx - 1].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        items[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        items[items.length - 1].focus();
      } else if (e.key === 'Tab') {
        // Tabbing out of the menu is a close, same as a backdrop click —
        // don't trap focus inside a transient dropdown the way a modal
        // traps it; the menu just shouldn't still claim to be open.
        closeMenu(false);
      }
    });
    // Capture phase so this also fires for a scroll inside a nested
    // scrollable ancestor (e.g. .admin-table-wrap), which doesn't bubble.
    window.addEventListener('scroll', closeMenu, true);
    window.addEventListener('resize', closeMenu);
  })();
})();
