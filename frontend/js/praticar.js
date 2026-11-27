// praticar.js - liga a câmera, manda os quadros pro back (MediaPipe + Random Forest),
// desenha a mão e confere se a pessoa fez a letra certa

const ROTA_DETECTAR = "/api/maos/detectar";
const ROTA_MOVIMENTO = "/api/maos/movimento";        // sequência de quadros da câmera
const ROTA_VIDEO = "/api/maos/video";                // vídeo enviado
const ROTA_SINAIS_MOVIMENTO = "/api/sinais/movimento";
const ROTA_NUMEROS = "/api/sinais/numeros";          // números 0 a 9 (sinais parados)

// Sinais com movimento: contagem regressiva e tempo de gravação (em segundos)
const SEGUNDOS_CONTAGEM = 3;
const SEGUNDOS_GRAVACAO = 3;
const MAXIMO_QUADROS_GRAVADOS = 300;                 // o back aceita até 300
const TAMANHO_MAXIMO_VIDEO = 50 * 1024 * 1024;       // 50 MB, igual ao back
const EXTENSOES_VIDEO = [".mp4", ".mov", ".avi", ".webm", ".mkv"];

// Letras paradas que o modelo conhece (1 foto basta). H, J, K, X, Z e as saudações têm
// movimento: vêm do back (GET /api/sinais/movimento) se o modelo de vídeo foi treinado.
const LETRAS = ["A", "B", "C", "D", "E", "F", "G", "I", "L", "M", "N",
                "O", "P", "Q", "R", "S", "T", "U", "V", "W", "Y"];

// Só mostra a letra se o modelo tiver pelo menos essa certeza (0 a 1)
const CERTEZA_MINIMA = 0.5;
// Sinais com movimento: o sinal certo precisa ser o mais provável e ter pelo menos 30%
// (o back manda o valor dele em "certezaMinima"; este é só o padrão)
const CERTEZA_MINIMA_MOVIMENTO = 0.3;

// Reconhecimento automático dos sinais com movimento (sem apertar Gravar): o site guarda os
// últimos segundos da câmera e, de tempos em tempos, pergunta ao back qual sinal foi feito.
const JANELA_AUTO_MS = 3000;        // quanto tempo de câmera vai em cada verificação
const MINIMO_JANELA_AUTO_MS = 2000; // só verifica depois de ter pelo menos isso guardado
const INTERVALO_AUTO_MS = 800;      // de quanto em quanto tempo verifica
// Só vale quando o sinal certo aparece em 2 verificações SEGUIDAS (0,8 s de diferença):
// um movimento qualquer de passagem (ex.: levantar a mão) não basta, o sinal precisa continuar.
const CONFIRMACOES_AUTO = 2;
let confirmacoesAuto = 0;

// Quantos quadros seguidos a pessoa precisa segurar o sinal certo pra acertar
const QUADROS_PARA_ACERTAR = 8;

// Tamanho do quadro que vai pro back. Menor = mais rápido.
// No celular a imagem vai pelo Wi-Fi até o computador: um quadro menor chega mais rápido
// (o MediaPipe acha a mão bem nesse tamanho). MAIOR_LADO vale pro lado maior da imagem,
// então serve com o celular em pé ou deitado.
const NO_CELULAR = window.matchMedia("(pointer: coarse)").matches;
const MAIOR_LADO_ENVIO = NO_CELULAR ? 480 : 640;
const QUALIDADE_JPEG = NO_CELULAR ? 0.6 : 0.7;
// Quantos quadros podem estar "a caminho" do servidor ao mesmo tempo. Com 2, enquanto um quadro
// está sendo analisado o próximo já está viajando pela rede (no celular isso quase dobra os
// quadros por segundo).
const PEDIDOS_SIMULTANEOS = 2;

// Mesmas ligações entre os 21 pontos do hand_landmarker_test.py
const LIGACOES_MAO = [
    [0, 1], [1, 2], [2, 3], [3, 4],          // polegar
    [0, 5], [5, 6], [6, 7], [7, 8],          // indicador
    [5, 9], [9, 10], [10, 11], [11, 12],     // médio
    [9, 13], [13, 14], [14, 15], [15, 16],   // anelar
    [13, 17], [17, 18], [18, 19], [19, 20],  // mínimo
    [0, 17],                                  // base da palma
];

const video = document.getElementById("video");
const canvasDesenho = document.getElementById("canvas-desenho");
const ctxDesenho = canvasDesenho.getContext("2d");
const avisoCamera = document.getElementById("aviso-camera");
const btnLigar = document.getElementById("btn-ligar");
const btnDesligar = document.getElementById("btn-desligar");

// Canvas "escondido" usado só pra montar a imagem que vai pro back
const canvasEnvio = document.createElement("canvas");
const ctxEnvio = canvasEnvio.getContext("2d");

let streamCamera = null;

// Recorte 4:3 do centro da câmera. O modelo das letras foi treinado com imagens 4:3 e errava
// bem mais com quadros 16:9 (webcams de notebook). A área da câmera na tela já mostra só o
// centro 4:3; agora o quadro enviado ao servidor é exatamente essa mesma área.
const PROPORCAO_ENVIO = 4 / 3;
let recorte = { x: 0, y: 0, largura: 0, altura: 0 };

function calcularRecorte() {
    const largura = video.videoWidth;
    const altura = video.videoHeight;
    let recLargura = largura;
    let recAltura = altura;
    if (largura / altura > PROPORCAO_ENVIO) {
        recLargura = Math.round(altura * PROPORCAO_ENVIO);   // mais largo que 4:3: corta as laterais
    }
    recorte = { x: Math.round((largura - recLargura) / 2), y: Math.round((altura - recAltura) / 2),
                largura: recLargura, altura: recAltura };
}
let rodando = false;

let letraAlvo = LETRAS[0];
let quadrosCertos = 0;
let jaAcertou = false;

// Sessão de treino no banco (POST /api/sessoes). É uma promessa que vira o id da sessão (ou null).
let sessaoPromessa = null;
let sessaoSinal = null;   // de qual sinal é a sessão aberta

// Sinais com movimento que o back conhece: { nome: { nome, categoria, video } }
let sinaisMovimento = {};

// Modo de coleta para teste (praticar.html?teste=1): a pessoa marca se está fazendo o sinal
// CERTO ou ERRADO e o servidor guarda só os pontos da mão (sem imagem). Nada vale ponto.
const MODO_COLETA = new URLSearchParams(window.location.search).get("teste") === "1";
let rotuloTeste = null;          // null, "certo" ou "errado"
let registrosColeta = 0;
let gravando = false;
let quadrosGravados = [];
let janelaAuto = [];           // [{ tempo, quadro }] dos últimos segundos (reconhecimento automático)
let verificandoAuto = false;
let ultimaVerificacaoAuto = 0;


