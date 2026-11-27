"""
Servidor do SignEdu.

- Mostra as páginas do front (pasta "frontend", ao lado da pasta "backend").
- Recebe os quadros da câmera em /api/maos/detectar (autenticado), roda o MediaPipe
  + Random Forest e valida os acertos diretamente no servidor (sem confiar no cliente).
- Sinais com MOVIMENTO (Z, H, J, K, X, saudações...): reconhece uma sequência de
  quadros (/api/maos/movimento) ou um vídeo enviado (/api/maos/video).
- Guarda usuários, progresso, moedas, loja, missões, conquistas, configurações,
  sessões, resultados e pontuação no banco MySQL "signedu".
"""

import json
import os
import re
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, request, session
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

PASTA_BACKEND = Path(__file__).resolve().parent
PASTA_FRONT = PASTA_BACKEND.parent / "frontend"
PASTA_AVATARES = PASTA_FRONT / "uploads" / "avatars"
CAMINHO_MODELO = PASTA_BACKEND / "hand_landmarker.task"
CAMINHO_CLASSIFICADOR = PASTA_BACKEND / "modelo_letras.joblib"
CAMINHO_MOVIMENTO = PASTA_BACKEND / "modelo_movimento.joblib"
CAMINHO_NUMEROS = PASTA_BACKEND / "modelo_numeros.joblib"
CAMINHO_GRUPOS = PASTA_BACKEND / "modelo_movimento_grupos.joblib"
CAMINHO_CORPO = PASTA_BACKEND / "pose_landmarker.task"
CAMINHO_ROSTO = PASTA_BACKEND / "face_landmarker.task"

load_dotenv(PASTA_BACKEND / ".env")

import banco  # noqa: E402
from banco import (  # noqa: E402
    Exercicio, SessaoTreinamento, Sinal, Usuario, db,
)
from detector_maos import (  # noqa: E402
    DetectorDeMaos, EXPRESSOES, EXTENSOES_VIDEO, PONTOS_CORPO, PONTOS_ROSTO,
)

QUANTIDADE_PONTOS_CORPO = len(PONTOS_CORPO)
QUANTIDADE_PONTOS_ROSTO = len(PONTOS_ROSTO)
QUANTIDADE_EXPRESSOES = len(EXPRESSOES)
QUADROS_PARA_ACERTAR = 8
TAMANHO_MAXIMO_FOTO = 2 * 1024 * 1024
EXTENSOES_FOTO = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

app = Flask(__name__, static_folder=str(PASTA_FRONT), static_url_path="")

config_banco = banco.config_do_banco()

chave_secreta = os.getenv("SECRET_KEY")
if not chave_secreta:
    chave_secreta = secrets.token_hex(32)
    print("Aviso: SECRET_KEY não definida no backend/.env. Usando uma chave temporária.")

app.config.update(
    SECRET_KEY=chave_secreta,
    # SIGNEDU_DATABASE_URL só é usada nos testes automáticos (tests/), com um banco SQLite
    # temporário; no uso normal o app conecta no MySQL configurado no backend/.env.
    SQLALCHEMY_DATABASE_URI=os.getenv("SIGNEDU_DATABASE_URL") or URL.create(
        "mysql+pymysql",
        username=config_banco["user"],
        password=config_banco["password"],
        host=config_banco["host"],
        port=config_banco["port"],
        database=config_banco["database"],
        query={"charset": "utf8mb4"},
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 280},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,
)

db.init_app(app)

detector = DetectorDeMaos(CAMINHO_MODELO, CAMINHO_CLASSIFICADOR, CAMINHO_MOVIMENTO,
                          CAMINHO_CORPO, CAMINHO_ROSTO, CAMINHO_NUMEROS, CAMINHO_GRUPOS)

if not detector.tem_classificador:
    print("Aviso: modelo_letras.joblib não encontrado. O app vai mostrar a mão, mas não a letra.")
if not detector.tem_corpo:
    print("Aviso: pose_landmarker.task e/ou face_landmarker.task não encontrados em backend/.")
elif not detector.tem_classificador_movimento:
    print("Aviso: modelo_movimento.joblib não encontrado. Sinais com movimento ficam desligados.")


