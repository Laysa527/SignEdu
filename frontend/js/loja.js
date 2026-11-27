// loja.js - loja real conectada ao banco (GET /api/loja, POST /api/loja/comprar, POST /api/loja/usar)

let ITENS = [];
let LOJA_MOLDURAS = [];
let estadoLoja = { moedas: 0, itens: {}, molduras: [], moldura: null, xpDobroAtivo: false };

const modalCompra = new bootstrap.Modal(document.getElementById("modal-compra"));
let compraPendente = null;

function mostrarSaldo() {
    document.getElementById("saldo-loja").textContent = estadoLoja.moedas + " moedas";
}

function botaoComprar(preco, moedas, desabilitarPorLimite) {
    if (desabilitarPorLimite) {
        return '<button type="button" class="btn btn-light w-100" disabled>Limite atingido</button>';
    }
    if (moedas < preco) {
        return '<button type="button" class="btn btn-light w-100" disabled>Faltam ' + (preco - moedas) + ' moedas</button>';
    }
    return '<button type="button" class="btn btn-primary w-100 btn-comprar">Comprar</button>';
}

function mostrarItens() {
    const lista = document.getElementById("lista-itens");
    lista.textContent = "";

    ITENS.forEach(function (item) {
        const quantidade = estadoLoja.itens[item.id] || 0;
        const noLimite = quantidade >= item.maximo;

        let botaoUsar = "";
        if (item.usavel && quantidade > 0) {
            botaoUsar = '<button type="button" class="btn btn-outline-success w-100 mt-2 btn-usar-item">' +
                (estadoLoja.xpDobroAtivo ? "Ativo (+15 min)" : "Usar agora (15 min)") + '</button>';
        }

        const coluna = document.createElement("div");
        coluna.className = "col-12 col-md-6 col-lg-4";
        coluna.innerHTML =
            '<div class="card h-100">' +
                '<div class="card-body d-flex flex-column">' +
                    '<div class="icone-loja"></div>' +
                    '<p class="fw-semibold mb-1 nome-item"></p>' +
                    '<p class="small mb-2 desc-item"></p>' +
                    '<p class="small text-muted mb-2">Você tem: ' + quantidade + ' de ' + item.maximo + '</p>' +
                    '<p class="mb-3"><span class="badge bg-primary">' + item.preco + ' moedas</span></p>' +
                    '<div class="mt-auto">' + botaoComprar(item.preco, estadoLoja.moedas, noLimite) + botaoUsar + '</div>' +
                '</div>' +
            '</div>';

        colocarIcone(coluna.querySelector(".icone-loja"), item.icone);
        coluna.querySelector(".nome-item").textContent = item.nome;
        coluna.querySelector(".desc-item").textContent = item.descricao;

        const botao = coluna.querySelector(".btn-comprar");
        if (botao) {
            botao.addEventListener("click", function () {
                pedirConfirmacao({ tipo: "item", id: item.id, icone: item.icone, nome: item.nome, preco: item.preco });
            });
        }

        const usar = coluna.querySelector(".btn-usar-item");
        if (usar) {
            usar.addEventListener("click", function () { usarItem(item); });
        }

        lista.appendChild(coluna);
    });
}

function mostrarMolduras() {
    const lista = document.getElementById("lista-molduras");
    lista.textContent = "";

    LOJA_MOLDURAS.forEach(function (m) {
        const dados = MOLDURAS[m.id];
        if (!dados) return;
        const comprada = estadoLoja.molduras.includes(m.id);
        const emUso = estadoLoja.moldura === m.id;

        let botao;
        if (emUso) {
            botao = '<button type="button" class="btn btn-light sidebar-btn w-100 btn-tirar">Em uso · tirar</button>';
        } else if (comprada) {
            botao = '<button type="button" class="btn btn-primary w-100 btn-usar">Usar</button>';
        } else {
            botao = botaoComprar(m.preco, estadoLoja.moedas, false);
        }

        const coluna = document.createElement("div");
        coluna.className = "col-6 col-md-4 col-lg-3";
        coluna.innerHTML =
            '<div class="card h-100">' +
                '<div class="card-body d-flex flex-column align-items-center">' +
                    '<div class="avatar previa-moldura rounded-circle bg-light d-inline-flex align-items-center justify-content-center mb-3 ' + dados.classe + '"><i class="bi bi-person-fill" aria-hidden="true"></i></div>' +
                    '<p class="fw-semibold mb-1"></p>' +
                    '<p class="small mb-2 desc-moldura"></p>' +
                    (comprada ? '<p class="small text-muted mb-3"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> Já é sua</p>' : '<p class="mb-3"><span class="badge bg-primary">' + m.preco + ' moedas</span></p>') +
                    '<div class="mt-auto w-100">' + botao + '</div>' +
                '</div>' +
            '</div>';

        coluna.querySelector(".fw-semibold").textContent = "Moldura " + dados.nome;
        coluna.querySelector(".desc-moldura").textContent = m.descricao;

        const comprar = coluna.querySelector(".btn-comprar");
        if (comprar) comprar.addEventListener("click", function () {
            pedirConfirmacao({ tipo: "moldura", id: m.id, icone: "bi-image", nome: "Moldura " + dados.nome, preco: m.preco });
        });

        const usar = coluna.querySelector(".btn-usar");
        if (usar) usar.addEventListener("click", function () { trocarMoldura(m.id); });

        const tirar = coluna.querySelector(".btn-tirar");
        if (tirar) tirar.addEventListener("click", function () { trocarMoldura(null); });

        lista.appendChild(coluna);
    });
}