// tipo: "danger" (erro), "warning" ou "success"
function mostrarMensagem(texto, tipo) {
    const caixa = document.getElementById("mensagem-camera");
    caixa.textContent = texto;
    caixa.className = "alert mt-3 mb-0 alert-" + tipo;
}

function esconderMensagem() {
    document.getElementById("mensagem-camera").className = "alert d-none mt-3 mb-0";
}


async function ligarCamera() {
    esconderMensagem();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        mostrarMensagem(window.isSecureContext
            ? "Seu navegador não liberou a câmera. Tente outro navegador (Chrome, Edge ou Safari atualizados)."
            : "A câmera só funciona em endereço seguro: no computador, abra por http://localhost:5000; no celular, use o endereço https:// que aparece na janela do servidor.", "danger");
        return false;
    }

    // trava o botão antes do await para evitar clique duplo abrir duas câmeras
    btnLigar.disabled = true;

    try {
        try {
            streamCamera = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: "user" },
                audio: false,
            });
        } catch (primeiro) {
            if (primeiro && primeiro.name === "NotAllowedError") throw primeiro;
            // algumas câmeras virtuais (ex.: celular vinculado ao Windows) não aceitam o tamanho pedido:
            // tenta de novo pedindo qualquer câmera
            streamCamera = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
    } catch (erro) {
        btnLigar.disabled = false;
        // mensagem conforme o motivo que o navegador informa
        const motivos = {
            NotAllowedError: "O acesso à câmera foi bloqueado. Clique no cadeado ao lado do endereço, " +
                "deixe \"Câmera\" como Permitir e recarregue a página. No Windows, confira também em " +
                "Configurações > Privacidade > Câmera se os aplicativos podem usar a câmera.",
            NotFoundError: "Nenhuma câmera foi encontrada neste aparelho. Conecte uma webcam (ou confira se a " +
                "câmera do celular vinculado aparece no Windows) e recarregue a página.",
            NotReadableError: "A câmera está sendo usada por outro programa (Teams, Zoom, app Câmera, Vincular ao " +
                "Celular...). Feche o outro programa e tente de novo.",
            OverconstrainedError: "A câmera não aceitou o formato pedido. Tente outra câmera.",
            SecurityError: "O navegador bloqueou a câmera por segurança. Abra o site pelo endereço https:// que " +
                "aparece na janela do servidor.",
        };
        mostrarMensagem((motivos[erro && erro.name] || "Não deu pra acessar a câmera. Confira se você permitiu o acesso no navegador.") +
            " (" + ((erro && erro.name) || "erro") + ")", "danger");
        return false;
    }

    video.srcObject = streamCamera;
    await video.play();

    calcularRecorte();

    // A área da câmera fica na mesma proporção do quadro enviado. No PC é 4:3; no celular em pé
    // a câmera vem "em pé" (ex.: 480x640) e assim a tela mostra exatamente o que o servidor vê.
    document.getElementById("area-camera").style.aspectRatio = recorte.largura + " / " + recorte.altura;

    // O canvas de desenho fica do tamanho do recorte (os pontos voltam do back nessa área)
    canvasDesenho.width = recorte.largura;
    canvasDesenho.height = recorte.altura;

    // O canvas de envio mantém a proporção do recorte
    const escala = MAIOR_LADO_ENVIO / Math.max(recorte.largura, recorte.altura);
    canvasEnvio.width = Math.round(recorte.largura * escala);
    canvasEnvio.height = Math.round(recorte.altura * escala);

    avisoCamera.hidden = true;
    btnDesligar.disabled = false;

    rodando = true;
    if (!eMovimento(letraAlvo)) iniciarSessao(letraAlvo);
    atualizarBlocoMovimento();
    repetirDeteccao();
    return true;
}


function desligarCamera() {
    rodando = false;
    gravando = false;
    limparJanelaAuto();
    esconderContagem();

    if (streamCamera) {
        streamCamera.getTracks().forEach(function (trilha) { trilha.stop(); });
        streamCamera = null;
    }
    video.srcObject = null;

    ctxDesenho.clearRect(0, 0, canvasDesenho.width, canvasDesenho.height);
    avisoCamera.hidden = false;
    btnLigar.disabled = false;
    btnDesligar.disabled = true;

    atualizarInfo([], null);
    document.getElementById("info-corpo").textContent = "—";
    mostrarLetraReconhecida(null, 0);
    quadrosCertos = 0;
    atualizarBarraAcerto();
    atualizarBlocoMovimento();
}


// Pega o quadro atual do vídeo, espelhado (igual o cv2.flip do teste em Python)
function capturarQuadro() {
    ctxEnvio.save();
    ctxEnvio.translate(canvasEnvio.width, 0);
    ctxEnvio.scale(-1, 1);
    ctxEnvio.drawImage(video, recorte.x, recorte.y, recorte.largura, recorte.altura,
                       0, 0, canvasEnvio.width, canvasEnvio.height);
    ctxEnvio.restore();

    return new Promise(function (resolver) {
        canvasEnvio.toBlob(resolver, "image/jpeg", QUALIDADE_JPEG);
    });
}


async function detectarMaos() {
    const tempoCaptura = performance.now();     // ordem real dos quadros (as respostas podem chegar trocadas)
    const quadro = await capturarQuadro();

    const dados = new FormData();
    dados.append("frame", quadro, "frame.jpg");
    // Corpo e rosto só nas saudações: as letras com movimento (H, J, K, X, Z, Ç) usam só a mão
    // (fica mais rápido e funciona sentado e perto da câmera)
    if (eMovimento(letraAlvo)) {
        if (!eLetraComMovimento(letraAlvo)) dados.append("corpo", "1");
    } else {
        if (eNumero(letraAlvo)) dados.append("grupo", "numeros");
    }
    if (rotuloTeste) {
        dados.append("rotuloTeste", rotuloTeste);
        dados.append("alvoTeste", letraAlvo);
        if (!eMovimento(letraAlvo)) contarRegistroColeta();
    } else if (!eMovimento(letraAlvo) && !jaAcertou && sessaoPromessa) {
        const sessaoId = await sessaoPromessa;
        if (sessaoId) dados.append("sessaoId", String(sessaoId));
    }

    const resposta = await fetch(ROTA_DETECTAR, {
        method: "POST",
        body: dados,
        credentials: "same-origin",
    });
    if (resposta.status === 401) {
        irParaLogin();
        throw new Error("Sessão expirada");
    }
    if (resposta.status === 429) {
        // muitos quadros por segundo (limite do servidor): não é erro, só espera um pouco
        const lento = new Error("Muitos quadros");
        lento.lento = true;
        throw lento;
    }
    if (!resposta.ok) {
        throw new Error("O servidor respondeu com erro " + resposta.status);
    }
    const resultado = await resposta.json();
    resultado.tempoCaptura = tempoCaptura;
    return resultado;
}


