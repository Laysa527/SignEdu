// ranking.js - ranking semanal por liga

let RANKING = [];
const PREMIOS = { 1: "liga-ouro", 2: "liga-prata", 3: "liga-bronze" };

function mostrarLigas() {
    const jogador = lerJogador();
    const faixa = document.getElementById("faixa-ligas");
    faixa.textContent = "";

    LIGAS.forEach(function (liga) {
        const coluna = document.createElement("div");
        coluna.className = "col-3 col-md-2 liga-item" + (liga.id === jogador.liga ? " atual" : "");
        coluna.innerHTML =
            '<div class="liga-icone"></div>' +
            '<p class="small mb-0 fw-semibold"></p>';
        colocarIcone(coluna.querySelector(".liga-icone"), liga.icone);
        coluna.querySelector("p").textContent = liga.nome;
        faixa.appendChild(coluna);
    });

    const atual = dadosDaLiga(jogador.liga);
    document.getElementById("texto-liga").textContent = "Você está na Liga " + atual.nome;
    document.getElementById("titulo-ranking").textContent = "Liga " + atual.nome;
    document.getElementById("fim-semana").textContent = textoFimDaSemana();
}

function mostrarRanking() {
    const lista = document.getElementById("lista-ranking");
    lista.textContent = "";

    const ordenado = RANKING.slice().sort(function (a, b) { return b.xpSemana - a.xpSemana; });
    const alguemPontuou = ordenado.some(function (p) { return p.xpSemana > 0; });

    if (ordenado.length === 0) {
        const p = document.createElement("p");
        p.className = "text-muted text-center my-3";
        p.textContent = "Ninguém está nesta liga ainda.";
        lista.appendChild(p);
        return;
    }

    if (!alguemPontuou) {
        const aviso = document.createElement("p");
        aviso.className = "small text-muted text-center mb-2";
        aviso.textContent = "Ninguém pontuou nesta liga nesta semana ainda. Seja o primeiro!";
        lista.appendChild(aviso);
    }

    ordenado.forEach(function (pessoa, i) {
        const posicao = i + 1;

        const linha = document.createElement("div");
        linha.className = "linha-ranking d-flex align-items-center gap-3 px-3 py-2" + (pessoa.voce ? " voce" : "");
        linha.innerHTML =
            '<span class="posicao-ranking"></span>' +
            '<span class="inicial-ranking rounded-circle d-inline-flex align-items-center justify-content-center"></span>' +
            '<span class="flex-grow-1 nome-ranking"></span>' +
            '<span class="xp-ranking fw-semibold"></span>';

        if (PREMIOS[posicao] && pessoa.xpSemana > 0) {
            colocarIcone(linha.querySelector(".posicao-ranking"), "bi-trophy-fill " + PREMIOS[posicao]);
        } else {
            linha.querySelector(".posicao-ranking").textContent = posicao;
        }
        linha.querySelector(".inicial-ranking").textContent = pessoa.nome.charAt(0).toUpperCase();
        linha.querySelector(".nome-ranking").textContent = pessoa.voce ? pessoa.nome + " (você)" : pessoa.nome;
        linha.querySelector(".xp-ranking").textContent = pessoa.xpSemana + " XP";

        lista.appendChild(linha);
    });
}

mostrarLigas();

async function carregarRanking() {
    try {
        const resposta = await chamarApi("GET", "/api/ranking/semana");
        if (!resposta.ok) return;
        RANKING = resposta.dados.pessoas || [];
        mostrarLigas();
        mostrarRanking();
    } catch (erro) {
        const lista = document.getElementById("lista-ranking");
        lista.textContent = "Não foi possível carregar o ranking.";
    }
}

document.addEventListener("DOMContentLoaded", carregarRanking);

document.addEventListener("signedu:progresso", function () {
    mostrarLigas();
    if (RANKING.length > 0) mostrarRanking();
});
