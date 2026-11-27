// geral.js - coisas que valem pra todas as páginas depois do login
// (precisa vir antes do script da página no HTML)

const CHAVE_CONFIG = "signedu-config";
const CHAVE_PROGRESSO = "signedu-progresso";

// lê as configurações em cache (ou null se não tiver nada)
function lerConfiguracoesSalvas() {
    try {
        return JSON.parse(localStorage.getItem(CHAVE_CONFIG));
    } catch (erro) {
        return null;
    }
}

// Coloca um ícone do Bootstrap Icons dentro de um elemento.
function colocarIcone(elemento, classes) {
    elemento.textContent = "";
    const icone = document.createElement("i");
    icone.className = "bi " + classes;
    icone.setAttribute("aria-hidden", "true");
    elemento.appendChild(icone);
}

// aplica o tamanho do texto escolhido nas Configurações
function aplicarTamanhoTexto(porcentagem) {
    document.documentElement.style.fontSize = porcentagem + "%";
}

const configSalvas = lerConfiguracoesSalvas();
if (configSalvas && configSalvas.fonte) {
    aplicarTamanhoTexto(configSalvas.fonte);
}


// Pop-up de meta cumprida.
function avisarMetaCumprida(minutos, forcar) {
    const config = lerConfiguracoesSalvas();
    const avisoLigado = !config || config.avisoMeta !== false;

    if (!avisoLigado && !forcar) {
        return;
    }

    let caixa = document.getElementById("modal-meta");
    if (!caixa) {
        caixa = document.createElement("div");
        caixa.className = "modal fade";
        caixa.id = "modal-meta";
        caixa.tabIndex = -1;
        caixa.setAttribute("aria-labelledby", "titulo-meta");
        caixa.setAttribute("aria-hidden", "true");
        caixa.innerHTML =
            '<div class="modal-dialog modal-dialog-centered modal-sm">' +
                '<div class="modal-content text-center p-3">' +
                    '<div class="icone-aviso"><i class="bi bi-trophy-fill" aria-hidden="true"></i></div>' +
                    '<h2 class="h4 mt-2" id="titulo-meta">Meta cumprida!</h2>' +
                    '<p class="mb-3" id="texto-meta"></p>' +
                    '<button type="button" class="btn btn-primary w-100" data-bs-dismiss="modal">Oba!</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(caixa);
    }

    document.getElementById("texto-meta").textContent =
        "Você estudou " + minutos + " minutos hoje. Continue assim!";

    bootstrap.Modal.getOrCreateInstance(caixa).show();
}


// Aviso de conquista - aparece no canto inferior direito e some sozinho depois de 5 segundos.
function avisarConquista(conquista, forcar) {
    const config = lerConfiguracoesSalvas();
    const avisoLigado = !config || config.avisoConquista !== false;

    if (!avisoLigado && !forcar) {
        return;
    }

    let area = document.getElementById("area-avisos");
    if (!area) {
        area = document.createElement("div");
        area.id = "area-avisos";
        area.className = "toast-container position-fixed bottom-0 end-0 p-3";
        document.body.appendChild(area);
    }

    const aviso = document.createElement("div");
    aviso.className = "toast aviso-conquista align-items-center border-0 shadow";
    aviso.setAttribute("role", "status");
    aviso.setAttribute("aria-live", "polite");
    aviso.innerHTML =
        '<div class="d-flex align-items-center p-3 gap-3">' +
            '<div class="icone-toast"></div>' +
            '<div class="flex-grow-1">' +
                '<p class="small text-muted mb-0">Nova conquista!</p>' +
                '<p class="fw-semibold mb-0 nome-toast"></p>' +
            '</div>' +
            '<span class="badge bg-primary pontos-toast"></span>' +
            '<button type="button" class="btn-close ms-1" data-bs-dismiss="toast" aria-label="Fechar"></button>' +
        '</div>';

    colocarIcone(aviso.querySelector(".icone-toast"), conquista.icone);
    aviso.querySelector(".nome-toast").textContent = conquista.nome;
    aviso.querySelector(".pontos-toast").textContent = "+" + conquista.pontos + " pts";

    area.appendChild(aviso);

    const toast = new bootstrap.Toast(aviso, { delay: 5000 });
    aviso.addEventListener("hidden.bs.toast", function () { aviso.remove(); });
    toast.show();
}