// Manda um quadro, espera a resposta e só então manda o próximo.
// Assim os pedidos não se acumulam se o computador estiver mais lento.
let ultimoDesenhado = 0;
let respostasRecentes = [];
let geracaoDeteccao = 0;     // se a câmera for desligada e ligada de novo, os laços antigos param

function repetirDeteccao() {
    ultimoDesenhado = 0;
    respostasRecentes = [];
    const geracao = ++geracaoDeteccao;
    for (let i = 0; i < PEDIDOS_SIMULTANEOS; i++) {
        setTimeout(function () { lacoDeDeteccao(geracao); }, i * 60);   // os laços saem um pouco defasados
    }
}

// Quadros por segundo = respostas que chegaram no último segundo
function contarQuadrosPorSegundo() {
    const agora = performance.now();
    respostasRecentes.push(agora);
    while (respostasRecentes.length && agora - respostasRecentes[0] > 1000) respostasRecentes.shift();
    return respostasRecentes.length;
}

// Intervalo mínimo entre os quadros de cada laço: com 2 laços dá no máximo ~22 quadros
// por segundo, abaixo do limite do servidor (30 por segundo).
const INTERVALO_MINIMO_MS = 90;
let falhasSeguidas = 0;

async function lacoDeDeteccao(geracao) {
    while (rodando && geracao === geracaoDeteccao) {
        const inicioQuadro = performance.now();
        try {
            const resultado = await detectarMaos();
            falhasSeguidas = 0;
            if (!rodando) break;

            const fps = contarQuadrosPorSegundo();
            // desenha só se for mais novo que o último desenhado (resposta atrasada não volta no tempo)
            if (resultado.tempoCaptura >= ultimoDesenhado) {
                ultimoDesenhado = resultado.tempoCaptura;
                desenharMaos(resultado.maos);
                if (eMovimento(letraAlvo)) desenharCorpoERosto(resultado);
                atualizarInfo(resultado.maos, fps);
                atualizarInfoCorpo(resultado);
            }

            if (eMovimento(letraAlvo)) {
                if (gravando) guardarQuadro(resultado);
                else acompanharAutomatico(resultado);
            } else {
                mostrarLetraReconhecida(resultado.letra, resultado.certeza);
                tratarProgressoEstatico(resultado);
            }
            esconderMensagem();
        } catch (erro) {
            if (!rodando) break;
            if (erro && erro.lento) {          // limite de quadros: só espera, sem aviso
                await esperar(150);
                continue;
            }
            // Um quadro que falha de vez em quando (rede, quadro perdido) não é motivo de aviso;
            // o aviso só aparece se o servidor ficar sem responder por vários quadros seguidos.
            falhasSeguidas++;
            if (falhasSeguidas >= 4) {
                mostrarMensagem("Sem resposta do servidor. Confira se a janela do servidor (INICIAR_SignEdu.bat) continua aberta.", "warning");
            }
            await esperar(falhasSeguidas >= 4 ? 1000 : 250);
            continue;
        }
        const sobra = INTERVALO_MINIMO_MS - (performance.now() - inicioQuadro);
        if (sobra > 0) await esperar(sobra);
    }
}


function desenharMaos(maos) {
    const largura = canvasDesenho.width;
    const altura = canvasDesenho.height;
    ctxDesenho.clearRect(0, 0, largura, altura);

    maos.forEach(function (mao) {
        // Os pontos vêm de 0 a 1, então multiplica pelo tamanho do canvas
        const pontos = mao.pontos.map(function (p) {
            return { x: p.x * largura, y: p.y * altura };
        });

        // Linhas (esqueleto da mão)
        ctxDesenho.strokeStyle = "#7253FE";
        ctxDesenho.lineWidth = 4;
        LIGACOES_MAO.forEach(function (ligacao) {
            const a = pontos[ligacao[0]];
            const b = pontos[ligacao[1]];
            ctxDesenho.beginPath();
            ctxDesenho.moveTo(a.x, a.y);
            ctxDesenho.lineTo(b.x, b.y);
            ctxDesenho.stroke();
        });

        // Pontos
        ctxDesenho.fillStyle = "#ffffff";
        ctxDesenho.strokeStyle = "#7253FE";
        ctxDesenho.lineWidth = 2;
        pontos.forEach(function (p) {
            ctxDesenho.beginPath();
            ctxDesenho.arc(p.x, p.y, 5, 0, 2 * Math.PI);
            ctxDesenho.fill();
            ctxDesenho.stroke();
        });
    });
}


// Desenha o corpo (ombros, braços) e o rosto por cima da câmera, nos sinais com movimento,
// pra pessoa ver se está bem enquadrada. Os pontos já vêm espelhados, como a mão.
const LIGACOES_CORPO = [[1, 2], [1, 3], [3, 5], [2, 4], [4, 6]];   // índices de PONTOS_CORPO do back
const PONTOS_CORPO_MIN_VISIBILIDADE = 0.5;

function desenharCorpoERosto(resultado) {
    const largura = canvasDesenho.width;
    const altura = canvasDesenho.height;
    const corpo = resultado.corpo;

    ctxDesenho.save();
    if (corpo) {
        ctxDesenho.strokeStyle = "#20c997";
        ctxDesenho.lineWidth = 3;
        LIGACOES_CORPO.forEach(function (lig) {
            const a = corpo[lig[0]];
            const b = corpo[lig[1]];
            if (a[2] < PONTOS_CORPO_MIN_VISIBILIDADE || b[2] < PONTOS_CORPO_MIN_VISIBILIDADE) return;
            ctxDesenho.beginPath();
            ctxDesenho.moveTo(a[0] * largura, a[1] * altura);
            ctxDesenho.lineTo(b[0] * largura, b[1] * altura);
            ctxDesenho.stroke();
        });
        ctxDesenho.fillStyle = "#20c997";
        corpo.forEach(function (p) {
            if (p[2] < PONTOS_CORPO_MIN_VISIBILIDADE) return;
            ctxDesenho.beginPath();
            ctxDesenho.arc(p[0] * largura, p[1] * altura, 5, 0, 2 * Math.PI);
            ctxDesenho.fill();
        });
    }
    if (resultado.rosto) {
        ctxDesenho.fillStyle = "#ffc107";
        resultado.rosto.pontos.forEach(function (p) {
            ctxDesenho.beginPath();
            ctxDesenho.arc(p[0] * largura, p[1] * altura, 4, 0, 2 * Math.PI);
            ctxDesenho.fill();
        });
    }
    ctxDesenho.restore();
}


