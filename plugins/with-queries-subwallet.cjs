// Adds <queries> for WalletConnect/SubWallet on Android 11+ (Package Visibility)
const { withAndroidManifest } = require("@expo/config-plugins");

function alreadyHas(manifest) {
  const xml = JSON.stringify(manifest.queries ?? []);
  return (
    xml.includes('"android:scheme":"subwallet"') ||
    xml.includes('"android:scheme":"wc"') ||
    xml.includes('"app.subwallet.mobile"')
  );
}

module.exports = function withQueriesSubwallet(config) {
  return withAndroidManifest(config, (conf) => {
    const manifest = conf.modResults;
    manifest.queries = manifest.queries || [];

    const bySubwalletScheme = {
      intent: [
        {
          action: [{ $: { "android:name": "android.intent.action.VIEW" } }],
          data: [{ $: { "android:scheme": "subwallet" } }],
        },
      ],
    };
    const byWcScheme = {
      intent: [
        {
          action: [{ $: { "android:name": "android.intent.action.VIEW" } }],
          data: [{ $: { "android:scheme": "wc" } }],
        },
      ],
    };
    const byPackage = {
      package: [{ $: { "android:name": "app.subwallet.mobile" } }],
    };

    if (!alreadyHas(manifest)) {
      manifest.queries.push(bySubwalletScheme);
      manifest.queries.push(byWcScheme);
      manifest.queries.push(byPackage);
    }
    return conf;
  });
};