async function trocarMoldura(id) {
    try {
        const resposta = await chamarApi("PUT", "/api/usuarios/me/moldura", { moldura: id });
        if (!resposta.ok) {
            mostrarAvisoRapido("bi-exclamation-triangle", "Ops",
                (resposta.dados && resposta.dados.erro) || "Não foi possível trocar a moldura.", null);
            return;
        }
        await atualizarProgresso();
        await carregarLoja();
    } catch (erro) {}
}

async function usarItem(item) {
    try {
        const resposta = await chamarApi("POST", "/api/loja/usar", { id: item.id });
        if (!resposta.ok) {
            mostrarAvisoRapido("bi-exclamation-triangle", "Ops",
                (resposta.dados && resposta.dados.erro) || "Não foi possível usar o item.", null);
            return;
        }
        mostrarAvisoRapido(item.icone, "Item ativado!", item.nome + " ativo por 15 minutos.", "2x XP");
        await atualizarProgresso();
        await carregarLoja();
    } catch (erro) {}
}

function pedirConfirmacao(compra) {
    compraPendente = compra;
    colocarIcone(document.getElementById("compra-icone"), compra.icone);
    document.getElementById("titulo-compra").textContent = compra.nome;
    document.getElementById("compra-texto").textContent =
        "Comprar por " + compra.preco + " moedas? Vão sobrar " + (estadoLoja.moedas - compra.preco) + " moedas.";
    modalCompra.show();
}

document.getElementById("btn-confirmar-compra").addEventListener("click", async function () {
    if (!compraPendente) return;
    const botao = this;
    botao.disabled = true;

    try {
        const resposta = await chamarApi("POST", "/api/loja/comprar", {
            tipo: compraPendente.tipo,
            id: compraPendente.id
        });
        modalCompra.hide();

        if (!resposta.ok) {
            mostrarAvisoRapido("bi-exclamation-triangle", "Ops",
                (resposta.dados && resposta.dados.erro) || "Não foi possível concluir a compra.", null);
        } else {
            mostrarAvisoRapido(compraPendente.icone, "Compra feita!", compraPendente.nome,
                "-" + compraPendente.preco + " moedas");
            if (Array.isArray(resposta.dados.novasConquistas)) {
                resposta.dados.novasConquistas.forEach(function (c) { avisarConquista(c); });
            }
            await atualizarProgresso();
            await carregarLoja();
        }
    } catch (erro) {
        modalCompra.hide();
        mostrarAvisoRapido("bi-exclamation-triangle", "Ops", "Sem resposta do servidor.", null);
    } finally {
        compraPendente = null;
        botao.disabled = false;
    }
});

function atualizarTudo() {
    mostrarSaldo();
    mostrarItens();
    mostrarMolduras();
}

async function carregarLoja() {
    try {
        const resposta = await chamarApi("GET", "/api/loja");
        if (!resposta.ok || !resposta.dados) return;
        ITENS = resposta.dados.itens || [];
        LOJA_MOLDURAS = resposta.dados.molduras || [];
        const inv = resposta.dados.inventario || {};
        estadoLoja = {
            moedas: resposta.dados.moedas || 0,
            itens: inv.itens || {},
            molduras: inv.molduras || [],
            moldura: inv.moldura || null,
            xpDobroAtivo: Boolean(inv.xpDobroAtivo)
        };
        atualizarTudo();
    } catch (erro) {}
}

carregarLoja();

document.addEventListener("signedu:progresso", function () {
    carregarLoja();
});
