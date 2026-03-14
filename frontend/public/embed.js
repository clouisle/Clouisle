/**
 * Clouisle Embed SDK
 * Embed AI agents into any website via iframe.
 *
 * Usage:
 *   <script src="https://your-clouisle.com/embed.js"></script>
 *   <script>
 *     Clouisle.init({
 *       type: 'agent',
 *       id: 'agent-uuid',
 *       token: 'clou_xxx',
 *       mode: 'bubble',        // 'fullscreen' | 'mobile' | 'bubble'
 *       theme: 'auto',         // 'light' | 'dark' | 'auto'
 *       primaryColor: '#6366f1',
 *       container: '#chat',    // for fullscreen/mobile
 *       position: 'bottom-right',
 *       greeting: 'Hi!',
 *     });
 *   </script>
 */
(function () {
  'use strict';

  var DEFAULTS = {
    type: 'agent',
    mode: 'bubble',
    theme: 'auto',
    position: 'bottom-right',
    greeting: '',
    primaryColor: '',
    container: '',
  };

  var BUBBLE_SIZE = 56;
  var CHAT_WIDTH = 400;
  var CHAT_HEIGHT = 600;
  var BUBBLE_MARGIN = 20;

  var instance = null;

  function getOrigin() {
    var scripts = document.getElementsByTagName('script');
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].src || '';
      if (src.indexOf('embed.js') !== -1) {
        var url = new URL(src);
        return url.origin;
      }
    }
    return window.location.origin;
  }

  function buildIframeUrl(origin, config) {
    var path = '/embed/' + config.type + '/' + config.id;
    var params = new URLSearchParams();
    if (config.token) params.set('token', config.token);
    if (config.theme) params.set('theme', config.theme);
    if (config.primaryColor) params.set('color', config.primaryColor);
    if (config.mode) params.set('mode', config.mode);
    return origin + path + '?' + params.toString();
  }

  function createStyles() {
    if (document.getElementById('clouisle-embed-styles')) return;
    var style = document.createElement('style');
    style.id = 'clouisle-embed-styles';
    style.textContent = [
      '.clouisle-bubble-btn{',
      '  position:fixed;width:' + BUBBLE_SIZE + 'px;height:' + BUBBLE_SIZE + 'px;',
      '  border-radius:50%;background:#6366f1;color:#fff;border:none;',
      '  cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.15);',
      '  display:flex;align-items:center;justify-content:center;',
      '  z-index:2147483646;transition:transform 0.2s,box-shadow 0.2s;',
      '}',
      '.clouisle-bubble-btn:hover{transform:scale(1.05);box-shadow:0 6px 20px rgba(0,0,0,0.2);}',
      '.clouisle-bubble-btn svg{width:28px;height:28px;}',
      '.clouisle-chat-frame{',
      '  position:fixed;z-index:2147483647;border:none;',
      '  border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.12);',
      '  overflow:hidden;transition:opacity 0.2s,transform 0.2s;',
      '}',
      '.clouisle-chat-frame.hidden{opacity:0;transform:scale(0.95);pointer-events:none;}',
      '.clouisle-greeting{',
      '  position:fixed;z-index:2147483645;background:#fff;color:#333;',
      '  padding:10px 16px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);',
      '  font-size:14px;max-width:240px;cursor:pointer;',
      '  transition:opacity 0.2s;',
      '}',
      '.clouisle-greeting.hidden{opacity:0;pointer-events:none;}',
      '.clouisle-fullscreen-frame{width:100%;height:100%;border:none;}',
      '.clouisle-mobile-frame{',
      '  position:fixed;top:0;left:0;width:100%;height:100%;',
      '  border:none;z-index:2147483647;',
      '}',
    ].join('\n');
    document.head.appendChild(style);
  }

  function createBubbleIcon() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
  }

  function createCloseIcon() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
  }

  function getContrastColor(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    var r = parseInt(hex.substring(0, 2), 16);
    var g = parseInt(hex.substring(2, 4), 16);
    var b = parseInt(hex.substring(4, 6), 16);
    // Relative luminance
    var luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? '#333' : '#fff';
  }

  function initBubble(origin, config) {
    var isOpen = false;
    var isRight = config.position !== 'bottom-left';

    // Bubble button
    var btn = document.createElement('button');
    btn.className = 'clouisle-bubble-btn';
    btn.innerHTML = createBubbleIcon();
    btn.style[isRight ? 'right' : 'left'] = BUBBLE_MARGIN + 'px';
    btn.style.bottom = BUBBLE_MARGIN + 'px';
    if (config.primaryColor) {
      btn.style.background = config.primaryColor;
      btn.style.color = getContrastColor(config.primaryColor);
    }
    document.body.appendChild(btn);

    // Chat iframe
    var iframe = document.createElement('iframe');
    iframe.className = 'clouisle-chat-frame hidden';
    iframe.src = buildIframeUrl(origin, config);
    iframe.style.width = CHAT_WIDTH + 'px';
    iframe.style.height = CHAT_HEIGHT + 'px';
    iframe.style.bottom = (BUBBLE_MARGIN + BUBBLE_SIZE + 12) + 'px';
    iframe.style[isRight ? 'right' : 'left'] = BUBBLE_MARGIN + 'px';
    iframe.allow = 'clipboard-write';
    document.body.appendChild(iframe);

    // Greeting tooltip
    var greeting = null;
    if (config.greeting) {
      greeting = document.createElement('div');
      greeting.className = 'clouisle-greeting';
      greeting.textContent = config.greeting;
      greeting.style.bottom = (BUBBLE_MARGIN + BUBBLE_SIZE + 8) + 'px';
      greeting.style[isRight ? 'right' : 'left'] = BUBBLE_MARGIN + 'px';
      document.body.appendChild(greeting);
      greeting.addEventListener('click', function () { toggle(); });
    }

    function toggle() {
      isOpen = !isOpen;
      iframe.classList.toggle('hidden', !isOpen);
      btn.innerHTML = isOpen ? createCloseIcon() : createBubbleIcon();
      if (greeting) greeting.classList.toggle('hidden', isOpen);
    }

    btn.addEventListener('click', toggle);

    // Listen for close message from iframe
    window.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'clouisle:close') {
        isOpen = false;
        iframe.classList.add('hidden');
        btn.innerHTML = createBubbleIcon();
        if (greeting) greeting.classList.remove('hidden');
      }
    });

    return {
      open: function () { if (!isOpen) toggle(); },
      close: function () { if (isOpen) toggle(); },
      destroy: function () {
        btn.remove();
        iframe.remove();
        if (greeting) greeting.remove();
      },
    };
  }

  function initFullscreen(origin, config) {
    var container = config.container
      ? document.querySelector(config.container)
      : document.body;
    if (!container) {
      console.error('[Clouisle] Container not found:', config.container);
      return null;
    }

    var iframe = document.createElement('iframe');
    iframe.className = 'clouisle-fullscreen-frame';
    iframe.src = buildIframeUrl(origin, config);
    iframe.allow = 'clipboard-write';
    container.appendChild(iframe);

    return {
      destroy: function () { iframe.remove(); },
    };
  }

  function initMobile(origin, config) {
    var iframe = document.createElement('iframe');
    iframe.className = 'clouisle-mobile-frame';
    iframe.src = buildIframeUrl(origin, config);
    iframe.allow = 'clipboard-write';
    document.body.appendChild(iframe);

    return {
      destroy: function () { iframe.remove(); },
    };
  }

  // Public API
  window.Clouisle = {
    init: function (userConfig) {
      if (instance) {
        instance.destroy();
        instance = null;
      }

      var config = {};
      for (var key in DEFAULTS) config[key] = DEFAULTS[key];
      for (var key in userConfig) config[key] = userConfig[key];

      if (!config.id || !config.token) {
        console.error('[Clouisle] id and token are required');
        return null;
      }

      createStyles();
      var origin = getOrigin();

      switch (config.mode) {
        case 'fullscreen':
          instance = initFullscreen(origin, config);
          break;
        case 'mobile':
          instance = initMobile(origin, config);
          break;
        case 'bubble':
        default:
          instance = initBubble(origin, config);
          break;
      }

      return instance;
    },

    destroy: function () {
      if (instance) {
        instance.destroy();
        instance = null;
      }
    },

    open: function () {
      if (instance && instance.open) instance.open();
    },

    close: function () {
      if (instance && instance.close) instance.close();
    },
  };
})();
