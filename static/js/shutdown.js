// shutdown.js – Power-Button + Bestätigungsdialog für alle Seiten

(function () {
    const POWER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-1.98.81-3.77 2.1-5.07L5.67 5.5A8.93 8.93 0 0 0 3 12a9 9 0 0 0 18 0c0-2.74-1.23-5.18-3.17-6.83z"/>
    </svg>`;

    // Farben kommen aus static/app.css (Design der App)
    const CSS = `
        .sd-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(3,4,9,0.72);
            -webkit-backdrop-filter: blur(10px);
            backdrop-filter: blur(10px);
            z-index: 9999;
            align-items: center;
            justify-content: center;
        }
        .sd-overlay.show { display: flex; }
        .sd-dialog {
            background: var(--surface-high, #1A1F33);
            border: 1px solid var(--stroke, rgba(255,255,255,.1));
            color: var(--ink, #F4F6FF);
            border-radius: 24px;
            padding: 28px 24px 22px;
            max-width: 380px;
            width: 90%;
            text-align: center;
            box-shadow: 0 30px 80px -20px rgba(0,0,0,0.7);
        }
        .sd-icon {
            width: 64px; height: 64px; margin: 0 auto 14px; border-radius: 20px;
            display: flex; align-items: center; justify-content: center;
            color: #FF453A; background: rgba(255,69,58,.14); border: 1px solid rgba(255,69,58,.4);
        }
        .sd-title { font-size: 20px; font-weight: 800; margin-bottom: 8px; }
        .sd-warning { font-size: 14px; line-height: 1.5; color: var(--ink-dim, #9AA3BD); margin-bottom: 22px; }
        .sd-btns { display: flex; gap: 10px; }
        .sd-btns button {
            flex: 1; padding: 13px 14px; border-radius: 16px; cursor: pointer;
            font-family: inherit; font-size: 15px; font-weight: 600;
        }
        .sd-cancel { background: transparent; border: 1px solid var(--stroke, rgba(255,255,255,.1)); color: var(--ink, #F4F6FF); }
        .sd-confirm { background: #FF453A; border: 1px solid #FF453A; color: #fff; font-weight: 700; }
        .sd-confirm:hover { filter: brightness(1.1); }
    `;

    function tr(key, fallback) {
        if (typeof getTranslation === 'function') {
            return getTranslation(key) || fallback;
        }
        return fallback;
    }

    function injectStyles() {
        const s = document.createElement('style');
        s.textContent = CSS;
        document.head.appendChild(s);
    }

    function createModal() {
        const overlay = document.createElement('div');
        overlay.className = 'sd-overlay';
        overlay.id = 'sdOverlay';
        overlay.innerHTML = `
            <div class="sd-dialog">
                <div class="sd-icon">${POWER_SVG.replace(/width="18" height="18"/, 'width="30" height="30"')}</div>
                <div class="sd-title" data-i18n="common.shutdown_confirm">Wirklich herunterfahren?</div>
                <div class="sd-warning" data-i18n="admin.warning_shutdown">Das Herunterfahren stoppt alle Dienste und schaltet das System aus.</div>
                <div class="sd-btns">
                    <button class="sd-cancel" id="sdCancel" data-i18n="common.cancel">Abbrechen</button>
                    <button class="sd-confirm" id="sdConfirm" data-i18n="common.shutdown_yes">Ja, herunterfahren</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        document.getElementById('sdCancel').addEventListener('click', function () {
            overlay.classList.remove('show');
        });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.classList.remove('show');
        });
        document.getElementById('sdConfirm').addEventListener('click', doShutdown);
    }

    function createButton() {
        const btn = document.createElement('button');
        btn.className = 'icon-btn danger';
        btn.title = 'System herunterfahren';
        btn.innerHTML = POWER_SVG;
        btn.addEventListener('click', function () {
            // Übersetzungen aktualisieren bevor Modal gezeigt wird
            const overlay = document.getElementById('sdOverlay');
            overlay.querySelectorAll('[data-i18n]').forEach(el => {
                const val = tr(el.getAttribute('data-i18n'), el.textContent);
                if (val) el.textContent = val;
            });
            overlay.classList.add('show');
        });
        return btn;
    }

    async function doShutdown() {
        const confirmBtn = document.getElementById('sdConfirm');
        confirmBtn.disabled = true;
        confirmBtn.textContent = '...';
        try {
            await fetch('/api/system/shutdown', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (_) {}
        // Zeige "System heruntergefahren" Seite
        setTimeout(function () {
            document.body.innerHTML = `
                <div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;
                            min-height:100vh;text-align:center;padding:24px;">
                    <img src="/static/logo.png" alt="openPadel"
                         style="width:200px;height:200px;margin-bottom:28px;filter:drop-shadow(0 30px 40px rgba(0,0,0,0.5));">
                    <div style="font-size:28px;font-weight:900;letter-spacing:-.02em;">
                        ${tr('common.shutdown_done', 'System wurde heruntergefahren')}
                    </div>
                    <div style="font-size:15px;margin-top:10px;color:var(--ink-dim,#9AA3BD);">
                        ${tr('common.shutdown_close', 'Sie können dieses Fenster schließen')}
                    </div>
                </div>`;
        }, 1500);
    }

    // Globale Funktion damit admin.html sie weiter nutzen kann
    window.shutdownSystem = function () {
        document.getElementById('sdOverlay').classList.add('show');
    };

    document.addEventListener('DOMContentLoaded', function () {
        injectStyles();
        createModal();

        const btn = createButton();

        // Kopfzeile (templates/_nav.html)
        const actions = document.querySelector('.nav-actions') || document.querySelector('.header-actions');
        if (actions) actions.appendChild(btn);
    });
})();
