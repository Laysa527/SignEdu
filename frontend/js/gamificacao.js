// gamificacao.js - blocos de gamificação do perfil (liga, moedas, missões e trilha de níveis)

let missoes = [];

function mostrarLigaEMoedas() {
    const jogador = lerJogador();
    const liga = dadosDaLiga(jogador.liga);

    colocarIcone(document.getElementById("perfil-liga-icone"), liga.icone);
    document.getElementById("perfil-liga-nome").textContent = "Liga " + liga.nome;
    document.getElementById("perfil-liga-posicao").textContent =
        "Você está em " + jogador.posicaoRanking + "º lugar nesta semana";
    document.getElementById("perfil-moedas").textContent = jogador.moedas + " moedas";
}

function mostrarMissoes() {
    document.getElementById("missoes-fim").textContent = textoFimDaSemana();

    const lista = document.getElementById("lista-missoes");
    lista.textContent = "";

    if (missoes.length === 0) {
        const p = document.createElement("p");
        p.className = "text-muted mb-0";
        p.textContent = "Carregando missões...";
        lista.appendChild(p);
        return;
    }

    missoes.forEach(function (m) {
        const completa = m.atual >= m.total;
        const porcentagem = Math.min(100, Math.round((m.atual / m.total) * 100));

        const linha = document.createElement("div");
        linha.className = "missao d-flex flex-wrap align-items-center gap-3 p-3" + (m.resgatada ? " concluida" : "");

        let acao;
        if (m.resgatada) {
            acao = '<span class="small fw-semibold"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> Resgatada</span>';
        } else if (completa) {
            acao = '<button type="button" class="btn btn-primary btn-sm btn-resgatar">Resgatar</button>';
        } else {
            acao = '<span class="small text-muted">' + m.atual + ' / ' + m.total + '</span>';
        }

        linha.innerHTML =
            '<div class="icone-conquista"></div>' +
            '<div class="flex-grow-1">' +
                '<p class="mb-1 texto-missao"></p>' +
                '<div class="progress barra-missao">' +
                    '<div class="progress-bar ' + (completa ? 'bg-success' : 'bg-primary') + '" role="progressbar" aria-label="Progresso da missão" style="width: ' + porcentagem + '%;" aria-valuenow="' + porcentagem + '" aria-valuemin="0" aria-valuemax="100"></div>' +
                '</div>' +
            '</div>' +
            '<div class="text-end">' +
                '<p class="mb-1"><span class="badge bg-primary">+' + m.moedas + ' moedas</span> <span class="badge bg-primary">+' + m.xp + ' XP</span></p>' +
                acao +
            '</div>';

        colocarIcone(linha.querySelector(".icone-conquista"), m.icone);
        linha.querySelector(".texto-missao").textContent = m.texto;

        const botao = linha.querySelector(".btn-resgatar");
        if (botao) {
            botao.addEventListener("click", function () { resgatarMissao(m, botao); });
        }

        lista.appendChild(linha);
    });
}

async function carregarMissoes() {
    try {
        const resposta = await chamarApi("GET", "/api/missoes/semana");
        if (!resposta.ok || !resposta.dados) return;
        missoes = resposta.dados.missoes || [];
        mostrarMissoes();
    } catch (erro) {}
}

async function resgatarMissao(missao, botao) {
    botao.disabled = true;
    try {
        const resposta = await chamarApi("POST", "/api/missoes/" + missao.id + "/resgatar", {});
        if (!resposta.ok) {
            mostrarAvisoRapido("bi-exclamation-triangle", "Ops",
                (resposta.dados && resposta.dados.erro) || "Não foi possível resgatar.", null);
            botao.disabled = false;
            return;
        }

        const res = resposta.dados;
        mostrarAvisoRapido("bi-coin", "Missão concluída!", missao.texto,
            "+" + res.moedasGanhas + " moedas · +" + res.xpGanho + " XP");

        if (res.subiuDeNivel) {
            avisarSubiuNivel(res.nivel);
        }
        if (Array.isArray(res.novasConquistas)) {
            res.novasConquistas.forEach(function (c) { avisarConquista(c); });
        }

        await atualizarProgresso();
        await carregarMissoes();
    } catch (erro) {
        mostrarAvisoRapido("bi-exclamation-triangle", "Ops", "Sem resposta do servidor.", null);
        botao.disabled = false;
    }
}

function mostrarTrilha() {
    const jogador = lerJogador();
    const trilha = document.getElementById("trilha-niveis");
    trilha.textContent = "";

    NIVEIS.forEach(function (n) {
        let estado = "bloqueado";
        if (n.nivel < jogador.nivel) estado = "feito";
        if (n.nivel === jogador.nivel) estado = "atual";

        const passo = document.createElement("div");
        passo.className = "passo-nivel text-center " + estado;
        passo.innerHTML =
            '<div class="bolinha-nivel rounded-circle d-inline-flex align-items-center justify-content-center"></div>' +
            '<p class="small fw-semibold mb-0 mt-1">Nível ' + n.nivel + '</p>' +
            '<p class="small mb-0 titulo-passo"></p>';

        colocarIcone(passo.querySelector(".bolinha-nivel"), estado === "bloqueado" ? "bi-lock-fill" : n.icone);
        passo.querySelector(".titulo-passo").textContent = n.titulo;
        trilha.appendChild(passo);
    });

    const proximo = NIVEIS.find(function (n) { return n.nivel === jogador.nivel + 1; });
    const texto = document.getElementById("texto-proximo-nivel");
    if (proximo) {
        const falta = Math.max(0, proximo.xp - jogador.xpTotal);
        texto.textContent = "Faltam " + falta + " XP para virar " +
            proximo.titulo + " (nível " + proximo.nivel + ") e ganhar " + MOEDAS_POR_NIVEL + " moedas";
    } else {
        texto.textContent = "Você chegou ao nível máximo!";
    }
}

mostrarLigaEMoedas();
mostrarMissoes();
mostrarTrilha();
carregarMissoes();

document.addEventListener("signedu:progresso", function () {
    mostrarLigaEMoedas();
    mostrarTrilha();
});
