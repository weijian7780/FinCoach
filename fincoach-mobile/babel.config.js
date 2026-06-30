module.exports = function (api) {
  api.cache(true);
  return {
    // babel-preset-expo (SDK 54+) automatically includes react-native-worklets/plugin,
    // which Reanimated 4 needs for worklets to run on the UI thread.
    presets: ['babel-preset-expo'],
  };
};
