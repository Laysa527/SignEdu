// login.js - validação dos formulários de login e cadastro

// tipo: "danger" (erro) ou "success"
function mostrarMensagem(idDaCaixa, texto, tipo) {
    const caixa = document.getElementById(idDaCaixa);
    caixa.textContent = texto;
    caixa.className = "alert alert-" + tipo;
}


// Manda um POST em JSON pro back e devolve { ok, status, dados }
async function enviarJson(rota, corpo) {
    const resposta = await fetch(rota, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo)
    });

    let dados = null;
    try { dados = await resposta.json(); } catch (erro) {}
    return { ok: resposta.ok, status: resposta.status, dados: dados };
}

// Se a pessoa já está logada, não precisa ver a tela de login de novo
fetch("/api/usuarios/me", { credentials: "same-origin" }).then(function (resposta) {
    if (resposta.ok) window.location.href = "perfil.html";
}).catch(function () {});


// Login
const formLogin = document.getElementById("form-login");

formLogin.addEventListener("submit", async function (evento) {
    evento.preventDefault();
    formLogin.classList.add("was-validated");

    if (!formLogin.checkValidity()) {
        return;
    }

    const email = document.getElementById("login-email").value.trim();
    const senha = document.getElementById("login-senha").value;

    // O login volta num cookie HttpOnly (RNF06), que o navegador guarda sozinho.
    try {
        const resposta = await enviarJson("/api/auth/login", { email: email, senha: senha });
        if (resposta.ok) {
            try {
                localStorage.removeItem("signedu-progresso");
                localStorage.removeItem("signedu-config");
            } catch (erro) {}
            window.location.href = "perfil.html";
            return;
        }
        mostrarMensagem("mensagem-login", (resposta.dados && resposta.dados.erro) || "Não foi possível entrar.", "danger");
    } catch (erro) {
        mostrarMensagem("mensagem-login", "Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
});


// Cadastro
const formCadastro = document.getElementById("form-cadastro");
const campoSenha = document.getElementById("cadastro-senha");
const campoConfirmar = document.getElementById("cadastro-confirmar");

function conferirSenhas() {
    if (campoConfirmar.value !== campoSenha.value) {
        campoConfirmar.setCustomValidity("As senhas não são iguais.");
    } else {
        campoConfirmar.setCustomValidity("");
    }
}

campoSenha.addEventListener("input", conferirSenhas);
campoConfirmar.addEventListener("input", conferirSenhas);

formCadastro.addEventListener("submit", async function (evento) {
    evento.preventDefault();

    conferirSenhas();
    formCadastro.classList.add("was-validated");

    if (!formCadastro.checkValidity()) {
        return;
    }

    // Antes de criar a conta, a pessoa precisa aceitar os Termos de Uso e a Política de Privacidade
    abrirTermos();
});


const MENSAGEM_SEM_ACEITE = "O cadastro e o acesso à plataforma só podem acontecer mediante a aceitação dos " +
                            "Termos de Uso e da Política de Privacidade.";
let janelaTermos = null;

// Mostra os termos (o mesmo texto da página termos.html) numa janela com "Li e aceito" e "Não aceito"
async function abrirTermos() {
    const caixa = document.getElementById("texto-termos");
    if (!caixa.dataset.carregado) {
        try {
            const html = await (await fetch("termos.html")).text();
            const conteudo = new DOMParser().parseFromString(html, "text/html").getElementById("conteudo-termos");
            caixa.replaceChildren(...conteudo.childNodes);
            caixa.dataset.carregado = "1";
        } catch (erro) {
            caixa.innerHTML = 'Leia os termos em <a href="termos.html" target="_blank" rel="noopener">termos.html</a>.';
        }
    }
    janelaTermos = janelaTermos || new bootstrap.Modal(document.getElementById("modal-termos"));
    janelaTermos.show();
}

document.getElementById("btn-recusar-termos").addEventListener("click", function () {
    janelaTermos.hide();
    mostrarMensagem("mensagem-cadastro", MENSAGEM_SEM_ACEITE, "warning");
});

document.getElementById("btn-aceitar-termos").addEventListener("click", async function () {
    janelaTermos.hide();
    await criarConta();
});


async function criarConta() {
    const nome = document.getElementById("cadastro-nome").value.trim();
    const email = document.getElementById("cadastro-email").value.trim();
    const senha = campoSenha.value;

    try {
        const resposta = await enviarJson("/api/auth/cadastro",
                                          { nome: nome, email: email, senha: senha, aceiteTermos: true });
        if (resposta.ok) {
            try {
                localStorage.removeItem("signedu-progresso");
                localStorage.removeItem("signedu-config");
            } catch (erro) {}
            window.location.href = "perfil.html";   // o cadastro já deixa a pessoa logada
            return;
        }
        mostrarMensagem("mensagem-cadastro", (resposta.dados && resposta.dados.erro) || "Não foi possível criar a conta.", "danger");
    } catch (erro) {
        mostrarMensagem("mensagem-cadastro", "Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
}
