// conta.js - dados da conta, foto de perfil, troca de senha e exclusão

function mostrarMensagem(idDaCaixa, texto, tipo) {
    const caixa = document.getElementById(idDaCaixa);
    caixa.textContent = texto;
    caixa.className = "alert mt-3 alert-" + tipo;
}

function formatarData(textoData) {
    const data = new Date(textoData);
    return data.toLocaleDateString("pt-BR");
}

function textoDoErro(resposta, padrao) {
    return (resposta.dados && resposta.dados.erro) || padrao;
}

// Foto de perfil
const TAMANHO_MAXIMO_FOTO = 2 * 1024 * 1024; // 2 MB
const TIPOS_FOTO = ["image/png", "image/jpeg", "image/webp"];

const campoFoto = document.getElementById("campo-foto");
const imagemFoto = document.getElementById("imagem-foto");
const iconeSemFoto = document.getElementById("icone-sem-foto");
const botaoSalvarFoto = document.getElementById("btn-salvar-foto");
const botaoRemoverFoto = document.getElementById("btn-remover-foto");
let fotoEscolhida = null;

function mostrarFoto(endereco) {
    if (endereco) {
        imagemFoto.src = endereco;
        imagemFoto.classList.remove("d-none");
        iconeSemFoto.classList.add("d-none");
        botaoRemoverFoto.classList.remove("d-none");
    } else {
        imagemFoto.src = "";
        imagemFoto.classList.add("d-none");
        iconeSemFoto.classList.remove("d-none");
        botaoRemoverFoto.classList.add("d-none");
    }
}

async function carregarConta() {
    try {
        const resposta = await chamarApi("GET", "/api/usuarios/me");
        if (!resposta.ok) return;

        const usuario = resposta.dados;
        document.getElementById("conta-nome").value = usuario.nome;
        document.getElementById("conta-email").textContent = usuario.email;
        document.getElementById("conta-criacao").textContent =
            usuario.dataCriacao ? formatarData(usuario.dataCriacao) : "—";
        mostrarFoto(usuario.fotoUrl || null);
    } catch (erro) {
        mostrarMensagem("mensagem-dados", "Não foi possível carregar os dados da conta.", "danger");
    }
}

carregarConta();

document.getElementById("btn-escolher-foto").addEventListener("click", function () {
    campoFoto.click();
});

campoFoto.addEventListener("change", function () {
    const arquivo = campoFoto.files[0];
    if (!arquivo) return;

    if (!TIPOS_FOTO.includes(arquivo.type)) {
        mostrarMensagem("mensagem-foto", "Escolha uma imagem JPG, PNG ou WEBP.", "danger");
        campoFoto.value = "";
        return;
    }
    if (arquivo.size > TAMANHO_MAXIMO_FOTO) {
        mostrarMensagem("mensagem-foto", "A imagem precisa ter até 2 MB.", "danger");
        campoFoto.value = "";
        return;
    }

    fotoEscolhida = arquivo;
    mostrarFoto(URL.createObjectURL(arquivo));
    botaoSalvarFoto.classList.remove("d-none");
    document.getElementById("mensagem-foto").className = "alert d-none mt-3";
});

botaoSalvarFoto.addEventListener("click", async function () {
    if (!fotoEscolhida) return;
    botaoSalvarFoto.disabled = true;

    const dados = new FormData();
    dados.append("foto", fotoEscolhida, fotoEscolhida.name);

    try {
        const bruto = await fetch("/api/usuarios/me/foto", {
            method: "POST",
            credentials: "same-origin",
            body: dados
        });
        let corpo = null;
        try { corpo = await bruto.json(); } catch (erro) {}

        if (bruto.status === 401) { irParaLogin(); return; }
        if (bruto.ok) {
            fotoEscolhida = null;
            campoFoto.value = "";
            mostrarFoto(corpo.fotoUrl);
            botaoSalvarFoto.classList.add("d-none");
            mostrarMensagem("mensagem-foto", "Foto salva.", "success");
            atualizarProgresso();
        } else {
            mostrarMensagem("mensagem-foto", (corpo && corpo.erro) || "Não foi possível salvar a foto.", "danger");
        }
    } catch (erro) {
        mostrarMensagem("mensagem-foto", "Sem resposta do servidor.", "danger");
    } finally {
        botaoSalvarFoto.disabled = false;
    }
});

botaoRemoverFoto.addEventListener("click", async function () {
    botaoRemoverFoto.disabled = true;
    try {
        const resposta = await chamarApi("DELETE", "/api/usuarios/me/foto", {});
        if (resposta.ok) {
            fotoEscolhida = null;
            campoFoto.value = "";
            mostrarFoto(null);
            botaoSalvarFoto.classList.add("d-none");
            mostrarMensagem("mensagem-foto", "Foto removida.", "success");
            atualizarProgresso();
        } else {
            mostrarMensagem("mensagem-foto", textoDoErro(resposta, "Não foi possível remover a foto."), "danger");
        }
    } catch (erro) {
        mostrarMensagem("mensagem-foto", "Sem resposta do servidor.", "danger");
    } finally {
        botaoRemoverFoto.disabled = false;
    }
});


// Nome
const formDados = document.getElementById("form-dados");

