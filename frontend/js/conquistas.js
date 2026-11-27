// conquistas.js - lista real de conquistas do usuário (GET /api/usuarios/conquistas)

let conquistas = [];
let filtroAtual = "todas";

const modal = new bootstrap.Modal(document.getElementById("modal-conquista"));

function formatarData(textoData) {
    if (!textoData) return "—";
    const data = new Date(textoData);
    return data.toLocaleDateString("pt-BR") + " às " +
           data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function mostrarResumo() {
    const ganhas = conquistas.filter(function (c) { return c.conquistada; });
    const pontos = ganhas.reduce(function (soma, c) { return soma + c.pontos; }, 0);
    const porcentagem = conquistas.length > 0 ? Math.round((ganhas.length / conquistas.length) * 100) : 0;

    document.getElementById("resumo-conquistas").textContent =
        ganhas.length + " de " + conquistas.length + " conquistas";
    document.getElementById("resumo-pontos").textContent = pontos + " pts";

    const barra = document.getElementById("barra-resumo");
    barra.style.width = porcentagem + "%";
    barra.setAttribute("aria-valuenow", porcentagem);
}

function mostrarConquistas() {
    const lista = document.getElementById("lista-conquistas");
    lista.textContent = "";

    const visiveis = conquistas.filter(function (c) {
        if (filtroAtual === "conquistadas") return c.conquistada;
        if (filtroAtual === "bloqueadas") return !c.conquistada;
        return true;
    });

    if (visiveis.length === 0) {
        const vazio = document.createElement("p");
        vazio.className = "text-muted";
        vazio.textContent = "Nenhuma conquista aqui ainda.";
        lista.appendChild(vazio);
        return;
    }

    visiveis.forEach(function (c) {
        const coluna = document.createElement("div");
        coluna.className = "col-6 col-md-4 col-lg-3";

        const card = document.createElement("button");
        card.type = "button";
        card.className = "card card-conquista h-100 w-100" + (c.conquistada ? "" : " bloqueada");
        // Sem aria-label: o nome lido pelo leitor de tela é o próprio texto do cartão (nome +
        // situação), igual ao que aparece na tela (WCAG 2.5.3).

        const corpo = document.createElement("div");
        corpo.className = "card-body w-100";

        const iconeDiv = document.createElement("div");
        iconeDiv.className = "icone-conquista";
        colocarIcone(iconeDiv, c.icone);

        const nomeP = document.createElement("p");
        nomeP.className = "mb-1";
        nomeP.textContent = c.nome;

        const rodape = document.createElement("span");
        if (c.conquistada) {
            rodape.className = "badge bg-primary";
            rodape.textContent = "+" + c.pontos + " pts";
        } else {
            rodape.className = "small text-muted";
            const cadeado = document.createElement("i");
            cadeado.className = "bi bi-lock-fill";
            cadeado.setAttribute("aria-hidden", "true");
            rodape.appendChild(cadeado);
            rodape.appendChild(document.createTextNode(" " + c.progressoAtual + " / " + c.progressoTotal));
        }
        // situação lida pelo leitor de tela (o cadeado e a cor só aparecem para quem enxerga)
        const situacao = document.createElement("span");
        situacao.className = "visually-hidden";
        situacao.textContent = c.conquistada ? " (conquistada)" : " (bloqueada)";
        rodape.appendChild(situacao);

        corpo.appendChild(iconeDiv);
        corpo.appendChild(nomeP);
        corpo.appendChild(rodape);
        card.appendChild(corpo);
        card.addEventListener("click", function () { abrirDetalhe(c); });

        coluna.appendChild(card);
        lista.appendChild(coluna);
    });
}

function abrirDetalhe(c) {
    colocarIcone(document.getElementById("modal-icone"), c.icone);
    document.getElementById("modal-titulo").textContent = c.nome;
    document.getElementById("modal-pontos").textContent = "+" + c.pontos + " pts";
    document.getElementById("modal-descricao").textContent = c.descricao;

    const blocoProgresso = document.getElementById("modal-bloco-progresso");

    if (c.conquistada) {
        document.getElementById("modal-subtitulo").textContent = "Você conseguiu!";
        document.getElementById("modal-como").textContent = c.comoConseguiu;
        document.getElementById("modal-data").textContent = "Conquistada em " + formatarData(c.dataConquista);
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

    modal.show();
}

document.querySelectorAll("#filtros button").forEach(function (botao) {
    botao.addEventListener("click", function () {
        document.querySelectorAll("#filtros button").forEach(function (b) { b.classList.remove("active"); });
        botao.classList.add("active");
        filtroAtual = botao.dataset.filtro;
        mostrarConquistas();
    });
});

async function carregarConquistas() {
    try {
        const resposta = await chamarApi("GET", "/api/usuarios/conquistas");
        if (!resposta.ok || !resposta.dados) return;
        conquistas = resposta.dados.conquistas || [];
        mostrarResumo();
        mostrarConquistas();
    } catch (erro) {
        const lista = document.getElementById("lista-conquistas");
        lista.textContent = "Não foi possível carregar as conquistas.";
    }
}

carregarConquistas();
