# Project 002: iPhone App and the Apple App Store

This page covers building the iPhone version of the app and publishing it on the
**Apple App Store**. Read the **[phone app plan](README.md)** first. It covers putting the
server online and setting up Capacitor, which both phones share.

> **Last checked: November 2026.** Apple changes its requirements every year. Check
> the [App Store submission page](https://developer.apple.com/app-store/submitting/)
> and the [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
> before you submit.

---

## Contents

1. [What you need (yes, you need a Mac)](#1-what-you-need-yes-you-need-a-mac)
2. [Install Xcode](#2-install-xcode)
3. [Run the app in the iPhone Simulator](#3-run-the-app-in-the-iphone-simulator)
4. [Run the app on a real iPhone (free)](#4-run-the-app-on-a-real-iphone-free)
5. [Set the app's details](#5-set-the-apps-details)
6. [Join the Apple Developer Program](#6-join-the-apple-developer-program)
7. [Create the app in App Store Connect](#7-create-the-app-in-app-store-connect)
8. [Upload a build](#8-upload-a-build)
9. [Test with TestFlight](#9-test-with-testflight)
10. [Fill in the store listing](#10-fill-in-the-store-listing)
11. [Submit for App Review](#11-submit-for-app-review)
12. [Why Apple might say no](#why-apple-might-say-no)
13. [Sending updates](#13-sending-updates)

---

## 1. What you need (yes, you need a Mac)

| Need | Notes |
|---|---|
| **A Mac** | Apple's tool for building iPhone apps, **Xcode, only runs on a Mac**. Our Windows computer can't build the iPhone app. |
| Xcode | Free from the Mac App Store |
| Node.js and Capacitor | See [Step C of the plan](README.md#step-c-wrap-the-website-in-a-real-app-with-capacitor) |
| An iPhone | Optional but very useful for testing |
| Apple Developer Program membership | **$99 a year**, needed to publish. It must be owned by an adult (18+). Schools and nonprofits can ask for a fee waiver. |

### No Mac? Here are some options

- **Borrow one.** A school, library or volunteer might have a Mac you can use.
- **Buy a used Mac mini.** It's the least expensive Mac, and an older one is fine if it
  runs the latest Xcode.
- **Rent a Mac in the cloud.** Several companies rent Macs by the hour or month, and you
  use them from a Windows computer over the internet.
- **Use a cloud build service.** Some services build the iPhone app on their own Macs
  for you. Ionic Appflow is made for Capacitor apps, and Codemagic is another option.
  You still need the Apple developer account.

**Tip:** Do the Android version first on the Windows computer ([Android page](android.md)).
Almost all the code is shared, so by the time you get to a Mac, most of the work is done.

---

## 2. Install Xcode

1. On the Mac, open the **App Store**, search for **Xcode** and install it. It's large
   (many gigabytes), so give it time.
2. Open Xcode once so it can install its extra parts. Accept the license.
3. In your Capacitor project (copied to the Mac, or cloned from GitHub), run:

   ```bash
   npm install
   npx cap sync ios       # copy the latest website files into the iPhone project
   npx cap open ios       # open the iPhone project in Xcode
   ```

> **Xcode version rule:** Since April 28, 2026, apps uploaded to the App Store must be
> built with **Xcode 26 or newer**, using the iOS 26 SDK. Apple raises this every
> spring, so always use the newest Xcode for builds you upload.

---

## 3. Run the app in the iPhone Simulator

The **Simulator** is a pretend iPhone that runs on the Mac.

1. In Xcode, pick a simulator (for example, "iPhone 17") from the device menu at the top.
2. Click the **▶ Run** button. The Simulator opens, and the app starts.

**Tip:** To test "Near me," use the Simulator menu: **Features → Location → Custom
Location...**, then enter a spot in Port St. Lucie or Fort Pierce.

---

## 4. Run the app on a real iPhone (free)

You can put the app on your own iPhone **without paying** for the developer program.
You only need a free Apple Account.

1. In Xcode, go to **Settings → Accounts**, click **+**, and sign in with an Apple Account.
2. Click the project in the left sidebar → **Signing & Capabilities** tab → turn on
   **Automatically manage signing**, and pick your account as the **Team**.
3. Plug in the iPhone with a cable, and tap **Trust** on the phone.
4. On the iPhone, turn on **Developer Mode**: **Settings → Privacy & Security →
   Developer Mode**. The phone restarts.
5. Pick your iPhone in Xcode's device menu, and click **▶ Run**.

> With a free account, the app **stops working after 7 days**. Just run it from
> Xcode again. Paid accounts don't have this limit.

---

## 5. Set the app's details

In Xcode, click the project → the **App** target.

### Bundle Identifier

This is the `org.example.project002` you picked during `npx cap init`. It's the app's
permanent ID with Apple, and **it can't change** after you create the app in
App Store Connect.

### Location permission message

iPhones make every app explain *why* it wants the user's location. Without this
message, the app crashes when it asks for location, and Apple will reject it.

Open `ios/App/App/Info.plist` and add:

```xml
<!-- The message the iPhone shows when the app asks for location. -->
<!-- Apple checks this message: it must say clearly WHY the app needs location. -->
<key>NSLocationWhenInUseUsageDescription</key>
<string>Project 002 uses your location to show property taxes for homes near you.</string>
```

> Only ask for "When In Use" location. Our app doesn't need location when it's closed,
> and asking for more than it needs is a common reason for rejection.

### Encryption question

Apple asks every app about encryption. Our app only uses normal HTTPS, so add this
to `Info.plist` to answer the question automatically:

```xml
<!-- We only use standard HTTPS, so the app is exempt from export paperwork. -->
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

### Version numbers

On the **General** tab:

- **Version** (for example, `1.0`) is what people see in the App Store.
- **Build** (for example, `1`) must go up with every upload: 1, 2, 3...

### App icon

In Xcode, open `Assets` → **AppIcon** and drop in a **1024 × 1024** PNG. It must have
**no transparency** and no rounded corners, because the iPhone rounds the corners
itself.

---

## 6. Join the Apple Developer Program

An **adult (18+)** joins on behalf of the project. Go to
[developer.apple.com/programs/enroll](https://developer.apple.com/programs/enroll/).

| | Individual | Organization |
|---|---|---|
| Who | One person | A business, school or nonprofit that is a legal entity |
| Needs | An Apple Account with two-factor authentication | A **D-U-N-S number**, a website, and someone with authority to sign for the organization |
| Name in the App Store | The person's name | The organization's name |
| Cost | $99 a year | $99 a year, or **free with a fee waiver** for eligible nonprofits and accredited schools |

For a school project, an **organization** membership is usually best. The app shows the
organization's name, and the team can add other adults later. Ask about the
[fee waiver](https://developer.apple.com/help/account/membership/fee-waivers/), and start
early: getting a D-U-N-S number and approval can take a few weeks.

---

## 7. Create the app in App Store Connect

**App Store Connect** ([appstoreconnect.apple.com](https://appstoreconnect.apple.com)) is
the website where you manage the app.

1. Go to **Apps** → **+** → **New App**.
2. Fill in:
   - **Platform:** iOS
   - **Name:** up to 30 characters. It must not already be taken in the App Store.
   - **Primary language:** English (U.S.)
   - **Bundle ID:** choose `org.example.project002`. If it isn't in the list, register
     it under **Certificates, Identifiers & Profiles → Identifiers**.
   - **SKU:** any private ID you like, for example `project002`.

---

## 8. Upload a build

1. In Xcode, pick **Any iOS Device (arm64)** from the device menu, not a simulator.
2. Choose **Product → Archive**. Xcode builds the release version.
3. When the **Organizer** window opens, pick the archive → **Distribute App** →
   **App Store Connect** → **Upload**. Xcode handles signing automatically.
4. After about 5–30 minutes, the build appears in App Store Connect under **TestFlight**.

---

## 9. Test with TestFlight

**TestFlight** is Apple's app for testing beta versions. Testers install the TestFlight
app from the App Store, then install your app through it.

| Tester type | How many | Review? |
|---|---|---|
| **Internal testers** | Up to 100 people on your App Store Connect team | No. Ready right away. |
| **External testers** | Up to 10,000 people, invited by email or a public link | Yes. The first build gets a short "Beta App Review." |

Apple doesn't require a minimum testing period like Google does, but testing is still
very important. Have the students and their families try it, and keep a list of bugs.

Each TestFlight build works for **90 days**.

---

## 10. Fill in the store listing

In App Store Connect, open the app and fill in the version page:

| Item | Notes |
|---|---|
| **Name and subtitle** | Up to 30 characters each. Sample subtitle: *St. Lucie County tax estimates* |
| **Description** | What the app does. Include the **"not affiliated with the county" disclaimer**. |
| **Keywords** | Up to 100 characters, separated by commas: `property tax,St. Lucie,homestead,millage,Florida` |
| **Screenshots** | Required for the iPhone sizes App Store Connect lists (the largest iPhone size, at least). Take them in the Simulator with **File → Save Screen** (⌘S). |
| **Support URL** | A web page where people can get help |
| **Privacy Policy URL** | Required ([plan, Step D](README.md#step-d-get-ready-for-the-stores)) |
| **App Privacy** | The privacy "nutrition label." For our app, say **Location (precise and coarse)** is used for **App Functionality**, is **not linked to the user's identity**, and is **not used for tracking**. |
| **Age rating** | Answer the questionnaire. Our app has no mature content. |
| **Category** | Utilities, or Reference |
| **Price** | Free |

**Student job:** Make the screenshots, write the description, and pick the keywords.

---

## 11. Submit for App Review

1. On the version page, choose the build you uploaded.
2. Fill in **App Review Information**:
   - contact details for the adult in charge
   - **Notes for the reviewer**: explain what the app does, where the data comes
     from, and that it's a student project. For example:

     > *Project 002 is an educational after-school project built by 8th grade students.
     > It shows estimated property taxes for St. Lucie County, Florida, using public
     > records from the county Property Appraiser. It is not affiliated with any
     > government office. To try "Near me," set the device location to Port St. Lucie, FL.
     > No login is required.*

3. Click **Add for Review → Submit**.
4. Most reviews finish in **about a day or two**. You'll get an email.
5. When it's approved, release the app. It shows up in the App Store within a few hours. 🎉

---

## Why Apple might say no

Apple reviews every app carefully. These are the most likely problems for **our** app,
and how to avoid them:

| Guideline | The problem | How to avoid it |
|---|---|---|
| **4.2: Minimum functionality** | Apple rejects apps that are "just a website in an app." | Add real app features: GPS "Near me," **favorites saved on the phone**, sharing, offline mode. Put the HTML/JS files inside the app instead of loading the website. (See [plan, Step C](README.md#ideas-that-make-it-feel-like-a-real-app).) |
| **5.1.1: Data collection** | Asking for location without a clear reason, or asking for more data than needed | A clear location message. "When In Use" only. No login unless it's really needed. |
| **5.1.1: Privacy policy** | No privacy policy, or one that doesn't match the app | Write a short, honest privacy policy, and link it in the app too. |
| **Misleading government affiliation** | The app looks like it's from the county | Use our own name and logo. Don't use county seals. Add a clear "not affiliated" disclaimer. |
| **2.1: App completeness** | Crashes, broken links, or the server is down during review | Test well. Make sure the server is running while Apple reviews. |

If the app is rejected, Apple explains why in **App Store Connect → Resolution Center**.
Fix the problem, upload a new build (raise the Build number), and resubmit. You can
also reply to explain something the reviewer may have misunderstood.

---

## 13. Sending updates

1. Make changes in the website code, then run `npx cap sync ios`.
2. In Xcode, raise the **Build** number (and the **Version** if it's a new release).
3. **Product → Archive → Distribute App**, same as before.
4. Test it in TestFlight, then create a new version in App Store Connect and submit it.

Also remember:

- **Renew the $99 membership every year**, unless you have a fee waiver. If it lapses,
  the app is removed from the App Store.
- Apple requires a **newer Xcode every spring**. Plan to rebuild at least once a year.

---

## Quick checklist

- [ ] A Mac with the latest Xcode (or a cloud build service)
- [ ] Server online with HTTPS ([plan, Step A](README.md#step-a-put-the-server-on-the-internet))
- [ ] App runs in the Simulator and on a real iPhone
- [ ] Location message added to `Info.plist`, and "Near me" works
- [ ] Bundle ID chosen (it's permanent!)
- [ ] 1024 × 1024 app icon with no transparency
- [ ] Apple Developer Program joined by an adult (ask about the fee waiver)
- [ ] App created in App Store Connect
- [ ] Build archived and uploaded
- [ ] TestFlight testing done
- [ ] Privacy policy and support pages online
- [ ] Store listing done (screenshots, description, keywords, App Privacy, age rating)
- [ ] Reviewer notes written → submitted → approved → released!

← Back to the **[phone app plan](README.md)** · See also: **[Android and Google Play](android.md)**
