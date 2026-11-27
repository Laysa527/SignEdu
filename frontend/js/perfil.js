// perfil.js - preenche o perfil com o progresso e conquistas reais do banco

function mostrarPerfil(progresso) {
    const jogador = lerJogador();
    const nivel = progressoNoNivel(jogador);

    if (progresso && progresso.nome) {
        document.getElementById("perfil-saudacao").textContent = "Olá, " + progresso.nome + "!";
    }
    document.getElementById("perfil-titulo-nivel").textContent = nivel.atual.titulo;

    const barra = document.getElementById("perfil-barra-xp");
    barra.style.width = nivel.porcentagem + "%";
    barra.setAttribute("aria-valuenow", nivel.porcentagem);
    barra.textContent = nivel.proximo
        ? nivel.xpNoNivel + " / " + nivel.xpDoNivel + " XP"
        : jogador.xpTotal + " XP (nível máximo)";

    if (progresso) {
        document.getElementById("perfil-pontos").textContent = progresso.pontosTotais;
        document.getElementById("perfil-sinais").textContent = progresso.sinaisAprendidos;
        document.getElementById("perfil-acerto").textContent =
            progresso.taxaAcerto === null ? "—" : progresso.taxaAcerto + "%";
        document.getElementById("perfil-sequencia").textContent =
            progresso.sequenciaDias + (progresso.sequenciaDias === 1 ? " dia" : " dias");

        if (progresso.desafioDia) {
            const d = progresso.desafioDia;
            const pct = Math.min(100, Math.round((d.atual / d.total) * 100));
            const barraDesafio = document.getElementById("desafio-barra");
            if (barraDesafio) {
                barraDesafio.style.width = pct + "%";
                barraDesafio.setAttribute("aria-valuenow", pct);
                barraDesafio.textContent = d.atual + " / " + d.total;
            }
            const desc = document.getElementById("desafio-descricao");
            if (desc) {
                desc.textContent = d.concluido
                    ? "Desafio de hoje concluído! Parabéns!"
                    : "Acerte " + d.total + " sinais hoje";
            }
        }
    }
}

async function carregarResumoConquistas() {
    const container = document.getElementById("perfil-conquistas");
    if (!container) return;

    try {
        const resposta = await chamarApi("GET", "/api/usuarios/conquistas");
        if (!resposta.ok || !resposta.dados) return;

        // Últimas conquistas: as 4 ganhas mais recentes (da mais nova pra mais antiga)
        const todas = resposta.dados.conquistas || [];
        const destaque = todas.filter(function (c) { return c.conquistada; })
            .sort(function (a, b) { return String(b.dataConquista || "").localeCompare(String(a.dataConquista || "")); })
            .slice(0, 4);

        container.textContent = "";
        if (destaque.length === 0) {
            const vazio = document.createElement("p");
            vazio.className = "text-muted text-start mb-0";
            vazio.textContent = "Você ainda não tem conquistas. Pratique pra ganhar a primeira!";
            container.appendChild(vazio);
            return;
        }
        destaque.forEach(function (c) {
            const col = document.createElement("div");
            col.className = "col-6 col-md-3";

            const card = document.createElement("div");
            // clicável, igual à tela de conquistas: abre o detalhe
            card.className = "card card-conquista h-100";
            card.tabIndex = 0;
            card.setAttribute("role", "button");
            card.setAttribute("aria-label", c.nome + " (ver detalhes)");
            card.addEventListener("click", function () { abrirDetalheConquista(c); });
            card.addEventListener("keydown", function (evento) {
                if (evento.key === "Enter" || evento.key === " ") {
                    evento.preventDefault();
                    abrirDetalheConquista(c);
                }
            });

            const body = document.createElement("div");
            body.className = "card-body";

            const iconeDiv = document.createElement("div");
            iconeDiv.className = "icone-conquista";
            colocarIcone(iconeDiv, c.icone);

            const nomeP = document.createElement("p");
            nomeP.className = "mb-1";
            nomeP.textContent = c.nome;

            const badge = document.createElement("span");
            badge.className = c.conquistada ? "badge bg-primary" : "small text-muted";
            badge.textContent = c.conquistada
                ? "+" + c.pontos + " pts"
                : c.progressoAtual + " / " + c.progressoTotal;

            body.appendChild(iconeDiv);
            body.appendChild(nomeP);
            body.appendChild(badge);
            card.appendChild(body);
            col.appendChild(card);
            container.appendChild(col);
        });
    } catch (erro) {}
}

// Detalhe da conquista (mesmo pop-up da tela de conquistas)
function abrirDetalheConquista(c) {
    const caixa = document.getElementById("modal-conquista");
    if (!caixa) return;
    colocarIcone(document.getElementById("modal-icone"), c.icone);
    document.getElementById("modal-titulo").textContent = c.nome;
    document.getElementById("modal-pontos").textContent = "+" + c.pontos + " pts";
    document.getElementById("modal-descricao").textContent = c.descricao;
    const blocoProgresso = document.getElementById("modal-bloco-progresso");
    if (c.conquistada) {
        const data = c.dataConquista ? new Date(c.dataConquista) : null;
        document.getElementById("modal-subtitulo").textContent = "Você conseguiu!";
        document.getElementById("modal-como").textContent = c.comoConseguiu;
        document.getElementById("modal-data").textContent = data
            ? "Conquistada em " + data.toLocaleDateString("pt-BR") + " às " +
              data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
            : "";
        blocoProgresso.classList.add("d-none");
    } else {
        const porcentagem = Math.round((c.progressoAtual / c.progressoTotal) * 100);
        document.getElementById("modal-subtitulo").textContent = "Como conseguir";
        document.getElementById("modal-como").textContent = c.requisito;
        document.getElementById("modal-data").textContent = "";
        document.getElementById("modal-barra").style.width = porcentagem + "%";
        document.getElementById("modal-progresso-texto").textContent =
            c.progressoAtual + " de " + c.progressoTotal + " (" + porcentagem + "%)";
        blocoProgresso.classList.remove("d-none");
    }
    bootstrap.Modal.getOrCreateInstance(caixa).show();
}

mostrarPerfil(lerProgressoDoServidor());
carregarResumoConquistas();

document.addEventListener("signedu:progresso", function (evento) {
    mostrarPerfil(evento.detail);
});
