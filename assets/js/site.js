/* =========================================================
   Mama's Mwiko — site behaviour
   No dependencies. Safe to load with `defer`.
   ========================================================= */
(function () {
  'use strict';

  /* ---------------------------------------------------------
     CONFIG — edit these two values and the whole site follows.
     Hours are in 24h Nairobi time. Use null for a closed day.
     --------------------------------------------------------- */
  var PHONE_INTL = '254791755663';           // WhatsApp / tel, no plus sign
  var TIMEZONE   = 'Africa/Nairobi';
  var HOURS = {
    0: { open: '08:00', close: '21:30' },    // Sunday
    1: { open: '08:00', close: '21:30' },
    2: { open: '08:00', close: '21:30' },
    3: { open: '08:00', close: '21:30' },
    4: { open: '08:00', close: '21:30' },
    5: { open: '08:00', close: '21:30' },
    6: { open: '08:00', close: '21:30' }     // Saturday
  };

  var DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  /* ---------------------------------------------------------
     Helpers
     --------------------------------------------------------- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function toMinutes(hhmm) {
    var parts = hhmm.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  function to12h(hhmm) {
    var m = toMinutes(hhmm), h = Math.floor(m / 60), mm = m % 60;
    var suffix = h >= 12 ? 'pm' : 'am';
    var h12 = h % 12 === 0 ? 12 : h % 12;
    return h12 + (mm ? ':' + String(mm).padStart(2, '0') : '') + suffix;
  }

  /* Current day + minute-of-day in Nairobi, whatever the visitor's timezone. */
  function nowInNairobi() {
    var d = new Date();
    try {
      var fmt = new Intl.DateTimeFormat('en-GB', {
        timeZone: TIMEZONE, weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false
      });
      var parts = {};
      fmt.formatToParts(d).forEach(function (p) { parts[p.type] = p.value; });
      var weekdayIndex = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(parts.weekday);
      var hour = parseInt(parts.hour, 10) % 24;
      var minute = parseInt(parts.minute, 10);
      if (weekdayIndex > -1 && !isNaN(hour) && !isNaN(minute)) {
        return { day: weekdayIndex, minutes: hour * 60 + minute };
      }
    } catch (e) { /* Intl unsupported — fall through to local time */ }
    return { day: d.getDay(), minutes: d.getHours() * 60 + d.getMinutes() };
  }

  /* ---------------------------------------------------------
     Open / closed status pill
     --------------------------------------------------------- */
  function renderStatus() {
    var nodes = $$('#openStatus');
    if (!nodes.length) return;

    var now = nowInNairobi();
    var today = HOURS[now.day];
    var isOpen = false, label;

    if (today) {
      var openM = toMinutes(today.open), closeM = toMinutes(today.close);
      if (now.minutes >= openM && now.minutes < closeM) {
        isOpen = true;
        label = now.minutes >= closeM - 60
          ? 'Open · closing at ' + to12h(today.close)
          : 'Open now · until ' + to12h(today.close);
      } else if (now.minutes < openM) {
        label = 'Closed · opens ' + to12h(today.open);
      }
    }

    if (!isOpen && !label) {
      // Find the next day we are open.
      for (var i = 1; i <= 7; i++) {
        var slot = HOURS[(now.day + i) % 7];
        if (slot) {
          label = 'Closed · opens ' + (i === 1 ? 'tomorrow' : DAY_NAMES[(now.day + i) % 7]) +
                  ' at ' + to12h(slot.open);
          break;
        }
      }
    }

    nodes.forEach(function (el) {
      el.textContent = label || 'See opening hours';
      el.classList.remove('status--loading');
      el.classList.add(isOpen ? 'status--open' : 'status--closed');
    });
  }

  /* ---------------------------------------------------------
     Highlight today's row in the hours table
     --------------------------------------------------------- */
  function highlightToday() {
    var table = $('#hoursTable');
    if (!table) return;
    var todayName = DAY_NAMES[nowInNairobi().day];
    $$('tr', table).forEach(function (row) {
      var th = $('th', row);
      if (th && th.textContent.trim() === todayName) row.classList.add('is-today');
    });
  }

  /* ---------------------------------------------------------
     Mobile navigation
     --------------------------------------------------------- */
  function initNav() {
    var toggle = $('#navToggle'), nav = $('#nav');
    if (!toggle || !nav) return;

    function close() {
      nav.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open menu');
    }

    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    });

    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') close();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) { close(); toggle.focus(); }
    });
  }

  /* ---------------------------------------------------------
     Header shadow once the page scrolls
     --------------------------------------------------------- */
  function initStickyHeader() {
    var header = $('#siteHeader');
    if (!header || header.classList.contains('site-header--solid')) return;
    var tick = false;
    function update() {
      header.classList.toggle('is-stuck', window.scrollY > 8);
      tick = false;
    }
    window.addEventListener('scroll', function () {
      if (!tick) { tick = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* ---------------------------------------------------------
     Booking form -> pre-filled WhatsApp message
     (no backend, nothing stored in the browser)
     --------------------------------------------------------- */
  function initBookingForm() {
    var form = $('#bookingForm');
    if (!form) return;
    var note = $('#formNote');
    var defaultNote = note ? note.textContent : '';

    // Don't let anyone book yesterday.
    var dateField = $('#bDate');
    if (dateField) {
      var t = new Date();
      var iso = t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' +
                String(t.getDate()).padStart(2, '0');
      dateField.min = iso;
      if (!dateField.value) dateField.value = iso;
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();

      var required = ['#bName', '#bDate', '#bTime', '#bGuests'];
      var firstBad = null;
      required.forEach(function (sel) {
        var el = $(sel);
        var bad = !el.value.trim();
        el.setAttribute('aria-invalid', bad ? 'true' : 'false');
        if (bad && !firstBad) firstBad = el;
      });

      if (firstBad) {
        if (note) { note.textContent = 'Please fill in your name, date, time and number of guests.'; note.classList.add('is-error'); }
        firstBad.focus();
        return;
      }

      if (note) { note.textContent = defaultNote; note.classList.remove('is-error'); }

      var seating = $('#bSeating') ? $('#bSeating').value : '';
      var notes = $('#bNotes') ? $('#bNotes').value.trim() : '';

      var lines = [
        'Hello Mama’s Mwiko, I’d like to book a table.',
        '',
        'Name: ' + $('#bName').value.trim(),
        'Date: ' + $('#bDate').value,
        'Time: ' + $('#bTime').value,
        'Guests: ' + $('#bGuests').value
      ];
      if (seating && seating !== 'No preference') lines.push('Seating: ' + seating);
      if (notes) lines.push('Notes: ' + notes);

      var url = 'https://wa.me/' + PHONE_INTL + '?text=' + encodeURIComponent(lines.join('\n'));
      window.open(url, '_blank', 'noopener');
    });
  }

  /* ---------------------------------------------------------
     Swap the placeholder illustrations for real photos.

     Each slot carries data-photo="<path>". If that file loads, it
     replaces the illustration; if it is missing, the illustration
     simply stays. So dropping photos into assets/img/photos/ is all
     it takes — no HTML to edit, and never a broken image.
     --------------------------------------------------------- */
  function upgradeToPhotos() {
    $$('img[data-photo]').forEach(function (img) {
      var probe = new Image();
      probe.onload = function () {
        img.src = img.dataset.photo;
        if (img.dataset.photoAlt) img.alt = img.dataset.photoAlt;
        img.classList.add('is-photo');
      };
      probe.src = img.dataset.photo;
    });
  }

  /* ---------------------------------------------------------
     Misc
     --------------------------------------------------------- */
  function setYear() {
    $$('#year').forEach(function (el) { el.textContent = String(new Date().getFullYear()); });
  }

  renderStatus();
  highlightToday();
  upgradeToPhotos();
  initNav();
  initStickyHeader();
  initBookingForm();
  setYear();

  // Keep the status pill honest on long-lived tabs.
  setInterval(renderStatus, 60000);
})();
