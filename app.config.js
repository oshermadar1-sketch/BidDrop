// app.config.js
// Takes app.json as the base and drops the Firebase file reference when the file is not
// present on the machine (google-services.json is not in git). Without it Android push
// notifications are off, but the build itself still works.
const fs = require("fs");
const path = require("path");

module.exports = ({ config }) => {
  const hasFirebase = fs.existsSync(path.join(__dirname, "google-services.json"));
  if (hasFirebase || !config.android) return config;
  const { googleServicesFile, ...android } = config.android;
  return { ...config, android };
};
