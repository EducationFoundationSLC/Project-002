# Project 002: Android App and the Google Play Store

This page covers building the Android version of the app and publishing it on
**Google Play**. Read the **[phone app plan](README.md)** first. It covers putting the
server online and setting up Capacitor, which both phones share.

> **Last checked: November 2026.** Google changes its requirements every year.
> Check the [Play Console Help Center](https://support.google.com/googleplay/android-developer/)
> before you submit.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Install Android Studio](#2-install-android-studio)
3. [Run the app on an emulator](#3-run-the-app-on-an-emulator)
4. [Run the app on a real Android phone](#4-run-the-app-on-a-real-android-phone)
5. [Set the app's details](#5-set-the-apps-details)
6. [Build a signed release](#6-build-a-signed-release)
7. [Create the Google Play developer account](#7-create-the-google-play-developer-account)
8. [Set up the app in Play Console](#8-set-up-the-app-in-play-console)
9. [Testing: the 12-tester, 14-day rule](#9-testing-the-12-tester-14-day-rule)
10. [Publish to production](#10-publish-to-production)
11. [Sending updates](#11-sending-updates)

---

## 1. What you need

| Need | Notes |
|---|---|
| A computer | **Windows, Mac or Linux all work.** Our Windows project computer is fine. |
| Android Studio | Free from [developer.android.com/studio](https://developer.android.com/studio) |
| Node.js and Capacitor | See [Step C of the plan](README.md#step-c-wrap-the-website-in-a-real-app-with-capacitor) |
| An Android phone | Optional but very useful for testing. Any recent phone works. |
| A Google Play developer account | $25 once. It must be owned by an adult (18+). |

**Android is the easier place to start.** It works on our Windows computer and costs
less, and you can put the app on your own phone for free.

---

## 2. Install Android Studio

1. Download and install **Android Studio** from
   [developer.android.com/studio](https://developer.android.com/studio).
2. The first time you open it, the setup wizard downloads the **Android SDK**, the
   tools for building Android apps. Choose **Standard** setup.
3. In your Capacitor project, run:

   ```bash
   npx cap sync android      # copy the latest website files into the Android project
   npx cap open android      # open the Android project in Android Studio
   ```

4. The first time, Android Studio downloads more pieces (Gradle, the build tool). Let it
   finish. The bar at the bottom shows its progress.

---

## 3. Run the app on an emulator

An **emulator** is a pretend phone that runs on the computer.

1. In Android Studio, open **Device Manager** (the phone icon on the right side).
2. Click **+** → **Create Virtual Device**. Pick a phone (for example, a Pixel) and a
   recent Android version.
3. Click the green **▶ Run** button at the top. The emulator starts, and the app opens.

**Tip:** You can pretend to be anywhere. In the emulator, click **⋯ (Extended
controls)** → **Location**, then set a spot in Port St. Lucie or Fort Pierce to test
"Near me."

---

## 4. Run the app on a real Android phone

This is free and doesn't need a Play Store account.

1. On the phone, open **Settings → About phone** and tap **Build number** **7 times**.
   A message says "You are now a developer!"
2. Go to **Settings → System → Developer options** and turn on **USB debugging**.
3. Plug the phone into the computer with a USB cable. On the phone, tap **Allow** when
   it asks whether to trust this computer.
4. In Android Studio, pick your phone from the device list at the top. Then click **▶ Run**.

---

## 5. Set the app's details

These settings live in the `android/` folder that Capacitor made.

### App ID (package name)

This is the `org.example.project002` you picked during `npx cap init`. Google Play uses
it as the app's permanent ID. **It can never change** once the app is uploaded.

### Location permission

To use GPS, the app has to ask permission. Add these lines to
`android/app/src/main/AndroidManifest.xml`, inside `<manifest>`:

```xml
<!-- "Fine" means exact GPS. "Coarse" means roughly where you are. -->
<!-- The app only uses location while it's open. It never tracks in the background. -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

> Don't ask for **background** location. Our app doesn't need it, and Google has strict
> rules about it.

### Version numbers

In `android/app/build.gradle`:

```groovy
defaultConfig {
    applicationId "org.example.project002"
    versionCode 1          // a whole number. It MUST go up (2, 3, 4...) with every upload.
    versionName "1.0"      // the version people see in the store. You choose it.
    targetSdkVersion 36    // see the note below
}
```

### Target API level

Google requires new apps and updates to **target a recent version of Android**. Since
August 31, 2026, that's **Android 16 (API level 36)** or higher. Google usually raises
this every August. Check the current rule on Google's
[target API level page](https://developer.android.com/google/play/requirements/target-sdk).
New Capacitor and Android Studio versions usually set this for you.

### App icon

In Android Studio, right-click the `res` folder → **New → Image Asset**. Pick your
1024×1024 icon picture, and Android Studio makes all the sizes Android needs.

---

## 6. Build a signed release

Google Play needs an **Android App Bundle** (a `.aab` file), **signed** with your key.
A **signing key** is like a digital signature. It proves that updates come from you.

1. In Android Studio: **Build → Generate Signed App Bundle or APK** → choose
   **Android App Bundle** → **Next**.
2. Click **Create new...** to make a **keystore**, the file that holds your key.
   - Save it somewhere safe, **outside** the Git project folder.
   - Choose strong passwords and write them down somewhere safe.
3. Choose **release** and click **Create**. The `.aab` file appears in
   `android/app/release/`.

> ⚠️ **Never put the keystore or its passwords in GitHub.** Keep a backup copy, for
> example on a USB drive in a safe place. This key is the **upload key**. With **Play
> App Signing** (on by default), Google keeps the final signing key. If you lose the
> upload key, Google can reset it, but that takes time.

---

## 7. Create the Google Play developer account

The account must be created by **an adult (18+)**: the teacher or the organization.

1. Go to [play.google.com/console](https://play.google.com/console) and sign in with a
   Google account. Use a project account, not a personal Gmail.
2. Choose the account type:

   | | Personal account | Organization account |
   |---|---|---|
   | Who | One person | A business, school or nonprofit |
   | Needs | Government ID | **D-U-N-S number** plus organization details |
   | Public name | The person's name may be shown | The organization's name |
   | **14-day testing rule** | **Required** (see Step 9) | **Not required** |

   For a school project, an **organization account** is often the better choice if the
   organization can get a D-U-N-S number. Apply for one early, because it can take
   weeks.

3. Pay the **$25 one-time** registration fee.
4. Finish **identity verification**. Google checks the ID and contact details. This can
   take a few days.

> **About developer verification:** Starting in 2026, Google is requiring all Android
> developers to verify their identity, even for apps installed from outside the Play
> Store. Apps published on Google Play go through this in Play Console, so finishing
> step 4 covers it.

---

## 8. Set up the app in Play Console

1. In Play Console, click **Create app**. Enter the name, language and "App" (not game),
   and choose **Free**.
2. Go through the **Dashboard** checklist. These are the main parts:

### App content (the policy section)

| Section | What to enter for our app |
|---|---|
| **Privacy policy** | The web address of the privacy policy page ([plan, Step D](README.md#step-d-get-ready-for-the-stores)) |
| **Ads** | "No, my app does not contain ads" |
| **App access** | "All functionality is available without special access" (no login) |
| **Content rating** | Fill in the questionnaire. Our app has no violence or chat, so it should be rated for everyone. |
| **Target audience** | Choose **18 and over**. The app is for homeowners. If you pick younger ages, Google's stricter **Families** rules apply. |
| **Data safety** | Say the app collects **approximate and precise location**, used only for **app functionality** (finding nearby homes), **not shared** and **not stored**. List anything else the app collects. |
| **Government apps** | Say it is **not** a government app, and include the "not affiliated" disclaimer in the description. |

### Store listing

| Item | Size or limit |
|---|---|
| App name | Up to 30 characters |
| Short description | Up to 80 characters |
| Full description | Up to 4,000 characters |
| App icon | 512 × 512 PNG |
| Feature graphic | 1024 × 500 (the banner at the top of the listing) |
| Phone screenshots | At least 2 |

**Student job:** Make the screenshots and the feature graphic, and write the
description. Here's a sample short description:

> *Estimate property taxes for homes near you in St. Lucie County, FL.*

---

## 9. Testing: the 12-tester, 14-day rule

Google Play has several **testing tracks**:

| Track | Who can get it | Review? |
|---|---|---|
| **Internal testing** | Up to 100 people you invite by email | No. Ready in minutes. |
| **Closed testing** | People you invite (an email list or Google Group) | Yes |
| **Open testing** | Anyone who finds it in the store | Yes |
| **Production** | Everyone | Yes |

### The rule for new personal accounts

If you use a **personal** account (created after November 13, 2023), Google won't let you
publish to production until:

- you run a **closed test** with at least **12 testers**,
- who stay **opted in for 14 days in a row**.

Then you **apply for production access** and answer questions about your testing.
([Google's help page](https://support.google.com/googleplay/android-developer/answer/14151465))

**This works well for a class.** Six students plus family members and teachers can
easily reach 12. Some tips:

- Invite **more than 12**, about 15–20, in case someone drops out.
- Testers need an Android phone and a Google account. They join with the link Play
  Console gives you, then install the app from the Play Store.
- Ask testers to **actually use the app** and report bugs. Google asks what you
  learned and what you changed during testing.
- Upload a new version or two during the 14 days to show you fixed things.

Organization accounts skip this rule, but testing is still a very good idea.

### How to upload a test build

1. Play Console → **Test and release → Testing → Internal testing** (start here) →
   **Create new release**.
2. Upload the `.aab` file from Step 6.
3. Add release notes ("First test version!") and click **Save → Review release → Start rollout**.
4. Add testers on the **Testers** tab, and send them the opt-in link.

When internal testing looks good, do the same in **Closed testing**.

---

## 10. Publish to production

1. Once everything on the Dashboard is done (and, for personal accounts, Google has
   approved production access), go to **Production → Create new release**.
2. Choose the build, and add release notes.
3. Click **Send for review**. Google's review usually takes a few days. It can take
   longer for a brand-new account.
4. When it's approved, the app goes live on Google Play. 🎉

If Google rejects the app, they email the reason. Fix the problem, raise the
`versionCode`, upload again and resubmit.

---

## 11. Sending updates

1. Make changes in the website code, then run `npx cap sync android`.
2. In `build.gradle`, raise `versionCode` by 1 and update `versionName` (for example, 1.1).
3. Build a new signed bundle with the **same keystore**.
4. Upload it to a testing track first, then to production.

Also, Google raises the required **target API level** every year, usually in August.
Plan to update the app at least once a year so it stays in the store.

---

## Quick checklist

- [ ] Server online with HTTPS ([plan, Step A](README.md#step-a-put-the-server-on-the-internet))
- [ ] Capacitor app runs on an emulator and on a real phone
- [ ] Location permission added, and "Near me" works
- [ ] App ID chosen (it's permanent!)
- [ ] App icon, name and version set
- [ ] Signed `.aab` built, and the keystore backed up somewhere safe
- [ ] Play Console account created by an adult, and identity verified
- [ ] Privacy policy page online
- [ ] App content sections done (data safety, content rating, target audience)
- [ ] Store listing done (descriptions, icon, feature graphic, screenshots)
- [ ] Internal test → closed test (12+ testers, 14 days, if you have a personal account)
- [ ] Sent for review → published!

← Back to the **[phone app plan](README.md)** · See also: **[iPhone and the App Store](iphone.md)**
