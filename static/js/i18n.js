// i18n.js - Internationalisierung
// Die Seiten betten die Übersetzungen direkt ein (templates/_head.html),
// damit Texte nicht erst nach dem Laden umspringen.
let translations = window.I18N || {};
let currentLang = document.documentElement.lang || 'en';

// Lade Übersetzungen
async function loadTranslations() {
    try {
        const langResponse = await fetch('/api/language');
        const langData = await langResponse.json();
        currentLang = langData.current;
        
        const transResponse = await fetch('/api/translations');
        translations = await transResponse.json();
        
        applyTranslations();
    } catch (error) {
        console.error('Error loading translations:', error);
    }
}

// Wende Übersetzungen auf Seite an
function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        const translation = getTranslation(key);
        if (translation) {
            element.textContent = translation;
        }
    });
    
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        const translation = getTranslation(key);
        if (translation) {
            element.placeholder = translation;
        }
    });
    
    document.querySelectorAll('[data-i18n-title]').forEach(element => {
        const key = element.getAttribute('data-i18n-title');
        const translation = getTranslation(key);
        if (translation) {
            element.title = translation;
        }
    });
    
    // HTML lang attribute
    document.documentElement.lang = currentLang;
}

// Holt Übersetzung mit verschachtelten Schlüsseln (z.B. "nav.scoreboard")
function getTranslation(key) {
    const keys = key.split('.');
    let value = translations;
    
    for (let k of keys) {
        if (value && typeof value === 'object' && k in value) {
            value = value[k];
        } else {
            return null;
        }
    }
    
    return typeof value === 'string' ? value : null;
}

// Übersetzung mit Fallback und Platzhaltern: tr('stats.set_n', 'Satz {n}', {n: 2})
function tr(key, fallback, vars) {
    let text = getTranslation(key) || fallback || key;
    if (vars) {
        for (const name in vars) {
            text = text.split('{' + name + '}').join(vars[name]);
        }
    }
    return text;
}

// Initialisiere beim Laden
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTranslations);
} else {
    loadTranslations();
}