// "Corpo e rosto: ok / faltando" no painel de detecção (só nos sinais com movimento)
function atualizarInfoCorpo(resultado) {
    const campo = document.getElementById("info-corpo");
    if (!rodando || !eMovimento(letraAlvo)) {
        campo.textContent = "—";
        return;
    }

    const ombros = resultado.corpo && Math.min(resultado.corpo[1][2], resultado.corpo[2][2]) >= PONTOS_CORPO_MIN_VISIBILIDADE;
    const partes = [];
    if (!ombros) partes.push("mostre os ombros");
    if (!resultado.rosto) partes.push("mostre o rosto");
    campo.textContent = partes.length === 0 ? "ok" : partes.join(" e ");
}


function atualizarInfo(maos, fps) {
    document.getElementById("info-maos").textContent = rodando ? maos.length : "—";
    document.getElementById("info-lado").textContent =
        maos.length > 0 ? maos.map(function (m) { return m.lado; }).join(" e ") : "—";
    document.getElementById("info-fps").textContent = fps ? Math.round(fps) : "—";
}


// ---------- Letras ----------

function criarBotoesLetras() {
    const lista = document.getElementById("lista-letras");

    LETRAS.forEach(function (letra) {
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "btn btn-outline-primary btn-sm btn-letra";
        botao.textContent = letra;
        botao.dataset.letra = letra;
        botao.addEventListener("click", function () { escolherLetra(letra); });
        lista.appendChild(botao);
    });
}


// Abre uma sessão de treino do sinal no banco.
function iniciarSessao(sinal) {
    sessaoSinal = sinal;
    sessaoPromessa = chamarApi("POST", "/api/sessoes", { letra: sinal })
        .then(function (resposta) { return resposta.ok ? resposta.dados.sessaoId : null; })
        .catch(function () { return null; });
}

// Devolve a sessão aberta do sinal escolhido (abre uma nova se não tiver, ou se for de outro sinal).
// Usada pelas gravações e vídeos: a sessão só abre quando a pessoa realmente tenta o sinal,
// assim escolher sinais sem tentar não deixa sessões "abandonadas" no banco.
function garantirSessao(sinal) {
    if (!sessaoPromessa || (sessaoSinal || "").toLowerCase() !== sinal.toLowerCase()) {
        iniciarSessao(sinal);
    }
    return sessaoPromessa;
}

function eMovimento(sinal) {
    return Object.prototype.hasOwnProperty.call(sinaisMovimento, sinal);
}

function eLetraComMovimento(sinal) {
    return eMovimento(sinal) && sinal.length === 1;
}

// Números 0 a 9: em LIBRAS são sinais parados (só o formato da mão). O back reconhece
// quadro a quadro, como as letras, mas com o modelo dos números (grupo "numeros").
const numerosParados = {};
function eNumero(sinal) {
    return Object.prototype.hasOwnProperty.call(numerosParados, sinal) && !eMovimento(sinal);
}

// Ordem da tela: Alfabeto, Números e Saudações (é a ordem do botão "próximo")
function todosOsSinais() {
    return Array.from(document.querySelectorAll(".btn-letra")).map(function (botao) {
        return botao.dataset.letra;
    });
}


function escolherLetra(letra) {
    letraAlvo = letra;
    if (MODO_COLETA) mudarRotuloTeste(null);   // trocou de sinal: volta para "desligado"
    quadrosCertos = 0;
    jaAcertou = false;
    sessaoPromessa = null;
    sessaoSinal = null;

    // letras paradas abrem a sessão na hora (se a câmera estiver ligada); os sinais com
    // movimento só abrem quando a pessoa grava ou envia um vídeo
    if (rodando && !eMovimento(letra)) {
        iniciarSessao(letra);
    }

    document.getElementById("letra-alvo").textContent = letra;
    document.getElementById("alvo-curto").textContent = letra;
    document.getElementById("rotulo-alvo").textContent =
        eNumero(letra) ? "Faça o número" : letra.length === 1 ? "Faça a letra" : "Faça o sinal";
    mostrarExemplo(letra);

    document.querySelectorAll(".btn-letra").forEach(function (botao) {
        botao.classList.toggle("ativa", botao.dataset.letra === letra);
    });

    document.getElementById("mensagem-acerto").hidden = true;
    document.getElementById("resultado-video").className = "alert d-none mt-3 mb-0";
    document.querySelector(".barra-acerto").hidden = eMovimento(letra);
    limparJanelaAuto();
    mostrarLetraReconhecida(null, 0);
    atualizarBarraAcerto();
    atualizarBlocoMovimento();
}


// Foto (letras) ou vídeo (sinais com movimento) de exemplo
function mostrarExemplo(sinal) {
    const foto = document.getElementById("foto-exemplo");
    const exemplo = document.getElementById("video-exemplo");

    if (eMovimento(sinal)) {
        foto.hidden = true;
        const endereco = sinaisMovimento[sinal].video;
        if (endereco) {
            const config = lerConfiguracoesSalvas();
            exemplo.src = endereco;
            exemplo.playbackRate = Number((config && config.velocidade) || 1);
            exemplo.hidden = false;
            exemplo.play().catch(function () {});
        } else {
            exemplo.removeAttribute("src");
            exemplo.hidden = true;
        }
    } else {
        exemplo.pause();
        exemplo.removeAttribute("src");
        exemplo.hidden = true;
        foto.hidden = false;
        if (eNumero(sinal)) {
            foto.src = numerosParados[sinal].foto || "";
            foto.alt = "Exemplo do sinal do número " + sinal + " em Libras";
        } else {
            foto.src = "img/letras/" + sinal + ".png";
            foto.alt = "Exemplo do sinal da letra " + sinal + " em Libras";
        }
    }
}


function proximaLetra() {
    const sinais = todosOsSinais();
    const posicao = sinais.indexOf(letraAlvo);
    escolherLetra(sinais[(posicao + 1) % sinais.length]);
}


function mostrarLetraReconhecida(letra, certeza) {
    const caixa = document.getElementById("letra-reconhecida");
    const textoCerteza = document.getElementById("info-certeza");

    if (letra === SEM_SINAL && certeza >= CERTEZA_MINIMA) {
        caixa.textContent = "—";
        caixa.classList.remove("certa", "longo");
        textoCerteza.textContent = "Nenhum sinal reconhecido";
    } else if (letra && certeza >= CERTEZA_MINIMA) {
        caixa.textContent = letra;
        caixa.classList.toggle("longo", letra.length > 2);
        caixa.classList.toggle("certa", letra === letraAlvo);
        textoCerteza.textContent = "Certeza: " + Math.round(certeza * 100) + "%";
    } else {
        caixa.textContent = "—";
        caixa.classList.remove("certa", "longo");
        textoCerteza.innerHTML = "&nbsp;";
    }
}


