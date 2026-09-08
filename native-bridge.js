(() => {
  const capacitor = window.Capacitor;
  if (!capacitor?.isNativePlatform?.()) return;
  document.documentElement.classList.add('cofish-native');
  window.addEventListener('DOMContentLoaded', () => document.body.classList.add('cofish-native'));

  const plugins = capacitor.Plugins || {};
  plugins.StatusBar?.setStyle?.({ style: 'LIGHT' }).catch(() => {});
  plugins.SplashScreen?.hide?.().catch(() => {});

  plugins.App?.addListener?.('backButton', () => {
    const details = document.getElementById('details');
    if (details?.open) {
      details.close();
      return;
    }
    if (document.body.dataset.mobileView && document.body.dataset.mobileView !== 'home') {
      document.querySelector('[data-mobile-view-target="home"]')?.click();
      return;
    }
    plugins.App.exitApp?.();
  });
})();
