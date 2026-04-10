const $cru = e => document.querySelector(e);
const $crus = e => document.querySelectorAll(e);

// Estado interno de configuração
let _cruConfig = {
    prefix_url: "",
    headers: {
        "Content-Type": "application/json"
    },
    callbacks: {}
};

// Função de configuração que aceita novos parâmetros
const $cruConfig = (config) => {
    if (config) {
        Object.assign(_cruConfig, config);
    }
};

// Alias para compatibilidade se necessário
const $C = $cruConfig;

const $cruTypeResponse = async (type, response) => {
    if (type === "json") return await response.json();
    return await response.text();
};

const $cruLoadContainer = async (el) => {
    if (!el) return; // Evita erro se o elemento não for encontrado no DOM

    const url = el.getAttribute("c-container");
    const targetSelector = el.getAttribute("c-target");
    const type = el.getAttribute("c-type") || "html";
    const callbackName = el.getAttribute("c-callback");

    const timestamp = new Date().getTime();
    const separator = url.includes("?") ? "&" : "?";
    const finalUrl = _cruConfig.prefix_url + url + separator + "t=" + timestamp;

    try {
        const response = await fetch(finalUrl, {
            method: "GET",
            headers: _cruConfig.headers
        });

        const data = await $cruTypeResponse(type, response);
        const target = targetSelector ? $cru(targetSelector) : el;

        if (type === "html") {
            target.innerHTML = data;
        }

        if (callbackName && _cruConfig.callbacks[callbackName]) {
            _cruConfig.callbacks[callbackName](data, target);
        }
    } catch (error) {
        console.error(`[cru.js] Erro ao carregar ${url}:`, error);
    }
};

const $cruLoadEvents = () => {
    $crus("[c-container]").forEach(el => {
        if (!el.classList.contains("loaded")) {
            el.classList.add("loaded");
            $cruLoadContainer(el);
        }
    });
};

// Inicialização automática
window.addEventListener("DOMContentLoaded", () => {
    $cruLoadEvents();
});