// Processa a contagem de quadros e o acerto validados diretamente pelo servidor.
function tratarProgressoEstatico(resposta) {
    if (jaAcertou) return;

    if (typeof resposta.quadrosCertos === "number") {
        quadrosCertos = resposta.quadrosCertos;
        atualizarBarraAcerto();
    }

    const res = resposta.resultado;
    if (res && res.acertou) {
        jaAcertou = true;
        sessaoPromessa = null;
        quadrosCertos = QUADROS_PARA_ACERTAR;
        atualizarBarraAcerto();
        document.getElementById("mensagem-acerto").hidden = false;
        celebrarAcerto(letraAlvo, res);
    }
}

function celebrarAcerto(sinal, res) {
    const selo = "+" + res.pontosGanhos + " XP" + (res.xpDobro ? " (2x)" : "");
    // 1º acerto do sinal vale mais; repetir no mesmo dia vale pouco; revisar em outro dia, metade
    const motivo = { novo: "Sinal novo!", revisao: "Revisão", repeticao: "Repetição do dia" }[res.tipoPontos];
    // aviso de acerto (não é conquista: cada acerto dá XP de novo)
    const nome = /^[0-9]$/.test(sinal) ? "Número " + sinal : sinal.length === 1 ? "Letra " + sinal : sinal;
    mostrarAvisoRapido("bi-star-fill", "Acertou o sinal!" + (motivo ? " · " + motivo : ""), nome, selo);

    if (res.subiuDeNivel) {
        avisarSubiuNivel(res.nivel);
    }
    if (Array.isArray(res.novasConquistas)) {
        res.novasConquistas.forEach(function (c) { avisarConquista(c); });
    }
    atualizarProgresso();
}


function atualizarBarraAcerto() {
    const porcentagem = Math.min(100, (quadrosCertos / QUADROS_PARA_ACERTAR) * 100);
    document.getElementById("barra-acerto").style.width = porcentagem + "%";
}


// ---------- Sinais com movimento (câmera e vídeo) ----------

const btnGravar = document.getElementById("btn-gravar");
const btnEnviarVideo = document.getElementById("btn-enviar-video");
const campoVideo = document.getElementById("campo-video");

// Busca no back quais sinais com movimento existem e cria os botões deles
async function carregarSinaisMovimento() {
    try {
        const resposta = await chamarApi("GET", ROTA_SINAIS_MOVIMENTO);
        if (!resposta.ok || !resposta.dados.disponivel || resposta.dados.sinais.length === 0) {
            document.getElementById("nota-movimento").textContent =
                "H, J, K, X, Z e as saudações têm movimento. O modelo de vídeo ainda não foi treinado, " +
                "então por enquanto só dá pra praticar as letras paradas.";
            return;
        }

        // Cada sinal vai para a lista da sua categoria: Alfabeto, Números ou Saudações.
        // As letras com movimento (H, J, K, X, Z, Ç) entram no alfabeto, em ordem.
        const listas = {
            "Alfabeto": document.getElementById("lista-letras"),
            "Números": document.getElementById("lista-numeros"),
            "Saudações": document.getElementById("lista-saudacoes"),
        };
        resposta.dados.sinais.forEach(function (sinal) {
            sinaisMovimento[sinal.nome] = sinal;
            const categoria = listas[sinal.categoria] ? sinal.categoria : "Saudações";

            const botao = document.createElement("button");
            botao.type = "button";
            // bolinha vermelha de "gravar": deixa claro que esse sinal precisa do botão Gravar sinal
            botao.className = "btn btn-outline-primary btn-sm btn-letra movimento largo";
            const icone = document.createElement("i");
            icone.className = "bi bi-record-circle";
            icone.setAttribute("aria-hidden", "true");
            botao.append(icone, sinal.nome);
            botao.dataset.letra = sinal.nome;
            botao.title = "Sinal com movimento";
            botao.setAttribute("aria-label", sinal.nome + " (sinal com movimento)");
            botao.addEventListener("click", function () { escolherLetra(sinal.nome); });
            listas[categoria].appendChild(botao);
            if (categoria !== "Alfabeto") document.getElementById("bloco-" + (categoria === "Números" ? "numeros" : "saudacoes")).hidden = false;
        });
        ordenarBotoes(listas["Alfabeto"]);
        ordenarBotoes(listas["Números"]);
        ordenarBotoes(listas["Saudações"], ORDEM_SAUDACOES);

        document.getElementById("nota-movimento").textContent =
            "Sinais com movimento: faça o sinal inteiro na câmera (pode ser sentado). As letras H, J, K, X, Z e Ç usam só a mão; nas saudações, mostrar o rosto e os ombros ajuda. Os números são parados: é só segurar o formato da mão, como nas letras.";
    } catch (erro) {
        // sem resposta do back: continua só com as letras paradas
    }
}


// Busca no back os números (sinais parados) e cria os botões deles na lista "Números"
async function carregarNumeros() {
    try {
        const resposta = await chamarApi("GET", ROTA_NUMEROS);
        if (!resposta.ok || !resposta.dados.disponivel) return;
        const lista = document.getElementById("lista-numeros");
        resposta.dados.sinais.forEach(function (sinal) {
            if (eMovimento(sinal.nome)) return;          // modelo antigo: continua como movimento
            numerosParados[sinal.nome] = sinal;
            const botao = document.createElement("button");
            botao.type = "button";
            botao.className = "btn btn-outline-primary btn-sm btn-letra";
            botao.textContent = sinal.nome;
            botao.dataset.letra = sinal.nome;
            botao.title = "Sinal parado";
            botao.addEventListener("click", function () { escolherLetra(sinal.nome); });
            lista.appendChild(botao);
        });
        if (lista.children.length) document.getElementById("bloco-numeros").hidden = false;
        ordenarBotoes(lista);
    } catch (erro) {
        // sem resposta do back: continua sem os números
    }
}


// Saudações na ordem em que costumam ser ensinadas (as que não estiverem aqui vão para o fim)
const ORDEM_SAUDACOES = ["Oi", "Tchau", "Bom dia", "Boa tarde", "Boa noite", "Obrigado", "Por favor",
                         "Desculpa", "Tudo bem", "Sim", "Não", "Nome"];