def preparar_banco():
    """Conecta no MySQL, cria/migra o que faltar e garante os sinais iniciais."""
    try:
        banco.garantir_banco(config_banco)
        with app.app_context():
            db.create_all()
            banco.migrar_banco()
            banco.semear_alfabeto()
            banco.semear_sinais_movimento(detector.sinais_movimento)
            banco.semear_numeros(detector.numeros)
    except Exception as erro_banco:
        print("\nNão consegui usar o banco de dados MySQL.\n"
              f"  Servidor: {config_banco['host']}:{config_banco['port']}  "
              f"Usuário: {config_banco['user']}  Banco: {config_banco['database']}\n"
              f"  Erro: {erro_banco}\n"
              "Confira se o MySQL está ligado e se o backend/.env está certo.")
        sys.exit(1)


# ================== RATE LIMITING E CONTADOR DE QUADROS ==================

_trava_taxa = threading.Lock()
_historico_taxa = defaultdict(deque)


def limitar_taxa(chave, maximo, janela_segundos):
    """Retorna True se ultrapassou o limite de requisições na janela."""
    agora_ts = time.monotonic()
    with _trava_taxa:
        fila = _historico_taxa[chave]
        while fila and agora_ts - fila[0] > janela_segundos:
            fila.popleft()
        if len(fila) >= maximo:
            return True
        fila.append(agora_ts)
        return False


# Contagem no servidor de quadros corretos consecutivos por (usuario_id, sessao_id)
_trava_quadros = threading.Lock()

# ---- Modo de coleta para teste (praticar.html?teste=1) ----
# A pessoa marca se está fazendo o sinal CERTO ou ERRADO e o servidor guarda SÓ os pontos
# da mão/corpo (nenhuma imagem) em dados/coleta_testes.jsonl. Serve para calibrar e testar
# o reconhecimento com a câmera de verdade. Nesse modo nada vale ponto.
ARQUIVO_COLETA = PASTA_BACKEND / "dados" / "coleta_testes.jsonl"
_trava_coleta = threading.Lock()


def rotulo_de_coleta(valor):
    return valor if valor in ("certo", "errado") else None