// ================== GAMIFICAÇÃO ==================

const NIVEIS = [
    { nivel: 1, titulo: "Iniciante",            icone: "bi-flower1", xp: 0 },
    { nivel: 2, titulo: "Explorador de Sinais", icone: "bi-search", xp: 100 },
    { nivel: 3, titulo: "Aprendiz de Libras",   icone: "bi-book-half", xp: 250 },
    { nivel: 4, titulo: "Conversador",          icone: "bi-chat-left-text", xp: 450 },
    { nivel: 5, titulo: "Comunicador",          icone: "bi-megaphone", xp: 700 },
    { nivel: 6, titulo: "Fluente",              icone: "bi-stars", xp: 1000 },
    { nivel: 7, titulo: "Intérprete",           icone: "bi-translate", xp: 1400 },
    { nivel: 8, titulo: "Mestre em Libras",     icone: "bi-trophy-fill", xp: 1900 }
];

function dadosDoNivel(numero) {
    return NIVEIS.find(function (n) { return n.nivel === numero; }) || NIVEIS[0];
}

const LIGAS = [
    { id: "bronze",   nome: "Bronze",   icone: "bi-award-fill liga-bronze" },
    { id: "prata",    nome: "Prata",    icone: "bi-award-fill liga-prata" },
    { id: "ouro",     nome: "Ouro",     icone: "bi-award-fill liga-ouro" },
    { id: "diamante", nome: "Diamante", icone: "bi-gem liga-diamante" }
];

function dadosDaLiga(id) {
    return LIGAS.find(function (l) { return l.id === id; }) || LIGAS[0];
}


// ================== COMUNICAÇÃO COM O BACK ==================

async function chamarApi(metodo, rota, corpo) {
    const opcoes = { method: metodo, credentials: "same-origin", headers: {} };
    if (corpo !== undefined) {
        opcoes.headers["Content-Type"] = "application/json";
        opcoes.body = JSON.stringify(corpo);
    }

    const resposta = await fetch(rota, opcoes);
    let dados = null;
    try { dados = await resposta.json(); } catch (erro) {}

    if (resposta.status === 401) {
        irParaLogin();
    }
    return { ok: resposta.ok, status: resposta.status, dados: dados };
}

function irParaLogin() {
    try {
        localStorage.removeItem(CHAVE_PROGRESSO);
        localStorage.removeItem(CHAVE_CONFIG);
    } catch (erro) {}
    window.location.href = "login.html";
}

async function sair() {
    try {
        await fetch("/api/auth/logout", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: "{}"
        });
    } catch (erro) {}
    irParaLogin();
}


// Dados do jogador (tudo vem do banco via GET /api/usuarios/progresso).
const JOGADOR_PADRAO = {
    nivel: 1,
    xpTotal: 0,
    liga: "bronze",
    posicaoRanking: 1,
    moedas: 0,
    itens: {},
    molduras: [],
    moldura: null,
    fotoUrl: null
};

function lerProgressoDoServidor() {
    try { return JSON.parse(localStorage.getItem(CHAVE_PROGRESSO)); } catch (erro) { return null; }
}

function lerJogador() {
    const progresso = lerProgressoDoServidor() || {};
    return Object.assign({}, JOGADOR_PADRAO, progresso);
}

async function atualizarProgresso() {
    try {
        const resposta = await chamarApi("GET", "/api/usuarios/progresso");
        if (!resposta.ok) return null;

        localStorage.setItem(CHAVE_PROGRESSO, JSON.stringify(resposta.dados));
        atualizarMenu();
        document.dispatchEvent(new CustomEvent("signedu:progresso", { detail: resposta.dados }));
        return resposta.dados;
    } catch (erro) {
        return null;
    }
}

async function sincronizarConfiguracoes() {
    try {
        const resposta = await chamarApi("GET", "/api/usuarios/configuracoes");
        if (!resposta.ok) return null;
        localStorage.setItem(CHAVE_CONFIG, JSON.stringify(resposta.dados));
        if (resposta.dados && resposta.dados.fonte) {
            aplicarTamanhoTexto(resposta.dados.fonte);
        }
        document.dispatchEvent(new CustomEvent("signedu:config", { detail: resposta.dados }));
        return resposta.dados;
    } catch (erro) {
        return null;
    }
}