function ordenarBotoes(lista, ordem) {
    const posicao = function (nome) { const i = ordem ? ordem.indexOf(nome) : -1; return i < 0 ? 999 : i; };
    Array.from(lista.children)
        .sort(function (a, b) {
            return posicao(a.dataset.letra) - posicao(b.dataset.letra) ||
                   a.dataset.letra.localeCompare(b.dataset.letra, "pt-BR", { numeric: true });
        })
        .forEach(function (botao) { lista.appendChild(botao); });
}


// Mostra o bloco "Gravar sinal" só nos sinais com movimento
function atualizarBlocoMovimento() {
    const movimento = eMovimento(letraAlvo);
    document.getElementById("bloco-movimento").hidden = !movimento;
    document.getElementById("bloco-enviar-video").hidden = !movimento;   // enviar vídeo: só com movimento
    document.getElementById("rotulo-reconhecida").textContent =
        movimento ? "Sinal reconhecido" : eNumero(letraAlvo) ? "Número reconhecido" : "Letra reconhecida";
    if (!movimento) return;

    [btnGravar].forEach(function (botao) {
        botao.disabled = gravando;
        botao.classList.toggle("chamar", rodando && !gravando);
    });
    document.querySelectorAll(".texto-gravar").forEach(function (texto) {
        texto.textContent = gravando ? "Gravando..." : rodando ? "Gravar sinal" : "Ligar câmera e gravar sinal";
    });
    document.getElementById("instrucao-movimento").textContent = eLetraComMovimento(letraAlvo)
        ? "Pode ser sentado: deixe só a mão bem visível na câmera."
        : "Pode ser sentado. Se der, deixe o rosto e os ombros aparecendo: ajuda a reconhecer.";
}


function mostrarContagem(texto) {
    const caixa = document.getElementById("contagem");
    caixa.textContent = texto;
    caixa.hidden = false;
}

function esconderContagem() {
    document.getElementById("contagem").hidden = true;
    document.getElementById("area-camera").classList.remove("gravando");
}


// tipo: "danger", "warning", "success" ou "info"
function mostrarResultadoVideo(texto, tipo) {
    const caixa = document.getElementById("resultado-video");
    caixa.textContent = texto;
    caixa.className = "alert mt-3 mb-0 alert-" + tipo;
    caixa.scrollIntoView({ block: "nearest", behavior: "smooth" });   // no celular a tela rola até o resultado
}


// Guarda as mãos de um quadro da gravação (null se não apareceu mão).
// Vão as duas mãos (se aparecerem): o back acompanha as duas e usa a que mais se mexe,
// porque a outra mão pode estar parada na frente do corpo.
function guardarQuadro(resultado) {
    if (quadrosGravados.length >= MAXIMO_QUADROS_GRAVADOS) return;
    inserirEmOrdem(quadrosGravados, { tempo: resultado.tempoCaptura, quadro: montarQuadro(resultado) });
}

// Guarda {tempo, quadro} na ordem em que o quadro foi capturado
function inserirEmOrdem(lista, item) {
    let i = lista.length;
    while (i > 0 && lista[i - 1].tempo > item.tempo) i--;
    lista.splice(i, 0, item);
}

function montarQuadro(resultado) {
    const arredondar = function (v) { return Math.round(v * 10000) / 10000; };
    const maos = (resultado.maos || []).slice(0, 2).map(function (mao) {
        return {
            lado: mao.lado,
            pontos: mao.pontos.map(function (p) { return { x: arredondar(p.x), y: arredondar(p.y), z: arredondar(p.z) }; })
        };
    });

    return (maos.length ? {
        maos: maos,
        proporcao: resultado.proporcao,
        corpo: resultado.corpo || null,     // nariz, ombros, cotovelos, pulsos (MediaPipe Pose)
        rosto: resultado.rosto || null      // pontos do rosto + expressões (MediaPipe Face)
    } : null);
}


// ---------- Reconhecimento automático dos sinais com movimento ----------
// Guarda o quadro e, a cada INTERVALO_AUTO_MS, manda os últimos JANELA_AUTO_MS pro back
// no modo "verificar" (não salva tentativa). Se o sinal certo aparecer com certeza suficiente,
// manda a mesma janela de novo como tentativa de verdade (aí conta o acerto e os pontos).
function limparJanelaAuto() {
    confirmacoesAuto = 0;
    janelaAuto = [];
    ultimaVerificacaoAuto = 0;
}

function acompanharAutomatico(resultado) {
    if (jaAcertou || !eMovimento(letraAlvo)) return;
    const agora = performance.now();
    inserirEmOrdem(janelaAuto, { tempo: resultado.tempoCaptura || agora, quadro: montarQuadro(resultado) });
    while (janelaAuto.length && agora - janelaAuto[0].tempo > JANELA_AUTO_MS) janelaAuto.shift();

    const duracao = janelaAuto.length ? agora - janelaAuto[0].tempo : 0;
    const comMao = janelaAuto.filter(function (item) { return item.quadro; }).length;
    if (verificandoAuto || duracao < MINIMO_JANELA_AUTO_MS || comMao < 6) return;
    if (agora - ultimaVerificacaoAuto < INTERVALO_AUTO_MS) return;

    ultimaVerificacaoAuto = agora;
    verificarAutomatico(letraAlvo, janelaAuto.map(function (item) { return item.quadro; }));
}

async function verificarAutomatico(alvo, quadros) {
    verificandoAuto = true;
    try {
        const pedido = { quadros: quadros, verificar: true, alvo: alvo };
        if (rotuloTeste) { pedido.rotuloTeste = rotuloTeste; contarRegistroColeta(); }
        const resposta = await chamarApi("POST", ROTA_MOVIMENTO, pedido);
        if (!resposta.ok || letraAlvo !== alvo || gravando || jaAcertou || !rodando) return;

        const dados = resposta.dados;
        const minima = dados.certezaMinima || CERTEZA_MINIMA_MOVIMENTO;
        mostrarSinalAutomatico(dados, alvo, minima);

        const certo = !dados.semMovimento && dados.sinal.toLowerCase() === alvo.toLowerCase() &&
                      dados.certeza >= minima;
        confirmacoesAuto = certo ? confirmacoesAuto + 1 : 0;
        if (certo && confirmacoesAuto < CONFIRMACOES_AUTO) {
            document.getElementById("info-certeza").textContent = "Isso! Continue fazendo o sinal…";
        }
        if (!rotuloTeste && !MODO_COLETA && certo && confirmacoesAuto >= CONFIRMACOES_AUTO) {
            limparJanelaAuto();
            await enviarGravacao(alvo, quadros);       // agora vale como tentativa (com sessão)
        }
    } catch (erro) {
        // sem resposta: tenta de novo na próxima janela
    } finally {
        verificandoAuto = false;
    }
}

