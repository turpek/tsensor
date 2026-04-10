/**
 * cru.js v0.1 - Um framework minimalista para atualizações parciais
 */

let _cruOptions = {
    callbacks: {}
};

/**
 * Configuração global do cru.js
 */
function $cruConfig(options) {
    _cruOptions = { ..._cruOptions, ...options };
}

/**
 * Carrega o conteúdo de um container baseado nos atributos c-
 */
async function $cruLoadContainer(element) {
    if (!element) return;

    const url = element.getAttribute('c-container');
    const type = element.getAttribute('c-type') || 'html';
    const targetSelector = element.getAttribute('c-target');
    const callbackName = element.getAttribute('c-callback');

    try {
        const response = await fetch(url);
        
        if (type === 'json') {
            const data = await response.json();
            if (callbackName && _cruOptions.callbacks[callbackName]) {
                _cruOptions.callbacks[callbackName](data, element);
            }
        } else {
            const html = await response.text();
            const target = targetSelector ? document.querySelector(targetSelector) : element;
            if (target) {
                target.innerHTML = html;
            }
            if (callbackName && _cruOptions.callbacks[callbackName]) {
                _cruOptions.callbacks[callbackName](html, element);
            }
        }
    } catch (error) {
        console.error(`[cru.js] Erro ao carregar ${url}:`, error);
    }
}

// Inicializa elementos cru no carregamento da página
document.addEventListener('DOMContentLoaded', () => {
    // Procura por containers que devem ser carregados automaticamente (sem polling)
    // Para este projeto, o polling é controlado manualmente no index.html
});