formDados.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    formDados.classList.add("was-validated");

    if (!formDados.checkValidity()) {
        return;
    }

    const nome = document.getElementById("conta-nome").value.trim();

    try {
        const resposta = await chamarApi("PUT", "/api/usuarios/me", { nome: nome });
        if (resposta.ok) {
            document.getElementById("conta-nome").value = resposta.dados.nome;
            mostrarMensagem("mensagem-dados", "Nome salvo.", "success");
            atualizarProgresso();
        } else {
            mostrarMensagem("mensagem-dados", textoDoErro(resposta, "Não foi possível salvar o nome."), "danger");
        }
    } catch (erro) {
        mostrarMensagem("mensagem-dados", "Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
});


// Troca de senha
const formSenha = document.getElementById("form-senha");
const campoAtual = document.getElementById("senha-atual");
const campoNova = document.getElementById("senha-nova");
const campoConfirmar = document.getElementById("senha-confirmar");
const erroNova = document.getElementById("erro-senha-nova");

function conferirSenhas() {
    if (campoNova.value !== "" && campoNova.value === campoAtual.value) {
        campoNova.setCustomValidity("A nova senha precisa ser diferente da atual.");
        erroNova.textContent = "A nova senha precisa ser diferente da atual.";
    } else {
        campoNova.setCustomValidity("");
        erroNova.textContent = "A senha precisa ter pelo menos 8 caracteres.";
    }

    if (campoConfirmar.value !== campoNova.value) {
        campoConfirmar.setCustomValidity("As senhas não são iguais.");
    } else {
        campoConfirmar.setCustomValidity("");
    }
}

campoAtual.addEventListener("input", conferirSenhas);
campoNova.addEventListener("input", conferirSenhas);
campoConfirmar.addEventListener("input", conferirSenhas);

formSenha.addEventListener("submit", async function (evento) {
    evento.preventDefault();

    conferirSenhas();
    formSenha.classList.add("was-validated");

    if (!formSenha.checkValidity()) {
        return;
    }

    try {
        const resposta = await chamarApi("PUT", "/api/usuarios/me/senha", {
            senhaAtual: campoAtual.value,
            novaSenha: campoNova.value
        });
        if (resposta.ok) {
            mostrarMensagem("mensagem-senha", "Senha alterada.", "success");
            formSenha.reset();
            formSenha.classList.remove("was-validated");
        } else {
            mostrarMensagem("mensagem-senha", textoDoErro(resposta, "Não foi possível trocar a senha."), "danger");
        }
    } catch (erro) {
        mostrarMensagem("mensagem-senha", "Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
});


// Excluir conta - exige motivo e confirmação de senha atual
const formExcluir = document.getElementById("form-excluir");
const botaoExcluir = document.getElementById("btn-excluir");
const campoSenhaExcluir = document.getElementById("excluir-senha");
const opcoesMotivo = document.querySelectorAll('input[name="motivo"]');

const CAMPOS_MOTIVO = {
    problemas_tecnicos: { bloco: "bloco-erro", texto: "texto-erro" },
    insatisfeito: { bloco: "bloco-insatisfacao", texto: "texto-insatisfacao" }
};

function motivoEscolhido() {
    const marcado = document.querySelector('input[name="motivo"]:checked');
    return marcado ? marcado.value : null;
}

function conferirExclusao() {
    const motivo = motivoEscolhido();
    let faltaTexto = false;

    for (const chave in CAMPOS_MOTIVO) {
        const bloco = document.getElementById(CAMPOS_MOTIVO[chave].bloco);
        const texto = document.getElementById(CAMPOS_MOTIVO[chave].texto);
        const escolhido = motivo === chave;

        bloco.classList.toggle("d-none", !escolhido);
        texto.required = escolhido;

        if (escolhido && texto.value.trim() === "") {
            faltaTexto = true;
        }
    }

    const faltaSenha = campoSenhaExcluir.value.trim() === "";
    botaoExcluir.disabled = motivo === null || faltaTexto || faltaSenha;
}

opcoesMotivo.forEach(function (opcao) {
    opcao.addEventListener("change", conferirExclusao);
});
for (const chave in CAMPOS_MOTIVO) {
    document.getElementById(CAMPOS_MOTIVO[chave].texto).addEventListener("input", conferirExclusao);
}
campoSenhaExcluir.addEventListener("input", conferirExclusao);

document.getElementById("modal-excluir").addEventListener("hidden.bs.modal", function () {
    formExcluir.reset();
    formExcluir.classList.remove("was-validated");
    document.getElementById("mensagem-excluir").className = "alert d-none mt-3 mb-0";
    conferirExclusao();
});

formExcluir.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    formExcluir.classList.add("was-validated");

    if (!formExcluir.checkValidity()) {
        return;
    }

    const motivo = motivoEscolhido();
    const comentario = CAMPOS_MOTIVO[motivo]
        ? document.getElementById(CAMPOS_MOTIVO[motivo].texto).value.trim()
        : "";
    const senhaAtual = campoSenhaExcluir.value;

    try {
        const resposta = await chamarApi("DELETE", "/api/usuarios/me", {
            motivo: motivo,
            comentario: comentario,
            senhaAtual: senhaAtual
        });
        if (resposta.ok) {
            irParaLogin();
        } else {
            mostrarMensagem("mensagem-excluir", textoDoErro(resposta, "Não foi possível excluir a conta."), "danger");
        }
    } catch (erro) {
        mostrarMensagem("mensagem-excluir", "Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
});
