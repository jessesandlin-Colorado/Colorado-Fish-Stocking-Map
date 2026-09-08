(() => {
  const mobile = window.matchMedia('(max-width: 820px)');
  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const nativeApp = () => Boolean(window.Capacitor?.isNativePlatform?.());
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
  let installPrompt = null;

  function openRequestedView() {
    const view = new URL(location.href).searchParams.get('view');
    if (!['map', 'search', 'navigate'].includes(view)) return;
    const activate = () => {
      const button = document.querySelector(`[data-mobile-view-target="${view}"]`);
      if (button) button.click();
      else window.setTimeout(activate, 80);
    };
    activate();
  }

  function installCard() {
    if (!mobile.matches || standalone() || nativeApp()) return;
    const intro = document.querySelector('.mobile-app-intro');
    if (!intro || intro.querySelector('.pwa-install-card')) return;
    const card = document.createElement('section');
    card.className = 'pwa-install-card';
    card.innerHTML = '<div><strong>Install COFish</strong><span>Open faster from your home screen.</span></div><button type="button">Install</button>';
    intro.appendChild(card);
    card.querySelector('button').addEventListener('click', async () => {
      if (installPrompt) {
        installPrompt.prompt();
        await installPrompt.userChoice;
        installPrompt = null;
        card.remove();
        return;
      }
      const dialog = document.getElementById('pwaInstallHelp');
      dialog.querySelector('[data-platform]').textContent = isIos
        ? 'In Safari, tap Share, then choose Add to Home Screen.'
        : 'Open your browser menu and choose Install app or Add to Home screen.';
      dialog.showModal();
    });
  }

  function buildInstallHelp() {
    if (document.getElementById('pwaInstallHelp')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'pwaInstallHelp';
    dialog.className = 'pwa-install-help';
    dialog.innerHTML = '<button class="pwa-help-close" type="button" aria-label="Close">×</button><img src="cofish-logo.svg" alt=""><h2>Install COFish</h2><p data-platform></p><p class="pwa-help-note">The installed app opens full screen and stays connected to the same current COFish data.</p>';
    dialog.querySelector('button').addEventListener('click', () => dialog.close());
    document.body.appendChild(dialog);
  }

  function showConnectionState() {
    let notice = document.querySelector('.pwa-connection-notice');
    if (navigator.onLine) {
      notice?.remove();
      return;
    }
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'pwa-connection-notice';
      notice.setAttribute('role', 'status');
      notice.textContent = 'Offline — showing saved app content';
      document.body.appendChild(notice);
    }
  }

  function showUpdate(registration) {
    if (document.querySelector('.pwa-update-notice')) return;
    const notice = document.createElement('div');
    notice.className = 'pwa-update-notice';
    notice.innerHTML = '<span>A COFish update is ready.</span><button type="button">Update</button>';
    notice.querySelector('button').addEventListener('click', () => registration.waiting?.postMessage({ type: 'SKIP_WAITING' }));
    document.body.appendChild(notice);
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    installCard();
  });
  window.addEventListener('appinstalled', () => document.querySelector('.pwa-install-card')?.remove());
  window.addEventListener('online', showConnectionState);
  window.addEventListener('offline', showConnectionState);

  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register(new URL('service-worker.js', document.baseURI), { scope: './' }).then(registration => {
      if (registration.waiting) showUpdate(registration);
      registration.addEventListener('updatefound', () => {
        registration.installing?.addEventListener('statechange', event => {
          if (event.target.state === 'installed' && navigator.serviceWorker.controller) showUpdate(registration);
        });
      });
    }).catch(error => console.warn('COFish offline support unavailable', error));
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!refreshing) { refreshing = true; location.reload(); }
    });
  }

  buildInstallHelp();
  openRequestedView();
  showConnectionState();
  window.setTimeout(installCard, 250);
})();