def guardar_coleta(registro):
    registro["usuario"] = g.usuario.id
    registro["momento"] = round(time.time(), 3)
    ARQUIVO_COLETA.parent.mkdir(exist_ok=True)
    with _trava_coleta, open(ARQUIVO_COLETA, "a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
_quadros_certos = {}


def _limpar_contadores_usuario(usuario_id):
    with _trava_quadros:
        for chave in [k for k in _quadros_certos if k[0] == usuario_id]:
            _quadros_certos.pop(chave, None)


# ================== AJUDANTES ==================

EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def erro(mensagem, status):
    return jsonify({"erro": mensagem}), status


def dados_json():
    corpo = request.get_json(silent=True)
    return corpo if isinstance(corpo, dict) else {}


def ip_cliente():
    # Pelo túnel da internet (Cloudflare Tunnel rodando neste mesmo computador) todo mundo chega
    # como 127.0.0.1; o túnel informa o IP real no cabeçalho CF-Connecting-IP. Só confia nesse
    # cabeçalho quando o pedido veio deste computador, pra ninguém de fora conseguir falsificar.
    endereco = request.remote_addr or "desconhecido"
    if endereco in ("127.0.0.1", "::1") and request.headers.get("CF-Connecting-IP"):
        return request.headers["CF-Connecting-IP"][:64]
    return endereco


def usuario_logado():
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return None
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        session.clear()
    return usuario


def exige_login(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        usuario = usuario_logado()
        if usuario is None:
            return erro("Você precisa entrar na sua conta.", 401)
        g.usuario = usuario
        return funcao(*args, **kwargs)
    return protegida


ROTAS_MULTIPART = ("/api/maos/detectar", "/api/maos/video", "/api/usuarios/me/foto")


@app.before_request
def exigir_json_nas_alteracoes():
    if (request.path.startswith("/api/")
            and request.method in ("POST", "PUT", "DELETE")
            and request.path not in ROTAS_MULTIPART
            and not request.is_json):
        return erro("Envie os dados em JSON (Content-Type: application/json).", 415)


@app.errorhandler(413)
def arquivo_grande(excecao):
    return erro("O arquivo é grande demais (máximo de 50 MB).", 413)


@app.errorhandler(SQLAlchemyError)
def erro_do_banco(excecao):
    db.session.rollback()
    app.logger.exception("Erro no banco de dados")
    return erro("Não foi possível acessar o banco de dados agora. Tente de novo.", 503)


def dados_do_usuario(usuario):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "dataCriacao": usuario.data_cadastro.isoformat() if usuario.data_cadastro else None,
        "fotoUrl": usuario.foto_url,
    }


def entrar(usuario):
    session.clear()
    session["usuario_id"] = usuario.id
    session.permanent = True


def numero_ou_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _apagar_arquivo_avatar(foto_url):
    if not foto_url or not foto_url.startswith("uploads/avatars/"):
        return
    caminho = (PASTA_FRONT / foto_url).resolve()
    try:
        caminho.relative_to(PASTA_AVATARES.resolve())
        caminho.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


# ================== PÁGINAS ==================

@app.get("/")
def inicio():
    return redirect("/login.html")


# ================== MÃOS (MediaPipe + Random Forest) ==================

@app.post("/api/maos/detectar")
@exige_login
def detectar_maos():
    """
    Recebe um quadro da câmera (campo 'frame'). Se vier 'sessaoId' para uma letra parada,
    o servidor conta os quadros corretos consecutivos e registra o acerto ao atingir
    QUADROS_PARA_ACERTAR (impedindo fraude de XP pelo navegador).
    """
    if limitar_taxa(f"detectar:{g.usuario.id}", 30, 1):
        return erro("Muitas requisições de detecção. Aguarde um instante.", 429)

    arquivo = request.files.get("frame")
    if arquivo is None:
        return erro("Envie a imagem no campo 'frame'.", 400)

    com_corpo = request.form.get("corpo") == "1" and detector.tem_corpo
    grupo = grupo_do_pedido()

    try:
        resultado = detector.detectar(arquivo.read(), com_corpo=com_corpo, grupo=grupo)
    except ValueError as erro_imagem:
        return erro(str(erro_imagem), 400)

    rotulo = rotulo_de_coleta(request.form.get("rotuloTeste"))
    if rotulo and resultado.get("maos"):
        guardar_coleta({"tipo": "parado", "rotulo": rotulo, "grupo": grupo,
                        "alvo": (request.form.get("alvoTeste") or "")[:50],
                        "maos": resultado["maos"], "proporcao": resultado.get("proporcao"),
                        "letra": resultado.get("letra"), "certeza": resultado.get("certeza"),
                        "corpo": resultado.get("corpo"), "rosto": resultado.get("rosto")})
        return jsonify(resultado)      # modo de coleta: não conta acerto

    # Validação de acerto no servidor para letras paradas
    sessao_id = numero_ou_none(request.form.get("sessaoId"))
    if sessao_id is not None and not com_corpo:
        sessao = db.session.get(SessaoTreinamento, sessao_id)
        if sessao and sessao.usuario_id == g.usuario.id and sessao.status == "em_andamento":
            exercicio = db.session.get(Exercicio, sessao.exercicio_id)
            sinal = db.session.get(Sinal, exercicio.sinal_id) if exercicio else None
            if sinal:
                letra_detectada = resultado.get("letra") or ""
                certeza = float(resultado.get("certeza") or 0.0)
                chave = (g.usuario.id, sessao.id)
                acertou_quadro = (
                    letra_detectada.lower() == sinal.nome.lower()
                    and certeza >= banco.CERTEZA_MINIMA
                )
                with _trava_quadros:
                    atual = _quadros_certos.get(chave, 0)
                    atual = (atual + 1) if acertou_quadro else max(0, atual - 2)
                    if atual >= QUADROS_PARA_ACERTAR:
                        _quadros_certos.pop(chave, None)
                    else:
                        _quadros_certos[chave] = atual

                resultado["quadrosCertos"] = min(atual, QUADROS_PARA_ACERTAR)
                resultado["quadrosNecessarios"] = QUADROS_PARA_ACERTAR

                if atual >= QUADROS_PARA_ACERTAR:
                    try:
                        resultado["resultado"] = banco.registrar_tentativa(
                            g.usuario, sessao.id, letra_detectada, certeza
                        )
                    except banco.TentativaInvalida:
                        pass

    return jsonify(resultado)


def grupo_do_pedido():
    """Sinal parado: "numeros" usa o modelo dos números (0 a 9); o resto usa o das letras."""
    if request.form.get("grupo") == "numeros" and detector.tem_classificador_numeros:
        return "numeros"
    return "letras"


def foto_do_numero(nome):
    # Foto de exemplo do número (frontend/img/numeros/<n>.jpg): a mão do especialista em
    # LIBRAS, recortada dos vídeos gravados com autorização (termo assinado).
    arquivo = PASTA_FRONT / "img" / "numeros" / f"{nome}.jpg"
    return f"img/numeros/{nome}.jpg" if arquivo.is_file() else None


@app.get("/api/sinais/numeros")
@exige_login
def listar_numeros():
    """Números 0 a 9: sinais parados, reconhecidos quadro a quadro como as letras."""
    sinais = [{"nome": nome, "categoria": "Números", "foto": foto_do_numero(nome)}
              for nome in detector.numeros]
    return jsonify({"disponivel": detector.tem_classificador_numeros, "sinais": sinais})


# ================== SINAIS COM MOVIMENTO (câmera e vídeo) ==================

def video_de_exemplo(nome):
    # Vídeo de exemplo do sinal (frontend/videos/<nome>.mp4), gravado pelo especialista em
    # LIBRAS com autorização (termo assinado). O nome pode ter espaço e acento ("Bom dia").
    arquivo = PASTA_FRONT / "videos" / f"{nome}.mp4"
    return "videos/" + quote(f"{nome}.mp4") if arquivo.is_file() else None


@app.get("/api/sinais/movimento")
@exige_login
def listar_sinais_movimento():
    sinais = []
    for nome in detector.sinais_movimento:
        sinal = banco.buscar_sinal(nome)
        sinais.append({
            "nome": nome,
            "categoria": sinal.categoria if sinal else banco.categoria_do_sinal(nome),
            "video": video_de_exemplo(nome),
        })
    return jsonify({"disponivel": detector.tem_classificador_movimento, "sinais": sinais})


def numero_valido(valor):
    return not isinstance(valor, bool) and isinstance(valor, (int, float)) and abs(valor) <= 100


def mao_valida(mao):
    if not isinstance(mao, dict) or mao.get("lado") not in ("Esquerda", "Direita"):
        return False
    pontos = mao.get("pontos")
    if not isinstance(pontos, list) or len(pontos) != 21:
        return False
    for ponto in pontos:
        if not isinstance(ponto, dict):
            return False
        for eixo in ("x", "y", "z"):
            if not numero_valido(ponto.get(eixo)):
                return False
    return True


def quadro_valido(quadro):
    # Formato novo: "maos" com 1 ou 2 mãos (o back escolhe a que mais se mexe).
    # Formato antigo: "lado" e "pontos" de uma mão só (continua aceito).
    if not isinstance(quadro, dict):
        return False
    if "maos" in quadro:
        maos = quadro.get("maos")
        if not isinstance(maos, list) or not 1 <= len(maos) <= 2 or not all(mao_valida(m) for m in maos):
            return False
    elif not mao_valida(quadro):
        return False

    proporcao = quadro.get("proporcao")
    if isinstance(proporcao, bool) or not isinstance(proporcao, (int, float)) or not 0.2 <= proporcao <= 5:
        return False

    corpo = quadro.get("corpo")
    if corpo is not None:
        if not isinstance(corpo, list) or len(corpo) != QUANTIDADE_PONTOS_CORPO:
            return False
        if not all(isinstance(p, list) and len(p) == 3 and all(numero_valido(v) for v in p) for p in corpo):
            return False

    rosto = quadro.get("rosto")
    if rosto is not None:
        if not isinstance(rosto, dict):
            return False
        pontos_rosto, expressao = rosto.get("pontos"), rosto.get("expressao")
        if not isinstance(pontos_rosto, list) or len(pontos_rosto) != QUANTIDADE_PONTOS_ROSTO:
            return False
        if not all(isinstance(p, list) and len(p) == 2 and all(numero_valido(v) for v in p) for p in pontos_rosto):
            return False
        if not isinstance(expressao, list) or len(expressao) != QUANTIDADE_EXPRESSOES:
            return False
        if not all(numero_valido(v) for v in expressao):
            return False
    return True


def dados_da_tentativa(sessao_id, sinal, certeza, certeza_minima=None):
    if sessao_id is None:
        return None
    return banco.registrar_tentativa(g.usuario, sessao_id, sinal, certeza, certeza_minima)


@app.post("/api/maos/movimento")
@exige_login
def reconhecer_movimento():
    if not detector.tem_classificador_movimento:
        return erro("Os sinais com movimento ainda não foram treinados.", 503)

    dados = dados_json()
    quadros = dados.get("quadros")
    if not isinstance(quadros, list) or not 1 <= len(quadros) <= 300:
        return erro("Envie de 1 a 300 quadros.", 422)
    if not all(q is None or quadro_valido(q) for q in quadros):
        return erro("Quadros inválidos.", 422)

    sessao_id = dados.get("sessaoId")
    if sessao_id is not None and (isinstance(sessao_id, bool) or not isinstance(sessao_id, int)):
        return erro("Sessão inválida.", 422)

    # "verificar": reconhecimento automático da câmera (sem apertar Gravar). O site manda os
    # últimos segundos a cada instante; aqui só responde o que reconheceu, sem salvar tentativa
    # (senão cada janela sem sinal viraria um erro no histórico). Quando o sinal certo aparece,
    # o site manda a mesma janela de novo, com a sessão, e aí a tentativa é registrada.
    verificar = dados.get("verificar") is True
    if verificar and limitar_taxa(f"verificar:{g.usuario.id}", 4, 1):
        return erro("Muitas verificações. Aguarde um instante.", 429)

    # "alvo": o sinal escolhido na tela (o modelo escolhe só entre os sinais do mesmo grupo)
    alvo = dados.get("alvo")
    if alvo is not None and (not isinstance(alvo, str) or len(alvo) > 50):
        return erro("Sinal inválido.", 422)

    try:
        reconhecido = detector.prever_movimento(quadros, alvo)
        rotulo = rotulo_de_coleta(dados.get("rotuloTeste"))
        if rotulo:
            guardar_coleta({"tipo": "movimento", "rotulo": rotulo, "alvo": alvo,
                            "quadros": quadros, **reconhecido})
            verificar = True           # modo de coleta: não registra tentativa
        resposta = {"tipo": "movimento", **reconhecido,
                    "certezaMinima": banco.CERTEZA_MINIMA_MOVIMENTO,
                    "quadrosComMao": sum(1 for q in quadros if q), "quadros": len(quadros)}
        resposta["resultado"] = None if verificar else dados_da_tentativa(
            sessao_id, reconhecido["sinal"], reconhecido["certeza"], banco.CERTEZA_MINIMA_MOVIMENTO)
    except ValueError as problema:
        return erro(str(problema), 422)
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resposta)