// Mostra no cartão "Sinal reconhecido" o que o modelo está vendo agora
// Igual ao nome da classe extra do back (detector_maos.SEM_SINAL)
const SEM_SINAL = "Nenhum sinal";

function mostrarSinalAutomatico(dados, alvo, minima) {
    const sinal = dados.sinal, certeza = dados.certeza;
    const caixa = document.getElementById("letra-reconhecida");
    const textoCerteza = document.getElementById("info-certeza");
    if (dados.semMovimento || sinal === SEM_SINAL) {
        // mão parada (filtro de movimento) ou o modelo disse "não é nenhum destes"
        caixa.textContent = "—";
        caixa.classList.remove("certa", "longo");
        textoCerteza.textContent = dados.semMovimento
            ? "Mão parada: faça o movimento do sinal"
            : "Nenhum sinal reconhecido";
        return;
    }
    const certo = sinal.toLowerCase() === alvo.toLowerCase();
    caixa.textContent = sinal;
    caixa.classList.toggle("longo", sinal.length > 2);   // "Boa noite" cabe na coluna estreita
    caixa.classList.toggle("certa", certo && certeza >= minima);
    textoCerteza.textContent = "Certeza: " + Math.round(certeza * 100) + "% (precisa de " +
        Math.round(minima * 100) + "% no sinal certo)";
}


// Contagem regressiva -> grava alguns segundos -> manda pro back
async function gravarSinal() {
    const alvo = letraAlvo;
    if (gravando || !eMovimento(alvo)) return;
    if (!rodando) {                       // câmera desligada: liga e já começa a gravar
        const ligou = await ligarCamera();
        if (!ligou || !rodando || letraAlvo !== alvo) return;
    }

    gravando = true;     // trava o botão (a captura de quadros só começa depois da contagem)
    quadrosGravados = [];
    atualizarBlocoMovimento();
    document.getElementById("resultado-video").className = "alert d-none mt-3 mb-0";
    document.getElementById("mensagem-acerto").hidden = true;

    const cancelado = function () { return !rodando || letraAlvo !== alvo; };
    const terminar = function () {
        gravando = false;
        esconderContagem();
        atualizarBlocoMovimento();
    };

    // durante a contagem a pessoa se posiciona: os quadros dessa fase são descartados
    for (let n = SEGUNDOS_CONTAGEM; n > 0; n--) {
        mostrarContagem(String(n));
        await esperar(1000);
        if (cancelado()) { terminar(); return; }
    }

    mostrarContagem("Faça o sinal!");
    document.getElementById("area-camera").classList.add("gravando");
    quadrosGravados = [];
    await esperar(SEGUNDOS_GRAVACAO * 1000);

    const quadros = quadrosGravados.map(function (item) { return item.quadro; });
    quadrosGravados = [];
    terminar();
    if (cancelado()) return;

    await enviarGravacao(alvo, quadros);
}


