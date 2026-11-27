// configuracoes.js - preferências do usuário salvas no banco (GET/PUT /api/usuarios/configuracoes)

const PADRAO = {
    meta: "10",
    avisoMeta: true,
    velocidade: "1",
    lembrete: false,
    horario: "19:00",
    avisoConquista: true,
    fonte: "100"
};

const CAMPOS = {
    meta: "config-meta",
    avisoMeta: "config-aviso-meta",
    velocidade: "config-velocidade",
    lembrete: "config-lembrete",
    horario: "config-horario",
    avisoConquista: "config-aviso-conquista",
    fonte: "config-fonte"
};

function mostrarMensagem(texto, tipo) {
    const caixa = document.getElementById("mensagem-config");
    caixa.textContent = texto;
    caixa.className = "alert mt-4 alert-" + tipo;
}

function preencherTela(config) {
    for (const chave in CAMPOS) {
        const campo = document.getElementById(CAMPOS[chave]);
        if (campo.type === "checkbox") {
            campo.checked = Boolean(config[chave]);
        } else {
            campo.value = config[chave];
        }
    }
    atualizarTela();
}

function lerTela() {
    const config = {};
    for (const chave in CAMPOS) {
        const campo = document.getElementById(CAMPOS[chave]);
        config[chave] = campo.type === "checkbox" ? campo.checked : campo.value;
    }
    return config;
}

function atualizarTela() {
    const fonte = document.getElementById("config-fonte").value;
    aplicarTamanhoTexto(fonte);

    document.querySelectorAll("#escala-fonte button").forEach(function (botao) {
        botao.classList.toggle("selecionado", botao.dataset.valor === fonte);
    });

    const avisoMetaLigado = document.getElementById("config-aviso-meta").checked;
    document.getElementById("btn-exemplo-meta").classList.toggle("d-none", !avisoMetaLigado);

    const avisoConquistaLigado = document.getElementById("config-aviso-conquista").checked;
    document.getElementById("btn-exemplo-conquista").classList.toggle("d-none", !avisoConquistaLigado);

    const lembreteLigado = document.getElementById("config-lembrete").checked;
    document.getElementById("config-horario").disabled = !lembreteLigado;
}

document.getElementById("config-fonte").addEventListener("input", atualizarTela);
document.getElementById("config-lembrete").addEventListener("change", atualizarTela);
document.getElementById("config-aviso-meta").addEventListener("change", atualizarTela);
document.getElementById("config-aviso-conquista").addEventListener("change", atualizarTela);

document.querySelectorAll("#escala-fonte button").forEach(function (botao) {
    botao.addEventListener("click", function () {
        document.getElementById("config-fonte").value = botao.dataset.valor;
        atualizarTela();
    });
});

document.getElementById("btn-exemplo-meta").addEventListener("click", function () {
    const minutos = document.getElementById("config-meta").value;
    avisarMetaCumprida(minutos, true);
});

document.getElementById("btn-exemplo-conquista").addEventListener("click", function () {
    avisarConquista({ icone: "bi-hand-index-thumb", nome: "Primeiro Sinal", pontos: 20 }, true);
});

async function carregarConfiguracoes() {
    const cache = lerConfiguracoesSalvas();
    preencherTela(Object.assign({}, PADRAO, cache));

    try {
        const resposta = await chamarApi("GET", "/api/usuarios/configuracoes");
        if (resposta.ok && resposta.dados) {
            localStorage.setItem(CHAVE_CONFIG, JSON.stringify(resposta.dados));
            preencherTela(Object.assign({}, PADRAO, resposta.dados));
        }
    } catch (erro) {}
}

carregarConfiguracoes();

document.getElementById("form-config").addEventListener("submit", async function (evento) {
    evento.preventDefault();
    const config = lerTela();

    try {
        const resposta = await chamarApi("PUT", "/api/usuarios/configuracoes", config);
        if (resposta.ok) {
            localStorage.setItem(CHAVE_CONFIG, JSON.stringify(resposta.dados));
            mostrarMensagem("Configurações salvas na sua conta.", "success");
        } else {
            mostrarMensagem((resposta.dados && resposta.dados.erro) || "Não foi possível salvar.", "danger");
        }
    } catch (erro) {
        mostrarMensagem("Sem resposta do servidor.", "danger");
    }
});

document.getElementById("btn-restaurar").addEventListener("click", function () {
    preencherTela(PADRAO);
    mostrarMensagem("Voltou tudo ao padrão. Clique em salvar para confirmar.", "secondary");
});