@app.post("/api/maos/video")
@exige_login
def reconhecer_video():
    arquivo = request.files.get("video")
    if arquivo is None:
        return erro("Envie o vídeo no campo 'video'.", 400)

    extensao = Path(arquivo.filename or "").suffix.lower()
    if extensao not in EXTENSOES_VIDEO:
        return erro("Formato não aceito. Use MP4, MOV, AVI, WEBM ou MKV.", 415)

    tipo = request.form.get("tipo", "movimento")
    if tipo not in ("movimento", "letra"):
        return erro("O tipo precisa ser 'movimento' ou 'letra'.", 422)
    if tipo == "movimento" and not detector.tem_classificador_movimento:
        return erro("Os sinais com movimento ainda não foram treinados.", 503)
    if tipo == "letra" and not detector.tem_classificador:
        return erro("O modelo das letras não está disponível.", 503)

    sessao_texto = request.form.get("sessaoId")
    sessao_id = numero_ou_none(sessao_texto)
    if sessao_texto not in (None, "") and sessao_id is None:
        return erro("Sessão inválida.", 422)

    try:
        # Para letra parada não precisa dos modelos de corpo/rosto (bem mais rápido)
        quadros = detector.ler_video_bytes(arquivo.read(), extensao, com_corpo=(tipo == "movimento"))
        com_mao = sum(1 for q in quadros if q)

        if tipo == "movimento":
            reconhecido = detector.prever_movimento(quadros, (request.form.get("alvo") or "")[:50] or None)
            sinal, certeza = reconhecido["sinal"], reconhecido["certeza"]
        else:
            reconhecido = detector.prever_letra_em_quadros(quadros, grupo_do_pedido())
            if reconhecido is None:
                return erro("Não encontrei nenhuma mão no vídeo.", 422)
            sinal, certeza = reconhecido["letra"], reconhecido["certeza"]
            reconhecido = {"sinal": sinal, "certeza": certeza}

        resposta = {"tipo": tipo, **reconhecido, "quadrosComMao": com_mao, "quadros": len(quadros)}
        resposta["resultado"] = dados_da_tentativa(
            sessao_id, sinal, certeza,
            banco.CERTEZA_MINIMA_MOVIMENTO if tipo == "movimento" else banco.CERTEZA_MINIMA)
    except ValueError as problema:
        return erro(str(problema), 422)
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resposta)


