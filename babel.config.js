module.exports = function (api) {
  api.cache(true);
  return {
    presets: ["babel-preset-expo"],
    plugins: [
      "expo-router/babel", // השאירי אם את משתמשת ב-expo-router
      "react-native-reanimated/plugin", // חייב להיות האחרון!
    ],
  };
};
