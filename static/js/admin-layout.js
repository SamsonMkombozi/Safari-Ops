// ── Sidebar toggle (mobile) ──────────────────────────────────
(function () {
  var sidebar  = document.getElementById('adminSidebar');
  var overlay  = document.getElementById('sidebarOverlay');
  var hamburger= document.getElementById('adminHamburger');
  var closeBtn = document.getElementById('sidebarClose');
  if (!sidebar || !overlay || !hamburger) return;

  function openSidebar() {
    sidebar.classList.add('open');
    overlay.classList.add('open');
    hamburger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }
  function closeSidebar() {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
    hamburger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  if (hamburger) hamburger.addEventListener('click', openSidebar);
  if (closeBtn)  closeBtn.addEventListener('click', closeSidebar);
  if (overlay)   overlay.addEventListener('click', closeSidebar);

  // Close on Escape
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSidebar();
  });

  // Close sidebar on nav link click (mobile)
  if (sidebar) {
    sidebar.querySelectorAll('.admin-nav-link').forEach(function(link) {
      link.addEventListener('click', function() {
        if (window.innerWidth <= 768) closeSidebar();
      });
    });
  }
})();

// ── Notification bell dropdown ───────────────────────────────
(function () {
  var wrap  = document.getElementById('adminNotif');
  var toggle = document.getElementById('notifToggle');
  var panel  = document.getElementById('notifPanel');
  if (!wrap || !toggle || !panel) return;

  function open() {
    wrap.classList.add('open');
    toggle.setAttribute('aria-expanded', 'true');
  }
  function close() {
    wrap.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
  }

  toggle.addEventListener('click', function (e) {
    e.stopPropagation();
    wrap.classList.contains('open') ? close() : open();
  });
  document.addEventListener('click', function (e) {
    if (!wrap.contains(e.target)) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
})();

// ── Collapsible nav groups (accordion — one open at a time) ──
// Remembers which single *non-active* group was last opened by choice,
// across page loads (this is a classic multi-page app, not an SPA, so
// without this every navigation would reset the nav back to all-closed).
// The group containing the current page is always forced open regardless
// of that — collapsing the section you're currently in would hide where
// you are.
//
// Storage is deliberately a single "which group is open" key, not a
// per-group map — a per-group map goes stale the moment a group is
// active (and therefore force-open without ever writing its own state),
// then later stops being active: its last manually-saved state (possibly
// "expanded", from before it was ever active) would incorrectly win and
// leave it open even though neither active nor most-recently chosen.
// A single key can't go stale like that — a group is open only if its
// key is the exact one most recently chosen, full stop.
//
// Default (nothing chosen yet) is every non-active group COLLAPSED: with
// 7 groups and dozens of links, having them all open at once is taller
// than the viewport, so the lower groups end up scrolled out of view
// with no visible scrollbar hint — they look missing, not just hidden
// below the fold.
(function () {
  var STORE_KEY = 'szv_admin_nav_open_group';

  function readOpenKey() {
    try { return localStorage.getItem(STORE_KEY); }
    catch (e) { return null; }
  }
  function writeOpenKey(key) {
    try {
      if (key) localStorage.setItem(STORE_KEY, key);
      else localStorage.removeItem(STORE_KEY);
    } catch (e) { /* private-window / storage blocked — collapsing just won't persist */ }
  }

  var openKey = readOpenKey();
  var groups  = [];

  document.querySelectorAll('.admin-nav-group').forEach(function (btn) {
    var key   = btn.getAttribute('data-group');
    var items = document.querySelector('.admin-nav-items[data-group-items="' + key + '"]');
    if (!items) return;

    var hasActive = items.getAttribute('data-has-active') === '1';
    var collapsed = !hasActive && key !== openKey;

    if (collapsed) {
      items.classList.add('collapsed');
      btn.setAttribute('aria-expanded', 'false');
    }

    groups.push({ btn: btn, items: items, key: key, hasActive: hasActive });
  });

  groups.forEach(function (g) {
    g.btn.addEventListener('click', function () {
      if (g.hasActive) return; // never let the current page's own group be hidden by its own click

      var opening = g.items.classList.contains('collapsed');

      // Selecting a new group to browse hides whichever one was
      // previously open that way — only the active group (handled
      // separately above) is exempt from this.
      if (opening) {
        groups.forEach(function (other) {
          if (other === g || other.hasActive) return;
          other.items.classList.add('collapsed');
          other.btn.setAttribute('aria-expanded', 'false');
        });
      }

      var nowCollapsed = g.items.classList.toggle('collapsed');
      g.btn.setAttribute('aria-expanded', nowCollapsed ? 'false' : 'true');
      openKey = nowCollapsed ? null : g.key;
      writeOpenKey(openKey);
    });
  });
})();

// ── Confirm before destructive form posts (data-confirm="…") ──
document.addEventListener('submit', function (e) {
  var form = e.target;
  var msg = form.getAttribute && form.getAttribute('data-confirm');
  if (!msg || form.dataset.confirmed === '1') return;
  e.preventDefault();
  var ask = window.confirmDialog ? window.confirmDialog(msg, { danger: form.dataset.confirmSafe !== '1', confirmLabel: form.dataset.confirmLabel }) : Promise.resolve(window.confirm(msg));
  ask.then(function (ok) { if (ok) { form.dataset.confirmed = '1'; form.submit(); } });
});

// ── Theme picker: system / light / dark / black & white ─────────────
// Applies instantly, remembers it in this browser, and (when signed in)
// saves it to the user's profile so it follows them to other devices.
(function () {
  var root = document.documentElement;
  var STORE_KEY = 'safariops-theme';

  function apply(theme) {
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    document.querySelectorAll('[data-theme-set]').forEach(function (b) {
      b.setAttribute('aria-checked', b.getAttribute('data-theme-set') === theme ? 'true' : 'false');
    });
  }

  // Signed-out pages: reflect the stored choice in the picker's checkmarks.
  if (root.getAttribute('data-theme-pref') === 'anon') {
    try { var stored = localStorage.getItem(STORE_KEY); if (stored) apply(stored); } catch (e) { /* storage blocked */ }
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-theme-set]');
    if (!btn) return;
    var theme = btn.getAttribute('data-theme-set');
    apply(theme);
    try { localStorage.setItem(STORE_KEY, theme); } catch (err) { /* storage blocked — still applies to this page */ }
    var picker = btn.closest('details');
    if (picker) picker.removeAttribute('open');
    if (root.getAttribute('data-theme-pref') === 'anon') return;
    var token = document.querySelector('meta[name="csrf-token"]');
    var body = new URLSearchParams({ theme: theme });
    fetch('/accounts/theme/', {
      method: 'POST', body: body, credentials: 'same-origin',
      headers: { 'X-CSRFToken': token ? token.content : '', 'X-Requested-With': 'fetch' }
    }).then(function (r) {
      if (!r.ok && window.toast) window.toast('Theme applied here, but could not be saved to your profile.', 'err');
    }).catch(function () {
      if (window.toast) window.toast('Theme applied here, but could not be saved to your profile.', 'err');
    });
  });

  // Close an open picker when clicking elsewhere or pressing Escape.
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.theme-picker[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('details.theme-picker[open]').forEach(function (d) { d.removeAttribute('open'); });
  });
})();