# ================== LOGIN E CADASTRO ==================

@app.post("/api/auth/cadastro")
def cadastrar():
    if limitar_taxa(f"cadastro:{ip_cliente()}", 5, 60):
        return erro("Muitas tentativas de cadastro. Aguarde 1 minuto.", 429)

    dados = dados_json()
    nome = dados.get("nome")
    email = dados.get("email")
    senha = dados.get("senha")

    if not all(isinstance(v, str) for v in (nome, email, senha)):
        return erro("Preencha nome, e-mail e senha.", 422)

    nome = nome.strip()
    email = email.strip().lower()

    if not nome or len(nome) > 100:
        return erro("O nome precisa ter de 1 a 100 caracteres.", 422)
    if len(email) > 120 or not EMAIL_VALIDO.match(email):
        return erro("Digite um e-mail válido.", 422)
    if not 8 <= len(senha) <= 128:
        return erro("A senha precisa ter de 8 a 128 caracteres.", 422)

    # LGPD: a conta só é criada com o aceite dos Termos de Uso e da Política de Privacidade
    if dados.get("aceiteTermos") is not True:
        return erro("O cadastro e o acesso à plataforma só podem acontecer mediante a aceitação "
                    "dos Termos de Uso e da Política de Privacidade.", 422)

    if Usuario.query.filter_by(email=email).first():
        return erro("Esse e-mail já está cadastrado.", 409)

    usuario = Usuario(nome=nome, email=email, senha=banco.criar_hash(senha),
                      termos_aceitos_em=banco.agora())
    db.session.add(usuario)
    try:
        db.session.flush()
        banco.obter_progresso(usuario.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return erro("Esse e-mail já está cadastrado.", 409)

    entrar(usuario)
    return jsonify({"usuario": dados_do_usuario(usuario)}), 201


@app.post("/api/auth/login")
def login():
    if limitar_taxa(f"login:{ip_cliente()}", 10, 60):
        return erro("Muitas tentativas de login. Aguarde 1 minuto.", 429)

    dados = dados_json()
    email = dados.get("email")
    senha = dados.get("senha")

    if not isinstance(email, str) or not isinstance(senha, str) or len(senha) > 128:
        return erro("Informe e-mail e senha.", 422)

    usuario = Usuario.query.filter_by(email=email.strip().lower()).first()
    if not banco.verificar_senha(usuario, senha):
        return erro("E-mail ou senha incorretos.", 401)

    entrar(usuario)
    return jsonify({"usuario": dados_do_usuario(usuario)})


@app.post("/api/auth/logout")
def logout():
    uid = session.get("usuario_id")
    if uid is not None:
        _limpar_contadores_usuario(uid)
    session.clear()
    return jsonify({"ok": True})


# ================== CONTA E FOTO ==================

@app.get("/api/usuarios/me")
@exige_login
def ver_conta():
    return jsonify(dados_do_usuario(g.usuario))


@app.put("/api/usuarios/me")
@exige_login
def editar_conta():
    nome = dados_json().get("nome")
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 100:
        return erro("O nome precisa ter de 1 a 100 caracteres.", 422)

    g.usuario.nome = nome.strip()
    db.session.commit()
    return jsonify(dados_do_usuario(g.usuario))


@app.post("/api/usuarios/me/foto")
@exige_login
def salvar_foto():
    arquivo = request.files.get("foto")
    if arquivo is None:
        return erro("Envie a foto no campo 'foto'.", 400)

    extensao = EXTENSOES_FOTO.get(arquivo.mimetype or "")
    if not extensao:
        return erro("Escolha uma imagem JPG, PNG ou WEBP.", 415)

    conteudo = arquivo.read()
    if not conteudo or len(conteudo) > TAMANHO_MAXIMO_FOTO:
        return erro("A imagem precisa ter até 2 MB.", 413)

    # Confirma que os bytes são mesmo uma imagem válida
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        return erro("O arquivo enviado não é uma imagem válida.", 422)

    PASTA_AVATARES.mkdir(parents=True, exist_ok=True)
    _apagar_arquivo_avatar(g.usuario.foto_url)

    nome_arquivo = f"user_{g.usuario.id}_{secrets.token_hex(4)}{extensao}"
    (PASTA_AVATARES / nome_arquivo).write_bytes(conteudo)

    g.usuario.foto_url = f"uploads/avatars/{nome_arquivo}"
    db.session.commit()
    return jsonify({"fotoUrl": g.usuario.foto_url})


@app.delete("/api/usuarios/me/foto")
@exige_login
def remover_foto():
    _apagar_arquivo_avatar(g.usuario.foto_url)
    g.usuario.foto_url = None
    db.session.commit()
    return jsonify({"ok": True, "fotoUrl": None})


@app.put("/api/usuarios/me/senha")
@exige_login
def trocar_senha():
    dados = dados_json()
    senha_atual = dados.get("senhaAtual")
    nova_senha = dados.get("novaSenha")

    if not isinstance(senha_atual, str) or not isinstance(nova_senha, str):
        return erro("Informe a senha atual e a nova senha.", 422)
    if not 8 <= len(nova_senha) <= 128:
        return erro("A nova senha precisa ter de 8 a 128 caracteres.", 422)
    if not banco.verificar_senha(g.usuario, senha_atual):
        return erro("A senha atual está incorreta.", 403)
    if nova_senha == senha_atual:
        return erro("A nova senha precisa ser diferente da atual.", 422)

    g.usuario.senha = banco.criar_hash(nova_senha)
    db.session.commit()
    return jsonify({"ok": True})


@app.delete("/api/usuarios/me")
@exige_login
def excluir_conta():
    dados = dados_json()
    senha_atual = dados.get("senhaAtual")
    if not isinstance(senha_atual, str) or not banco.verificar_senha(g.usuario, senha_atual):
        return erro("Informe sua senha atual correta para excluir a conta.", 403)

    _apagar_arquivo_avatar(g.usuario.foto_url)
    _limpar_contadores_usuario(g.usuario.id)
    banco.excluir_usuario_completo(g.usuario, dados.get("motivo"), dados.get("comentario"))
    session.clear()
    return jsonify({"ok": True})


# ================== CONFIGURAÇÕES ==================

@app.get("/api/usuarios/configuracoes")
@exige_login
def ver_configuracoes():
    return jsonify(banco.obter_configuracoes(g.usuario.id))


@app.put("/api/usuarios/configuracoes")
@exige_login
def atualizar_configuracoes():
    try:
        salvas = banco.salvar_configuracoes(g.usuario.id, dados_json())
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(salvas)


# ================== PROGRESSO, SESSÕES, RANKING ==================

@app.get("/api/usuarios/progresso")
@exige_login
def ver_progresso():
    return jsonify(banco.resumo_do_progresso(g.usuario))


@app.post("/api/sessoes")
@exige_login
def iniciar_sessao():
    if limitar_taxa(f"sessoes:{g.usuario.id}", 30, 60):
        return erro("Muitas sessões abertas em pouco tempo. Aguarde um instante.", 429)

    letra = dados_json().get("letra")
    if not isinstance(letra, str):
        return erro("Informe a letra.", 422)

    try:
        sessao, exercicio = banco.abrir_sessao(g.usuario, letra)
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)

    _limpar_contadores_usuario(g.usuario.id)
    return jsonify({"sessaoId": sessao.id, "exercicioId": exercicio.id,
                    "pontos": banco.pontos_do_exercicio(exercicio)}), 201