async function enviarGravacao(alvo, quadros) {
    if (quadros.filter(Boolean).length < 6) {
        mostrarResultadoVideo("Não vi sua mão por tempo suficiente. Deixe a mão bem visível durante o sinal e tente de novo.", "warning");
        return;
    }
    // sem corpo/rosto o back recusa; o aviso do back explica o que ajustar

    mostrarResultadoVideo("Analisando o movimento...", "info");
    if (rotuloTeste) {
        // modo de coleta: só guarda e mostra o que reconheceu (não vale ponto)
        try {
            contarRegistroColeta();
            const resposta = await chamarApi("POST", ROTA_MOVIMENTO,
                { quadros: quadros, alvo: alvo, verificar: true, rotuloTeste: rotuloTeste });
            if (resposta.ok) mostrarSinalAutomatico(resposta.dados, alvo,
                resposta.dados.certezaMinima || CERTEZA_MINIMA_MOVIMENTO);
            mostrarResultadoVideo("Gravação guardada para o teste (" + rotuloTeste + ").", "info");
        } catch (erro) {
            mostrarResultadoVideo("Sem resposta do servidor.", "danger");
        }
        return;
    }
    try {
        const sessaoId = await garantirSessao(alvo);
        const corpo = { quadros: quadros, alvo: alvo };
        if (sessaoId) corpo.sessaoId = sessaoId;

        const resposta = await chamarApi("POST", ROTA_MOVIMENTO, corpo);
        tratarRespostaDoSinal(resposta, alvo);
    } catch (erro) {
        mostrarResultadoVideo("Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    }
}


// Resposta de /api/maos/movimento ou /api/maos/video
function tratarRespostaDoSinal(resposta, alvo) {
    if (!resposta.ok) {
        // sessão encerrada (409) ou inexistente: a próxima tentativa abre outra
        if (resposta.status === 409 || resposta.status === 404) sessaoPromessa = null;
        mostrarResultadoVideo((resposta.dados && resposta.dados.erro) || "Não foi possível reconhecer o sinal.", "warning");
        return;
    }

    const dados = resposta.dados;
    const porcentagem = Math.round(dados.certeza * 100);
    const resultado = dados.resultado;

    // sem sessão no banco (ex.: o back não abriu), compara aqui mesmo (sem pontos)
    const acertou = resultado
        ? resultado.acertou
        : dados.sinal.toLowerCase() === alvo.toLowerCase() &&
          dados.certeza >= (dados.certezaMinima || CERTEZA_MINIMA_MOVIMENTO);

    if (!acertou) {
        const minima = Math.round((dados.certezaMinima || CERTEZA_MINIMA_MOVIMENTO) * 100);
        if (dados.sinal.toLowerCase() === alvo.toLowerCase() && porcentagem >= minima) {
            mostrarResultadoVideo("Reconheci \"" + dados.sinal + "\", mas não consegui registrar o acerto. Tente de novo.", "warning");
            sessaoPromessa = null;
            return;
        }
        if (dados.semMovimento) {
            mostrarResultadoVideo("Não vi movimento. \"" + alvo + "\" é um sinal com movimento: faça o " +
                                  "sinal inteiro, como no vídeo de exemplo, e tente de novo.", "warning");
            return;
        }
        if (dados.sinal === SEM_SINAL) {
            mostrarResultadoVideo("Não reconheci nenhum sinal. Confira o vídeo de exemplo e tente de novo.", "warning");
            return;
        }
        mostrarResultadoVideo("Reconheci \"" + dados.sinal + "\" (" + porcentagem + "% de certeza). " +
                              "Pra valer, o sinal reconhecido precisa ser \"" + alvo + "\" com pelo menos " +
                              minima + "%. Tente de novo.", "warning");
        return;
    }

    jaAcertou = true;
    sessaoPromessa = null;   // a sessão foi concluída: a próxima tentativa abre outra
    mostrarResultadoVideo("Isso mesmo! Reconheci \"" + dados.sinal + "\" (" + porcentagem + "% de certeza).", "success");
    document.getElementById("mensagem-acerto").hidden = false;

    if (resultado) {
        celebrarAcerto(alvo, resultado);
    }
}


// Vídeo enviado pela pessoa (letra parada ou sinal com movimento)
async function enviarVideo(arquivo) {
    const alvo = letraAlvo;
    const nome = arquivo.name.toLowerCase();

    if (!EXTENSOES_VIDEO.some(function (ext) { return nome.endsWith(ext); })) {
        mostrarResultadoVideo("Escolha um vídeo MP4, MOV, AVI, WEBM ou MKV.", "danger");
        return;
    }
    if (arquivo.size > TAMANHO_MAXIMO_VIDEO) {
        mostrarResultadoVideo("O vídeo precisa ter até 50 MB.", "danger");
        return;
    }

    btnEnviarVideo.disabled = true;
    document.getElementById("mensagem-acerto").hidden = true;
    mostrarResultadoVideo("Analisando o vídeo...", "info");

    try {
        const sessaoId = await garantirSessao(alvo);

        const dados = new FormData();
        dados.append("video", arquivo, arquivo.name);
        dados.append("tipo", eMovimento(alvo) ? "movimento" : "letra");
        if (eMovimento(alvo)) dados.append("alvo", alvo);
        if (eNumero(alvo)) dados.append("grupo", "numeros");
        if (sessaoId) dados.append("sessaoId", sessaoId);

        // sem Content-Type: o navegador monta sozinho (multipart)
        const bruto = await fetch(ROTA_VIDEO, { method: "POST", body: dados, credentials: "same-origin" });
        let corpo = null;
        try { corpo = await bruto.json(); } catch (erro) {}

        if (bruto.status === 401) { irParaLogin(); return; }
        tratarRespostaDoSinal({ ok: bruto.ok, status: bruto.status, dados: corpo }, alvo);
    } catch (erro) {
        mostrarResultadoVideo("Sem resposta do servidor. Confira se o app.py está rodando.", "danger");
    } finally {
        btnEnviarVideo.disabled = false;
        campoVideo.value = "";
    }
}


function esperar(ms) {
    return new Promise(function (resolver) { setTimeout(resolver, ms); });
}


btnGravar.addEventListener("click", gravarSinal);
btnEnviarVideo.addEventListener("click", function () { campoVideo.click(); });
campoVideo.addEventListener("change", function () {
    if (campoVideo.files[0]) enviarVideo(campoVideo.files[0]);
});

btnLigar.addEventListener("click", ligarCamera);
btnDesligar.addEventListener("click", desligarCamera);
document.getElementById("btn-proximo-sinal").addEventListener("click", proximaLetra);

criarBotoesLetras();
escolherLetra(LETRAS[0]);
// Primeiro os sinais com movimento (pra saber quais são), depois os números parados
carregarSinaisMovimento().then(carregarNumeros);

// Aplica a velocidade salva nos vídeos de exemplo quando as configurações sincronizarem
document.addEventListener("signedu:config", function (evento) {
    const exemplo = document.getElementById("video-exemplo");
    if (exemplo && evento.detail && evento.detail.velocidade) {
        exemplo.playbackRate = Number(evento.detail.velocidade) || 1;
    }
});

// Conta o tempo ativo na tela de prática (enquanto a aba estiver visível) para avisar a meta diária
(function iniciarContadorMetaDiaria() {
    const hoje = new Date().toISOString().slice(0, 10);
    const chaveSegundos = "signedu-estudo-seg-" + hoje;
    const chaveAvisou = "signedu-meta-avisada-" + hoje;

    setInterval(function () {
        if (document.hidden || !rodando) return;
        const segundos = Number(localStorage.getItem(chaveSegundos) || 0) + 5;
        localStorage.setItem(chaveSegundos, String(segundos));

        const config = lerConfiguracoesSalvas();
        const metaMinutos = Number((config && config.meta) || 10);
        if (segundos >= metaMinutos * 60 && !localStorage.getItem(chaveAvisou)) {
            localStorage.setItem(chaveAvisou, "1");
            avisarMetaCumprida(metaMinutos);
        }
    }, 5000);
})();

// Desliga a câmera se a pessoa sair da página
window.addEventListener("beforeunload", desligarCamera);


// ---------- Modo de coleta (praticar.html?teste=1) ----------
function contarRegistroColeta() {
    registrosColeta++;
    const contador = document.getElementById("coleta-contador");
    if (contador) contador.textContent = String(registrosColeta);
}

function mudarRotuloTeste(rotulo) {
    rotuloTeste = rotulo;
    limparJanelaAuto();      // a janela de movimento não mistura certo com errado
    document.querySelectorAll("[data-rotulo-teste]").forEach(function (botao) {
        const ativo = (botao.dataset.rotuloTeste || null) === (rotulo || "");
        botao.classList.toggle("active", ativo);
    });
    const estado = document.getElementById("coleta-estado");
    if (estado) {
        estado.textContent = rotulo === "certo" ? "Gravando: sinal CERTO"
            : rotulo === "errado" ? "Gravando: sinal ERRADO" : "Desligado";
        estado.className = "fw-bold " + (rotulo === "certo" ? "text-success"
            : rotulo === "errado" ? "text-danger" : "text-muted");
    }
}

(function montarPainelColeta() {
    if (!MODO_COLETA) return;
    const painel = document.createElement("div");
    painel.className = "alert alert-warning mt-3 mb-0 text-start small";
    painel.innerHTML =
        '<div class="fw-bold mb-1">Modo de coleta para teste</div>' +
        '<div class="mb-2">Guarda só os pontos da mão (sem imagem). Nada vale ponto. ' +
        'Ao trocar de sinal, volta para "Desligado".</div>' +
        '<div class="d-flex flex-wrap gap-1 mb-2">' +
        '<button type="button" class="btn btn-sm btn-outline-danger" data-rotulo-teste="errado">Fazendo ERRADO</button>' +
        '<button type="button" class="btn btn-sm btn-outline-success" data-rotulo-teste="certo">Fazendo CERTO</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary active" data-rotulo-teste="">Desligar</button>' +
        '</div>' +
        '<div>Estado: <span id="coleta-estado" class="fw-bold text-muted">Desligado</span> · ' +
        'registros: <strong id="coleta-contador">0</strong></div>';
    const destino = document.querySelector(".bloco-deteccao") || document.body;
    destino.after(painel);
    painel.querySelectorAll("[data-rotulo-teste]").forEach(function (botao) {
        botao.addEventListener("click", function () {
            mudarRotuloTeste(botao.dataset.rotuloTeste || null);
        });
    });
})();