function progressoNoNivel(jogador) {
    const atual = dadosDoNivel(jogador.nivel);
    const proximo = NIVEIS.find(function (n) { return n.nivel === jogador.nivel + 1; });

    if (!proximo) {
        return { atual: atual, proximo: null, xpNoNivel: jogador.xpTotal - atual.xp, xpDoNivel: 0, porcentagem: 100 };
    }

    const xpDoNivel = proximo.xp - atual.xp;
    const xpNoNivel = Math.max(0, jogador.xpTotal - atual.xp);
    return {
        atual: atual,
        proximo: proximo,
        xpNoNivel: xpNoNivel,
        xpDoNivel: xpDoNivel,
        porcentagem: Math.min(100, Math.round((xpNoNivel / xpDoNivel) * 100))
    };
}


// Molduras do avatar (vendidas na loja). A classe fica no paginas.css.
const MOLDURAS = {
    lilas:     { nome: "Lilás",      classe: "moldura-lilas" },
    fogo:      { nome: "Fogo",       classe: "moldura-fogo" },
    ouro:      { nome: "Ouro",       classe: "moldura-ouro" },
    arcoiris:  { nome: "Arco-íris",  classe: "moldura-arcoiris" }
};

function aplicarMoldura(idMoldura) {
    document.querySelectorAll("nav .avatar").forEach(function (avatar) {
        for (const id in MOLDURAS) avatar.classList.remove(MOLDURAS[id].classe);
        if (idMoldura && MOLDURAS[idMoldura]) avatar.classList.add(MOLDURAS[idMoldura].classe);
    });
}

function aplicarFotoMenu(fotoUrl) {
    document.querySelectorAll("nav .avatar").forEach(function (avatar) {
        avatar.classList.add("overflow-hidden");
        let img = avatar.querySelector("img.avatar-foto-menu");
        const svg = avatar.querySelector("svg");
        if (fotoUrl) {
            if (!img) {
                img = document.createElement("img");
                img.className = "avatar-foto-menu w-100 h-100";
                img.style.objectFit = "cover";
                img.alt = "Foto de perfil";
                avatar.appendChild(img);
            }
            img.src = fotoUrl;
            img.classList.remove("d-none");
            if (svg) svg.classList.add("d-none");
        } else {
            if (img) img.classList.add("d-none");
            if (svg) svg.classList.remove("d-none");
        }
    });
}


function atualizarMenu() {
    const jogador = lerJogador();
    const nivel = dadosDoNivel(jogador.nivel);
    const liga = dadosDaLiga(jogador.liga);

    const titulo = document.getElementById("menu-titulo-nivel");
    if (titulo) {
        titulo.textContent = nivel.titulo;

        const barra = titulo.previousElementSibling;
        const textoNivel = barra && barra.previousElementSibling;
        const preenchimento = barra && barra.querySelector(".progress-bar");
        if (textoNivel && preenchimento) {
            const progresso = progressoNoNivel(jogador);
            textoNivel.textContent = "Nível " + nivel.nivel;
            preenchimento.style.width = progresso.porcentagem + "%";
            preenchimento.setAttribute("aria-valuenow", progresso.porcentagem);
        }
    }

    const moedas = document.getElementById("menu-moedas");
    if (moedas) moedas.textContent = jogador.moedas + " moedas";

    const ligaMenu = document.getElementById("menu-liga");
    if (ligaMenu) ligaMenu.textContent = "Liga " + liga.nome;

    aplicarMoldura(jogador.moldura);
    aplicarFotoMenu(jogador.fotoUrl);
}

function adicionarBotaoSair() {
    const lista = document.querySelector("nav ul.nav");
    if (!lista || document.getElementById("btn-sair")) return;

    const item = document.createElement("li");
    item.className = "nav-item mb-2";

    const botao = document.createElement("button");
    botao.type = "button";
    botao.id = "btn-sair";
    botao.className = "btn btn-light sidebar-btn w-100 text-start d-flex align-items-center gap-2";
    colocarIcone(botao, "bi-box-arrow-left");
    botao.appendChild(document.createTextNode(" Sair"));
    botao.addEventListener("click", sair);

    item.appendChild(botao);
    lista.appendChild(item);
}