@app.get("/api/ranking/semana")
@exige_login
def ver_ranking():
    liga, posicao, pessoas = banco.ranking_da_liga(g.usuario)
    return jsonify({"liga": liga, "posicao": posicao, "pessoas": pessoas})


# ================== MISSÕES, CONQUISTAS E LOJA ==================

@app.get("/api/missoes/semana")
@exige_login
def ver_missoes():
    return jsonify({"missoes": banco.listar_missoes_semana(g.usuario)})


@app.post("/api/missoes/<int:missao_id>/resgatar")
@exige_login
def resgatar_missao_rota(missao_id):
    try:
        resultado = banco.resgatar_missao(g.usuario, missao_id)
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resultado)


@app.get("/api/usuarios/conquistas")
@exige_login
def ver_conquistas():
    return jsonify({"conquistas": banco.listar_conquistas(g.usuario)})


@app.get("/api/loja")
@exige_login
def ver_loja():
    return jsonify(banco.dados_da_loja(g.usuario))


@app.post("/api/loja/comprar")
@exige_login
def comprar_loja():
    dados = dados_json()
    try:
        resultado = banco.comprar_na_loja(g.usuario, dados.get("tipo"), dados.get("id"))
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resultado)


@app.post("/api/loja/usar")
@exige_login
def usar_item_loja():
    dados = dados_json()
    try:
        resultado = banco.usar_item(g.usuario, dados.get("id"))
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resultado)


