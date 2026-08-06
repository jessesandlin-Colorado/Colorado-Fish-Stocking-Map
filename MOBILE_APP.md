# COFish native mobile package

COFish uses Capacitor to package the existing mobile web interface as native iOS and Android applications. The web source remains canonical; `mobile-web/`, `ios/`, and `android/` are generated build outputs.

## First iOS build on a Mac

Requirements: Node.js 22+, Xcode, an Apple Developer account, and CocoaPods if requested by Capacitor.

```bash
npm install
npm run mobile:add:ios
npm run mobile:open:ios
```

In Xcode:

1. Select the **App** project and **App** target.
2. Open **Signing & Capabilities**.
3. Select your Apple Developer team.
4. Confirm the bundle identifier is `app.cofish.mobile`.
5. Choose an attached iPhone and press **Run**.

After later web changes, run `npm run mobile:sync` before rebuilding.

## TestFlight archive

In Xcode, select **Any iOS Device (arm64)**, then choose **Product → Archive**. From Organizer, validate and distribute the archive to App Store Connect for TestFlight testing.

## Android setup

```bash
npm install
npm run mobile:add:android
npm run mobile:open:android
```

Android Studio can then build a debug APK or signed Android App Bundle. Google Play signing credentials must never be committed to the repository.

## Security and generated files

- Do not commit signing certificates, provisioning profiles, keystores, API keys, or App Store Connect credentials.
- `mobile-web/`, `ios/`, `android/`, and `node_modules/` are generated locally and ignored.
- Store credentials belong in Apple/Google tooling or encrypted GitHub secrets only.
