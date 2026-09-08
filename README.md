# Mama's Mwiko — Restaurant Website

A fast, mobile-first marketing site for **Mama's Mwiko**, Azalea Square, General
Mathenge Drive, Nairobi. Built to turn searches and map listings into phone
calls, bookings and walk-ins.

Plain HTML, CSS and vanilla JavaScript — no build step, no framework, no
dependencies. Open `index.html` in a browser and it works.

---

## ⚠️ Read this before publishing

The site is complete and ready to deploy, but **some content is placeholder and
must be confirmed by the owner first.** Only the facts below came from the
business listing; everything else was written to fill the page.

### Confirmed from the listing (safe as-is)

| | |
|---|---|
| Name | Mama's Mwiko |
| Address | Azalea Square, Ground Floor, General Mathenge Drive, Nairobi |
| Phone | 0791 755663 (`+254791755663`) |
| Rating | 4.8 from 36 Google reviews |
| Price band | Ksh 1,000–1,500 per person |
| Features | Outdoor seating, vegetarian options |
| Closing time | 9:30 pm |

### Placeholder — replace before going live

1. **Every menu item and price** (`menu.html`, plus the three cards in
   `index.html`). These are representative Kenyan dishes with prices chosen to
   fit the Ksh 1,000–1,500 band. They are **not** the real menu. Publishing
   prices that aren't yours will annoy customers at the till.
2. **Opening times.** Only the 9:30 pm close is known. The site currently claims
   **8:00 am – 9:30 pm, seven days a week**. Fix it in two places (see
   *Changing opening hours* below).
3. **Photography.** All images are hand-drawn SVG stand-ins. Real photos of the
   food and the courtyard are the single biggest conversion win on a restaurant
   site — swap them in first. **Drop them into `assets/img/photos/` using the
   filenames in that folder's README and they appear automatically**; there is
   no HTML to edit, and a missing photo just leaves the illustration in place.
4. **The "Our Story" copy** in `index.html` is written from the name (a *mwiko*
   is the wooden cooking spoon) and is plausible, not sourced. Rewrite it in the
   owner's own words.
5. **The domain.** `https://mamasmwiko.co.ke/` is used in the canonical tag,
   Open Graph tags, `sitemap.xml` and `robots.txt`. Find-and-replace it with the
   real domain.

No fake customer testimonials were invented. The reviews section shows only the
real aggregate (4.8 / 36) and links out to Google.

---

## Files

```
index.html            Home: hero, highlights, story, signature plates,
                      booking form, reviews, hours + map
menu.html             Full menu, with sticky section jump-links
assets/css/styles.css One stylesheet; design tokens at the top
assets/js/site.js     Nav, live open/closed status, booking form
assets/img/*.svg      Placeholder artwork (see above)
robots.txt            Points crawlers at the sitemap
sitemap.xml           Two URLs
.nojekyll             Stops GitHub Pages running content through Jekyll
```

## What it does

- **Live open/closed pill** — computed in **Africa/Nairobi** time, so a visitor
  in London still sees the right answer. Shows "Open now · until 9:30pm",
  "closing at 9:30pm" in the last hour, or when we next open.
- **Today's row highlighted** in the opening-hours table.
- **Booking form → WhatsApp.** No backend and no database: the form assembles a
  pre-filled message and opens `wa.me/254791755663`. Nothing is stored.
- **Sticky call bar on mobile** — Call / Menu / Directions always one thumb away.
- **SEO groundwork** — `Restaurant` JSON-LD with address, phone, hours, price
  range and the 4.8/36 aggregate rating, so Google can show the rich result;
  plus canonical, Open Graph and Twitter card tags.
- **Accessibility** — skip link, visible focus rings, labelled form fields,
  keyboard-dismissable menu, `prefers-reduced-motion` respected.
- **No third-party JavaScript.** The only external requests are Google Fonts and
  the map iframe.

## Editing

### Changing opening hours

Two places, both need updating:

1. `assets/js/site.js` — the `HOURS` object near the top. 24-hour times, `null`
   for a closed day. This drives the live status pill.
2. `index.html` — the `<table id="hoursTable">` rows, and the
   `openingHoursSpecification` block in the JSON-LD at the bottom.

### Changing the phone number

Search for `254791755663` (links) and `0791 755663` (display text) across
`index.html`, `menu.html` and `assets/js/site.js`.

### Changing colours or type

All tokens live in `:root` at the top of `assets/css/styles.css` — palette,
radii, shadows, fonts. Change them there rather than hunting through rules.

### Adding real photos

Put them in `assets/img/photos/` with these exact names — nothing else to do:

| Filename | Where | Shape |
|---|---|---|
| `hero.jpg` | Behind the headline | Landscape 16:9 |
| `story.jpg` | Beside "The mwiko never lies" | Portrait 4:5 |
| `nyama-choma.jpg` | Signature plates, card 1 | Landscape 4:3 |
| `kuku-kienyeji.jpg` | Signature plates, card 2 | Landscape 4:3 |
| `managu-ugali.jpg` | Signature plates, card 3 | Landscape 4:3 |

`upgradeToPhotos()` in `assets/js/site.js` probes each file and swaps it in only
once it has loaded, so the page never flashes a broken image and works fine with
photos missing. Alt text for each photo lives in the slot's `data-photo-alt`
attribute in `index.html`. See `assets/img/photos/README.md` for shooting and
sizing notes.

**Note on link previews:** `og:image` currently points at an SVG. WhatsApp,
Facebook and X will not render an SVG preview — replace it with a 1200×630
JPEG or PNG before sharing the link anywhere.

## Running locally

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

Opening `index.html` directly with `file://` also works, though the map iframe
behaves better over HTTP.

## Deploying

Any static host works — GitHub Pages, Netlify, Cloudflare Pages, or plain
shared hosting via FTP. There is nothing to build.

For **GitHub Pages**: Settings → Pages → Deploy from a branch → pick this
branch, folder `/ (root)`. Then point the real domain at it and update the URLs
listed in the placeholder section above.