@app.put("/api/usuarios/me/moldura")
@exige_login
def trocar_moldura_rota():
    moldura = dados_json().get("moldura")
    if moldura is not None and not isinstance(moldura, str):
        return erro("Moldura inválida.", 422)
    try:
        resultado = banco.trocar_moldura(g.usuario, moldura)
    except banco.TentativaInvalida as problema:
        return erro(problema.mensagem, problema.status)
    return jsonify(resultado)


if __name__ == "__main__":
    preparar_banco()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    # Outros aparelhos na mesma rede (celular, outro PC): o navegador só libera a câmera em
    # endereço seguro (https). Com PORTA_REDE (ex.: 5443), além do endereço normal deste
    # computador (http://localhost:5000, sem aviso), o servidor abre um segundo endereço https
    # pra rede, com um certificado criado na hora (o navegador avisa que ele não é verificado:
    # é só tocar em "Avançado" e continuar). Os dois endereços usam o mesmo app e o mesmo banco.
    # Também dá pra usar só https: HTTPS=1 com HOST=0.0.0.0.
    ssl = "adhoc" if os.getenv("HTTPS", "0") == "1" else None
    porta_rede = os.getenv("PORTA_REDE")

    def ip_desta_maquina():
        """IP deste computador na rede local. Com VPN ligada o caminho "padrão" é o da VPN
        (ex.: 10.2.0.2), então dá preferência aos endereços de rede de casa (192.168.x.x)."""
        import socket
        ips = []
        try:
            ips = [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            pass
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as teste:
                teste.connect(("8.8.8.8", 80))
                ips.append(teste.getsockname()[0])
        except OSError:
            pass
        casa = [ip for ip in ips if ip.startswith("192.168.")]
        outros = [ip for ip in ips if not ip.startswith("127.")]
        return (casa or outros or ["IP-DESTE-COMPUTADOR"])[0]

    if porta_rede:
        import threading
        from werkzeug.serving import make_server
        # Se o endereço da rede não abrir (porta ocupada, falta da biblioteca cryptography...),
        # a plataforma continua funcionando neste computador.
        try:
            servidor_rede = make_server("0.0.0.0", int(porta_rede), app, threaded=True, ssl_context="adhoc")
            threading.Thread(target=servidor_rede.serve_forever, daemon=True).start()
            print("\n  Neste computador:  http://localhost:" + str(port) +
                  "\n  Celular ou outro computador (mesma rede): https://" + ip_desta_maquina() + ":" +
                  str(porta_rede) + "\n", flush=True)
        except Exception as erro_rede:
            print("\n  Neste computador:  http://localhost:" + str(port) +
                  "\n  (Não consegui abrir o endereço para celular/outro computador: " + str(erro_rede) + ")\n",
                  flush=True)
    elif host == "0.0.0.0":
        protocolo = "https" if ssl else "http"
        print("\n  No computador: " + protocolo + "://localhost:" + str(port) +
              "\n  No celular (mesmo Wi-Fi): " + protocolo + "://" + ip_desta_maquina() + ":" + str(port) + "\n",
              flush=True)
    # use_reloader=False pra não carregar o modelo do MediaPipe duas vezes
    app.run(host=host, port=port, debug=debug, use_reloader=False, ssl_context=ssl)