document.addEventListener("DOMContentLoaded", function () {
    atualizarMenu();
    adicionarBotaoSair();
    atualizarProgresso();
    sincronizarConfiguracoes();
});


function mostrarAvisoRapido(icone, titulo, texto, selo) {
    let area = document.getElementById("area-avisos");
    if (!area) {
        area = document.createElement("div");
        area.id = "area-avisos";
        area.className = "toast-container position-fixed bottom-0 end-0 p-3";
        document.body.appendChild(area);
    }

    const aviso = document.createElement("div");
    aviso.className = "toast aviso-conquista align-items-center border-0 shadow";
    aviso.setAttribute("role", "status");
    aviso.setAttribute("aria-live", "polite");
    aviso.innerHTML =
        '<div class="d-flex align-items-center p-3 gap-3">' +
            '<div class="icone-toast"></div>' +
            '<div class="flex-grow-1">' +
                '<p class="small text-muted mb-0 titulo-toast"></p>' +
                '<p class="fw-semibold mb-0 nome-toast"></p>' +
            '</div>' +
            (selo ? '<span class="badge bg-primary pontos-toast"></span>' : '') +
            '<button type="button" class="btn-close ms-1" data-bs-dismiss="toast" aria-label="Fechar"></button>' +
        '</div>';

    colocarIcone(aviso.querySelector(".icone-toast"), icone);
    aviso.querySelector(".titulo-toast").textContent = titulo;
    aviso.querySelector(".nome-toast").textContent = texto;
    if (selo) aviso.querySelector(".pontos-toast").textContent = selo;

    area.appendChild(aviso);
    const toast = new bootstrap.Toast(aviso, { delay: 5000 });
    aviso.addEventListener("hidden.bs.toast", function () { aviso.remove(); });
    toast.show();
}


const MOEDAS_POR_NIVEL = 50;

function avisarSubiuNivel(numero) {
    const nivel = dadosDoNivel(numero);

    let caixa = document.getElementById("modal-nivel");
    if (!caixa) {
        caixa = document.createElement("div");
        caixa.className = "modal fade";
        caixa.id = "modal-nivel";
        caixa.tabIndex = -1;
        caixa.setAttribute("aria-labelledby", "titulo-nivel");
        caixa.setAttribute("aria-hidden", "true");
        caixa.innerHTML =
            '<div class="modal-dialog modal-dialog-centered modal-sm">' +
                '<div class="modal-content text-center p-3">' +
                    '<p class="small text-muted mb-1">Você subiu de nível!</p>' +
                    '<div class="icone-aviso" id="icone-nivel"></div>' +
                    '<h2 class="h4 mt-2 mb-1" id="titulo-nivel"></h2>' +
                    '<p class="mb-2" id="subtitulo-nivel"></p>' +
                    '<p class="mb-3"><span class="badge bg-primary" id="premio-nivel"></span></p>' +
                    '<button type="button" class="btn btn-primary w-100" data-bs-dismiss="modal">Continuar</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(caixa);
    }

    colocarIcone(document.getElementById("icone-nivel"), nivel.icone);
    document.getElementById("titulo-nivel").textContent = "Nível " + nivel.nivel;
    document.getElementById("subtitulo-nivel").textContent = "Agora você é " + nivel.titulo + "!";
    document.getElementById("premio-nivel").textContent = "+" + MOEDAS_POR_NIVEL + " moedas";

    bootstrap.Modal.getOrCreateInstance(caixa).show();
}


function textoFimDaSemana() {
    const agora = new Date();
    const fim = new Date(agora);
    const diasAteDomingo = (7 - agora.getDay()) % 7;
    fim.setDate(agora.getDate() + diasAteDomingo);
    fim.setHours(23, 59, 59, 999);

    const horas = Math.floor((fim - agora) / (1000 * 60 * 60));
    if (horas >= 48) return Math.floor(horas / 24) + " dias";
    if (horas >= 24) return "1 dia";
    if (horas >= 1) return horas + " horas";
    return "menos de 1 hora";
}
