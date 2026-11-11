# Project 002: Making the Phone App

This page is the plan for turning the Project 002 website into a phone app. It covers
the parts that are the **same for Android and iPhone**. Then there's a separate page
for each store:

- **[Android and the Google Play Store](android.md)**
- **[iPhone and the Apple App Store](iphone.md)**

Read this page first. Most of the work happens here, before either store is involved.

> **Last checked: November 2026.** The store rules change every year. Before you
> submit, check the official links on each page for the latest requirements.

---

## Contents

1. [The good news: we already have most of the app](#1-the-good-news-we-already-have-most-of-the-app)
2. [Choosing how to build the app](#2-choosing-how-to-build-the-app)
3. [Step A: Put the server on the internet](#step-a-put-the-server-on-the-internet)
4. [Step B: Make the website installable (a PWA)](#step-b-make-the-website-installable-a-pwa)
5. [Step C: Wrap the website in a real app with Capacitor](#step-c-wrap-the-website-in-a-real-app-with-capacitor)
6. [Step D: Get ready for the stores](#step-d-get-ready-for-the-stores)
7. [Who owns the accounts? (Students and age limits)](#who-owns-the-accounts-students-and-age-limits)
8. [What it costs](#what-it-costs)
9. [A possible schedule](#a-possible-schedule)

---

## 1. The good news: we already have most of the app

The website already does what the app needs to do:

- finds properties near a location ("Near me")
- shows the assessed value, exemptions and estimated taxes
- shows each property on a map, with a drawing of the lot
- fits on a phone screen

So we don't need to start over. The plan is to **reuse the website's code** inside the
app, then add the things that make it feel like a real phone app.

But there's one big problem to solve first:

> **The website only runs on one computer right now.** The server runs at
> `http://localhost:8000`, and "localhost" means *this computer*. A phone can't reach
> it. Before anything else, the server has to go on the internet (Step A).

---

## 2. Choosing how to build the app

There are several ways to make a phone app. Here are the main choices:

| Approach | Language | One codebase for both phones? | Reuses our website code? | Notes |
|---|---|---|---|---|
| **PWA** (Progressive Web App) | HTML, CSS, JavaScript | Yes | **Yes, almost all of it** | Installs from the browser. Not in the app stores. Free. |
| **Capacitor** | HTML, CSS, JavaScript | Yes | **Yes, most of it** | Wraps the website in a real app that can go in both stores. |
| React Native / Expo | JavaScript (React) | Yes | Some logic only | The screens have to be rewritten in React. |
| Flutter | Dart | Yes | No | A new language to learn. Rewrite everything. |
| Native (Kotlin for Android, Swift for iPhone) | Two languages | **No, two separate apps** | No | The most work. Best performance. |
| MIT App Inventor | Blocks | Android mostly | No | Great for learning, but hard to rebuild this app with it. |

### Our recommendation

1. **Start with a PWA (Step B).** It's quick, free and needs no store approval, and
   people can install it on Android *and* iPhone. Students can build it with the
   HTML and JavaScript they're already learning from the website.
2. **Then use Capacitor (Step C)** to turn the same code into real Android and iPhone apps
   for the stores.

This way the class writes **one set of code** that works on the web, on Android and
on iPhone.

---

## Step A: Put the server on the internet

The app needs a server it can reach from anywhere. That means:

1. **Rent a small server** from a cloud company. A small Linux server is plenty.
   Prices start around $5–$20 a month.
2. **Copy the code and the database there.** The database (`property.db`) is about
   250 MB. It's too big for GitHub, so copy it to the server separately, or rebuild
   it there with `build_db.py`.
3. **Get a web address (a domain name)**, for example `project002.example.org`. A domain
   costs about $10–$20 a year.
4. **Turn on HTTPS** (the padlock in the browser). Both app stores and the phone's
   location feature require HTTPS. Free certificates are available from
   [Let's Encrypt](https://letsencrypt.org/).
5. **Make the server production-ready.** `server.py` is a simple learning server.
   On the internet it should run behind a real web server, such as nginx or Caddy,
   which handles HTTPS and lots of visitors at once.

> **Ask an adult or a mentor to help with this step.** A server on the internet has to
> be kept updated and secure.

### Check before going public

- **Data terms.** Check the St. Lucie County Property Appraiser's terms of use, and
  make sure it's OK to republish their data in an app.
- **Map pictures (tiles).** The website gets map pictures from OpenStreetMap and Esri.
  OpenStreetMap's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
  doesn't allow heavy use by apps without permission. Esri's satellite imagery has its
  own terms, and an app may need an account. For a published app, plan to use a map
  provider whose terms allow it. Many have a free tier.
- **Owner names.** Property owner names are public records in Florida. Still, decide
  whether the app *needs* to show them. Showing less personal information is safer
  and makes the store privacy forms simpler.

---

## Step B: Make the website installable (a PWA)

A **Progressive Web App** is a website that can be installed like an app. It gets an
icon on the home screen, opens full-screen, and can work partly offline.

It needs three things:

### 1. A manifest file

`manifest.json` tells the phone the app's name, icon and colors:

```json
{
  "name": "Project 002 Property Taxes",
  "short_name": "Project 002",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#0b6e69",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

`"display": "standalone"` means it opens without the browser's address bar, so it looks
like an app.

Link the manifest from `index.html`:

```html
<link rel="manifest" href="/manifest.json">
<!-- iPhones use this tag for the home screen icon -->
<link rel="apple-touch-icon" href="/icons/icon-192.png">
```

### 2. A service worker

A **service worker** is a small JavaScript file that runs in the background. It can save
copies of the app's files on the phone so the app opens fast, even with a weak signal:

```javascript
// sw.js: save the app's main files so it opens fast, even with a weak signal.
const CACHE = "project002-v1";   // change the number to v2, v3... when the files change
const FILES = ["/", "/app.js", "/map.js", "/style.css"];

// "install" runs once, when the phone first sees this service worker.
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(FILES)));
});

// "fetch" runs every time the app asks for a file.
self.addEventListener("fetch", (event) => {
  // Data from /api/ should always be fresh, so let those requests go straight to the server.
  if (event.request.url.includes("/api/")) return;
  // For everything else, use the saved copy if there is one. Otherwise, download it.
  event.respondWith(
    caches.match(event.request).then((saved) => saved || fetch(event.request))
  );
});
```

Turn it on from `app.js`:

```javascript
// Not every browser supports service workers, so check first.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
```

### 3. HTTPS

Service workers only work over HTTPS (or on `localhost` for testing). That's another
reason Step A matters.

### How people install it

- **Android (Chrome):** Chrome shows an **Install app** prompt, or use the menu (⋮) →
  **Add to Home screen**.
- **iPhone (Safari):** Tap the **Share** button → **Add to Home Screen**.

---

## Step C: Wrap the website in a real app with Capacitor

[Capacitor](https://capacitorjs.com/) takes a website and puts it inside a real Android
app and a real iPhone app. Each app shows the website's pages, but it's a real app
that can go in the stores and use phone features.

### What you need

- **Node.js** (the LTS version) from [nodejs.org](https://nodejs.org/). It isn't
  installed on our project computer yet.
- For Android: **Android Studio** (works on Windows, Mac or Linux)
- For iPhone: **a Mac with Xcode** (see the [iPhone page](iphone.md))

### Setting it up

Run these commands in a terminal, in a new `app/` folder:

```bash
# 1. Start a Node.js project and install Capacitor
npm init -y
npm install @capacitor/core @capacitor/cli

# 2. Create the Capacitor settings.
#    "Project 002" is the app's name.
#    "org.example.project002" is the app ID. Pick it carefully: you can NEVER change it
#    after the app is in a store. It's usually your website address written backwards.
npx cap init "Project 002" org.example.project002 --web-dir www

# 3. Copy the website files (index.html, app.js, map.js, style.css) into the www/ folder

# 4. Add the phone platforms
npm install @capacitor/android @capacitor/ios
npx cap add android
npx cap add ios          # this one only works on a Mac

# 5. Every time you change the website files, copy them into the phone projects:
npx cap sync
```

### Changes the website code needs

1. **Use the full server address.** On the website, `fetch("/api/properties")` works
   because the page and the server are at the same address. Inside the app, it needs
   the full internet address:

   ```javascript
   // On the website this is "" (same address). In the app it's the real server.
   const API = "https://project002.example.org";

   const res = await fetch(API + "/api/properties?" + params);
   ```

   The server also has to allow requests from the app. This is called **CORS**: the
   server sends an `Access-Control-Allow-Origin` header listing who may use it.

2. **Use the phone's real GPS for "Near me."** Capacitor has a Geolocation plugin:

   ```javascript
   import { Geolocation } from "@capacitor/geolocation";

   async function findMe() {
     // The first time, the phone asks the user for permission.
     const pos = await Geolocation.getCurrentPosition();
     setNear(pos.coords.latitude, pos.coords.longitude, "My location");
   }
   ```

3. **Put the files in the app.** Ship `index.html`, the JavaScript and the CSS
   inside the app, instead of loading the website from the internet. This makes the
   app open faster, and Apple prefers it (see [the iPhone page](iphone.md#why-apple-might-say-no)).

### Ideas that make it feel like a real app

The stores, Apple especially, want apps to do more than show a website:

- **Favorites:** save properties you're watching, stored on the phone
- **"Near me" on launch:** open straight to properties around you
- **Share button:** share a property with the phone's share sheet (`@capacitor/share`)
- **Offline mode:** show your saved favorites with no signal
- **Tax calculator:** "What if my home's value went up 10%?"

These are great projects for students.

---

## Step D: Get ready for the stores

Both stores ask for the same kinds of things. Get them ready before you start:

| Item | What it is |
|---|---|
| **App name** | Up to 30 characters on both stores |
| **App icon** | A square picture: 512×512 for Google and 1024×1024 for Apple. No transparency on Apple. |
| **Screenshots** | Pictures of the app running on a phone. Each store has its own required sizes. |
| **Description** | What the app does and who it's for |
| **Privacy policy** | **Required by both stores.** A web page that says what data the app collects and why. Ours would cover location (to find nearby homes), and say we don't sell data or track people. |
| **Support page or email** | Where people can ask for help |
| **Privacy answers** | Google's "Data safety" form and Apple's "App Privacy" labels: what data the app collects and how it's used |
| **Age rating** | A questionnaire about the app's content. Our app should get the lowest rating. |
| **Disclaimer** | **Important:** the app must **not** look like an official government app. Say in the description and in the app: *"Not affiliated with the St. Lucie County Property Appraiser or Tax Collector. Tax amounts are estimates."* Both stores reject apps that look like they're from the government when they aren't. |

---

## Who owns the accounts? (Students and age limits)

Both stores require developer account owners to be **adults (18 or older)**:

- An **adult** (the teacher or the organization) creates and owns the Google Play and
  Apple developer accounts, and clicks **Submit**.
- **Students** write the code, design the screens, make the screenshots, write the
  description and test the app.
- **Organization accounts** are worth considering. The app is published under the
  organization's name instead of a person's. Apple also offers
  [fee waivers](https://developer.apple.com/help/account/membership/fee-waivers/)
  to nonprofits and accredited schools. Both stores ask an organization for a
  **D-U-N-S number**, a free business ID from Dun & Bradstreet. It can take a few
  weeks to get, so **apply early**.
- Some steps happen on the **adult's computer**: signing keys, passwords and account
  logins. Keep these private and backed up.

---

## What it costs

| Item | Cost |
|---|---|
| PWA (Step B) | Free |
| Capacitor, Android Studio, Xcode | Free |
| Google Play developer account | **$25 once** |
| Apple Developer Program | **$99 per year** (nonprofits and schools can ask for a fee waiver) |
| Server hosting | About $5–$20 per month |
| Domain name | About $10–$20 per year |
| A Mac, needed for iPhone builds | Use one you have, buy a used Mac mini, or rent a Mac in the cloud |
| Map tiles | Often free at small sizes. Check the provider's limits. |

---

## A possible schedule

| Weeks | Goal |
|---|---|
| 1–2 | Design the app on paper: what screens, what buttons? |
| 2–4 | Put the server online (Step A). Make the PWA (Step B). |
| 4–7 | Build the Capacitor app (Step C). Add GPS and favorites. Test it on phones. |
| 6–7 | Start the store accounts. Ask for a D-U-N-S number early if you're using an organization. |
| 7–9 | Android: closed testing. Personal accounts need **14 days** of testing (see [Android](android.md)). |
| 7–9 | iPhone: TestFlight testing (see [iPhone](iphone.md)). |
| 9–10 | Make screenshots, write descriptions and submit to both stores. |

Next: **[Android and Google Play →](android.md)** or **[iPhone and the App Store →](iphone.md)**
