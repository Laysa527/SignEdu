"""
Banco de dados do SignEdu (MySQL + SQLAlchemy).

Tabelas principais: usuarios, progresso, sinais, exercicios, sessoes_treinamento,
resultados e pontuacoes.
Tabelas extras (gamificação, loja, conquistas, missões e configurações):
usuario_itens, usuario_molduras, usuario_configuracoes, missoes_resgatadas,
usuario_conquistas e exclusoes_conta.

Nada do que já está no banco é apagado: o db.create_all() cria tabelas novas e
migrar_banco() adiciona colunas/índices que faltarem com segurança.
"""

import os
import re
from datetime import date, datetime, timedelta

import pymysql
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, text
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def agora():
    """Data e hora local (o banco guarda datas sem fuso, e o ranking semanal usa a hora local)."""
    return datetime.now()


# ================== CONEXÃO ==================

def config_do_banco():
    """Lê a conexão das variáveis de ambiente (backend/.env). Veja o .env.example."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "signedu"),
    }


def garantir_banco(config):
    """Cria o banco (schema) se ainda não existir. Se já existir, não faz nada."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", config["database"]):
        raise ValueError("DB_NAME só pode ter letras, números e _.")

    conexao = pymysql.connect(
        host=config["host"], port=config["port"],
        user=config["user"], password=config["password"],
    )
    try:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config['database']}` "
                "CHARACTER SET utf8mb4"
            )
        conexao.commit()
    finally:
        conexao.close()


# ================== TABELAS ==================

class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    data_cadastro = db.Column(db.DateTime, default=agora)
    foto_url = db.Column(db.String(255), nullable=True)
    termos_aceitos_em = db.Column(db.DateTime, nullable=True)   # quando aceitou os Termos de Uso (LGPD)

    progresso = db.relationship("Progresso", backref="usuario", uselist=False,
                                cascade="all, delete-orphan")


class Progresso(db.Model):
    __tablename__ = "progresso"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    nivel = db.Column(db.Integer, default=1)
    experiencia = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=agora, onupdate=agora)
    moedas = db.Column(db.Integer, default=0, nullable=False)
    moldura_ativa = db.Column(db.String(50), nullable=True)
    xp_dobro_ate = db.Column(db.DateTime, nullable=True)


class Sinal(db.Model):
    __tablename__ = "sinais"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    imagem = db.Column(db.String(255))
    video = db.Column(db.String(255))
    categoria = db.Column(db.String(50))


class Exercicio(db.Model):
    __tablename__ = "exercicios"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    nivel = db.Column(db.Integer)
    tipo = db.Column(db.Enum("reconhecimento", "multipla_escolha"), default="reconhecimento")
    sinal_id = db.Column(db.Integer, db.ForeignKey("sinais.id"), nullable=False)


class SessaoTreinamento(db.Model):
    __tablename__ = "sessoes_treinamento"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    exercicio_id = db.Column(db.Integer, db.ForeignKey("exercicios.id"), nullable=False)
    status = db.Column(db.Enum("em_andamento", "concluida", "abandonada"), default="em_andamento")
    inicio = db.Column(db.DateTime, default=agora)
    fim = db.Column(db.DateTime, nullable=True)


class Resultado(db.Model):
    __tablename__ = "resultados"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    exercicio_id = db.Column(db.Integer, db.ForeignKey("exercicios.id"), nullable=False)
    sessao_id = db.Column(db.Integer, db.ForeignKey("sessoes_treinamento.id"), nullable=False)
    sinal_identificado = db.Column(db.String(50))
    confianca = db.Column(db.Float)
    acertou = db.Column(db.Boolean, default=False)
    pontos_obtidos = db.Column(db.Integer, default=0)
    data_hora = db.Column(db.DateTime, default=agora)


class Pontuacao(db.Model):
    __tablename__ = "pontuacoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    resultado_id = db.Column(db.Integer, db.ForeignKey("resultados.id"), nullable=True)
    origem = db.Column(db.String(50))
    pontos = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, default=agora, index=True)


class UsuarioItem(db.Model):
    __tablename__ = "usuario_itens"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    item_id = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (db.UniqueConstraint("usuario_id", "item_id", name="uq_usuario_item"),)


class UsuarioMoldura(db.Model):
    __tablename__ = "usuario_molduras"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    moldura_id = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint("usuario_id", "moldura_id", name="uq_usuario_moldura"),)


class UsuarioConfiguracao(db.Model):
    __tablename__ = "usuario_configuracoes"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    meta = db.Column(db.String(10), default="10", nullable=False)
    aviso_meta = db.Column(db.Boolean, default=True, nullable=False)
    velocidade = db.Column(db.String(10), default="1", nullable=False)
    lembrete = db.Column(db.Boolean, default=False, nullable=False)
    horario = db.Column(db.String(10), default="19:00", nullable=False)
    aviso_conquista = db.Column(db.Boolean, default=True, nullable=False)
    fonte = db.Column(db.String(10), default="100", nullable=False)


class MissaoResgatada(db.Model):
    __tablename__ = "missoes_resgatadas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    semana_inicio = db.Column(db.Date, nullable=False)
    missao_id = db.Column(db.Integer, nullable=False)
    data_resgate = db.Column(db.DateTime, default=agora)
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "semana_inicio", "missao_id", name="uq_missao_semana"),
    )


class UsuarioConquista(db.Model):
    __tablename__ = "usuario_conquistas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    conquista_id = db.Column(db.Integer, nullable=False)
    data_conquista = db.Column(db.DateTime, default=agora)
    como_conseguiu = db.Column(db.String(255))
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "conquista_id", name="uq_usuario_conquista"),
    )


class ExclusaoConta(db.Model):
    __tablename__ = "exclusoes_conta"
    id = db.Column(db.Integer, primary_key=True)
    motivo = db.Column(db.String(50), nullable=False)
    comentario = db.Column(db.Text)
    data_exclusao = db.Column(db.DateTime, default=agora)


# ================== MIGRAÇÃO SEGURA ==================

def migrar_banco():
    """Adiciona colunas e índices novos em tabelas que já existiam, sem apagar dados."""
    schema = db.session.execute(text("SELECT DATABASE()")).scalar()

    def tem_coluna(tabela, coluna):
        return db.session.execute(
            text("SELECT COUNT(*) FROM information_schema.COLUMNS "
                 "WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t AND COLUMN_NAME=:c"),
            {"s": schema, "t": tabela, "c": coluna},
        ).scalar() > 0

    def tem_indice(tabela, indice):
        return db.session.execute(
            text("SELECT COUNT(*) FROM information_schema.STATISTICS "
                 "WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t AND INDEX_NAME=:i"),
            {"s": schema, "t": tabela, "i": indice},
        ).scalar() > 0

    alteracoes = [
        ("usuarios", "foto_url", "ALTER TABLE usuarios ADD COLUMN foto_url VARCHAR(255) NULL"),
        ("usuarios", "termos_aceitos_em", "ALTER TABLE usuarios ADD COLUMN termos_aceitos_em DATETIME NULL"),
        ("progresso", "moedas", "ALTER TABLE progresso ADD COLUMN moedas INT NOT NULL DEFAULT 0"),
        ("progresso", "moldura_ativa", "ALTER TABLE progresso ADD COLUMN moldura_ativa VARCHAR(50) NULL"),
        ("progresso", "xp_dobro_ate", "ALTER TABLE progresso ADD COLUMN xp_dobro_ate DATETIME NULL"),
    ]
    for tabela, coluna, sql in alteracoes:
        if not tem_coluna(tabela, coluna):
            db.session.execute(text(sql))

    # Permite pontuações vindas de missões/conquistas (sem resultado_id)
    nullable_res = db.session.execute(
        text("SELECT IS_NULLABLE FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA=:s AND TABLE_NAME='pontuacoes' AND COLUMN_NAME='resultado_id'"),
        {"s": schema},
    ).scalar()
    if nullable_res == "NO":
        db.session.execute(text("ALTER TABLE pontuacoes MODIFY COLUMN resultado_id INT NULL"))

    if not tem_indice("pontuacoes", "idx_pontuacoes_data_hora"):
        db.session.execute(text("CREATE INDEX idx_pontuacoes_data_hora ON pontuacoes (data_hora)"))

    # Nome do sinal com comparação exata (com acento e cedilha). Com a comparação padrão do
    # MySQL, "Ç" e "C" contavam como o mesmo nome e o índice único impedia criar o Ç.
    colacao = db.session.execute(
        text("SELECT COLLATION_NAME FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA=:s AND TABLE_NAME='sinais' AND COLUMN_NAME='nome'"),
        {"s": schema},
    ).scalar()
    if colacao and colacao != "utf8mb4_bin":
        db.session.execute(text(
            "ALTER TABLE sinais MODIFY COLUMN nome VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"))

    if not tem_indice("sinais", "uq_sinais_nome"):
        duplicados = db.session.execute(
            text("SELECT COUNT(*) FROM (SELECT nome FROM sinais GROUP BY nome HAVING COUNT(*) > 1) d")
        ).scalar()
        if duplicados == 0:
            db.session.execute(text("CREATE UNIQUE INDEX uq_sinais_nome ON sinais (nome)"))

    db.session.commit()


# ================== DADOS INICIAIS ==================

LETRAS = ["A", "B", "C", "D", "E", "F", "G", "I", "L", "M", "N",
          "O", "P", "Q", "R", "S", "T", "U", "V", "W", "Y"]


def categoria_do_sinal(nome):
    """Alfabeto (letras, inclusive o Ç), Números (0 a 9) ou Saudações (o resto).
    Antes todo sinal de um caractere ia para "Alfabeto", e os números entravam como letras
    (e contavam para a conquista "Alfabeto Completo")."""
    nome = (nome or "").strip()
    if nome.isdigit():
        return "Números"
    if len(nome) == 1 and nome.isalpha():
        return "Alfabeto"
    return "Saudações"


def _garantir_sinal_e_exercicio(nome, categoria, nivel):
    """Cria o sinal e o exercício de reconhecimento dele, se ainda não existirem."""
    sinal = buscar_sinal(nome)
    if sinal is not None and sinal.categoria != categoria:
        sinal.categoria = categoria        # corrige sinais salvos com a categoria antiga
    if sinal is None:
        sinal = Sinal(nome=nome, descricao=f"Sinal {nome} em Libras", categoria=categoria,
                      imagem=f"img/letras/{nome}.png" if categoria == "Alfabeto" and nivel == 1 else None)
        db.session.add(sinal)
        db.session.flush()

    if Exercicio.query.filter_by(sinal_id=sinal.id).first() is None:
        db.session.add(Exercicio(titulo=f"Praticar {nome}", nivel=nivel,
                                 descricao=f"Faça o sinal {nome} na câmera.",
                                 tipo="reconhecimento", sinal_id=sinal.id))


def semear_alfabeto():
    for letra in LETRAS:
        _garantir_sinal_e_exercicio(letra, "Alfabeto", 1)
    db.session.commit()


def semear_numeros(nomes):
    """Números 0 a 9 como sinais parados (nível 1, como as letras paradas)."""
    for nome in nomes:
        _garantir_sinal_e_exercicio(nome, "Números", 1)
        sinal = buscar_sinal(nome)
        if sinal is not None and not sinal.imagem:
            sinal.imagem = f"img/numeros/{nome}.jpg"
    db.session.commit()


def semear_sinais_movimento(nomes):
    for nome in nomes:
        _garantir_sinal_e_exercicio(nome, categoria_do_sinal(nome), 2)
    db.session.commit()


def buscar_sinal(nome):
    nome = (nome or "").strip()
    if not nome:
        return None
    # O MySQL compara sem acento ("Ç" = "C", "Não" = "Nao"): a consulta traz os parecidos e
    # aqui fica só o nome exato (antes, o Ç abria a sessão da letra C e nunca dava acerto).
    candidatos = Sinal.query.filter(or_(func.lower(Sinal.nome) == nome.lower(), Sinal.nome == nome)).all()
    exatos = [s for s in candidatos if s.nome.lower() == nome.lower()]
    return exatos[0] if exatos else None


# ================== SENHAS ==================

_HASH_FALSO = generate_password_hash("senha-falsa-para-igualar-o-tempo")


def criar_hash(senha):
    return generate_password_hash(senha)


def verificar_senha(usuario, senha):
    """Confere o hash da senha (tempo constante mesmo quando o e-mail não existe)."""
    if usuario is None or not usuario.senha:
        check_password_hash(_HASH_FALSO, senha)
        return False
    try:
        return check_password_hash(usuario.senha, senha)
    except ValueError:
        return False


# ================== NÍVEIS, LIGAS E LOJA ==================

# XP total necessário pra chegar em cada nível (igual à lista NIVEIS do frontend/js/geral.js)
XP_POR_NIVEL = [0, 100, 250, 450, 700, 1000, 1400, 1900]
MOEDAS_POR_NIVEL = 50
META_DESAFIO_DIA = 5

PONTOS_POR_NIVEL_EXERCICIO = {1: 10, 2: 20}
PONTOS_NIVEL_DIFICIL = 35

# Pontos de um acerto, conforme a pessoa já acertou esse sinal antes (pra repetir o mesmo sinal
# várias vezes não valer o mesmo que aprender um sinal novo):
BONUS_SINAL_NOVO = 5          # 1º acerto do sinal: pontos cheios + bônus
PONTOS_REPETICAO_NO_DIA = 2   # já acertou esse sinal hoje: vale pouco
#                               já acertou em outro dia (revisão): metade dos pontos
CERTEZA_MINIMA = 0.5
# Sinais com movimento: o modelo divide os "votos" entre 18 sinais e a certeza do sinal certo
# costuma ficar abaixo de 50% mesmo quando ele acerta. No teste com os vídeos do especialista
# (treino com uma luz, teste com a outra), o modelo acertou o sinal em 80% dos vídeos, mas só
# 17% passavam de 50% de certeza; com 30% passam 57%. Continua exigindo que o sinal certo seja
# o mais provável.
CERTEZA_MINIMA_MOVIMENTO = 0.3

ITENS_LOJA = [
    {
        "id": "protetor", "icone": "bi-shield-check", "nome": "Protetor de sequência",
        "preco": 100, "maximo": 2, "usavel": False,
        "descricao": "Se você ficar 1 dia sem estudar, sua sequência não zera.",
    },
    {
        "id": "xpDobro", "icone": "bi-lightning-charge", "nome": "XP em dobro",
        "preco": 80, "maximo": 3, "usavel": True,
        "descricao": "Ganhe o dobro de XP nos próximos 15 minutos de prática.",
    },
    {
        "id": "segundaChance", "icone": "bi-arrow-repeat", "nome": "Segunda chance",
        "preco": 50, "maximo": 3, "usavel": False,
        "descricao": "Item de reserva para desafios futuros.",
    },
]

MOLDURAS_LOJA = [
    {"id": "lilas", "nome": "Lilás", "preco": 60, "descricao": "Um contorno lilás simples e bonito."},
    {"id": "fogo", "nome": "Fogo", "preco": 120, "descricao": "Pra quem está com a sequência pegando fogo."},
    {"id": "ouro", "nome": "Ouro", "preco": 150, "descricao": "Brilho dourado de quem chegou longe."},
    {"id": "arcoiris", "nome": "Arco-íris", "preco": 200, "descricao": "Todas as cores ao redor da sua foto."},
]

_ITENS_POR_ID = {i["id"]: i for i in ITENS_LOJA}
_MOLDURAS_POR_ID = {m["id"]: m for m in MOLDURAS_LOJA}


def pontos_do_exercicio(exercicio):
    return PONTOS_POR_NIVEL_EXERCICIO.get(exercicio.nivel or 1, PONTOS_NIVEL_DIFICIL)


def pontos_do_acerto(usuario_id, exercicio, sinal):
    """Devolve (pontos, tipo): tipo é "novo" (1º acerto do sinal), "repeticao" (já acertou hoje)
    ou "revisao" (já acertou em outro dia)."""
    base = pontos_do_exercicio(exercicio)
    ultimo = (
        db.session.query(func.max(Resultado.data_hora))
        .join(Exercicio, Exercicio.id == Resultado.exercicio_id)
        .filter(Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True),
                Exercicio.sinal_id == sinal.id)
        .scalar()
    )
    if ultimo is None:
        return base + BONUS_SINAL_NOVO, "novo"
    if ultimo >= agora().replace(hour=0, minute=0, second=0, microsecond=0):
        return PONTOS_REPETICAO_NO_DIA, "repeticao"
    return max(1, base // 2), "revisao"


def nivel_por_xp(xp):
    xp = xp or 0
    nivel = 1
    for numero, necessario in enumerate(XP_POR_NIVEL, start=1):
        if xp >= necessario:
            nivel = numero
    return nivel


def liga_do_nivel(nivel):
    nivel = nivel or 1
    if nivel <= 2:
        return "bronze"
    if nivel <= 4:
        return "prata"
    if nivel <= 6:
        return "ouro"
    return "diamante"


def _niveis_da_liga(liga):
    return {
        "bronze": (1, 2),
        "prata": (3, 4),
        "ouro": (5, 6),
        "diamante": (7, 99),
    }[liga]


def obter_progresso(usuario_id, bloquear=False):
    consulta = Progresso.query.filter_by(usuario_id=usuario_id)
    if bloquear:
        consulta = consulta.with_for_update()
    progresso = consulta.first()

    if progresso is None:
        progresso = Progresso(usuario_id=usuario_id, nivel=1, experiencia=0, moedas=0)
        db.session.add(progresso)
        db.session.flush()
    return progresso


def _inventario_do_usuario(usuario_id):
    itens = {r.item_id: r.quantidade for r in UsuarioItem.query.filter_by(usuario_id=usuario_id).all()}
    molduras = [r.moldura_id for r in UsuarioMoldura.query.filter_by(usuario_id=usuario_id).all()]
    return itens, molduras


# ================== RANKING E ESTATÍSTICAS ==================

def inicio_da_semana():
    """Segunda-feira 00:00 (a semana termina no domingo 23:59)."""
    hoje = agora().replace(hour=0, minute=0, second=0, microsecond=0)
    return hoje - timedelta(days=hoje.weekday())


def ranking_da_liga(usuario):
    """Pessoas da mesma liga do usuário, ordenadas pelo XP ganho nesta semana."""
    progresso = obter_progresso(usuario.id)
    nivel_do_usuario = nivel_por_xp(progresso.experiencia or 0)
    liga = liga_do_nivel(nivel_do_usuario)
    min_n, max_n = _niveis_da_liga(liga)

    nivel_col = func.coalesce(Progresso.nivel, 1)
    linhas = (
        db.session.query(Usuario.id, Usuario.nome)
        .outerjoin(Progresso, Progresso.usuario_id == Usuario.id)
        .filter(nivel_col >= min_n, nivel_col <= max_n)
        .all()
    )
    ids = [i for i, _ in linhas]
    if usuario.id not in ids:
        linhas.append((usuario.id, usuario.nome))
        ids.append(usuario.id)

    xp_semana = dict(
        db.session.query(Pontuacao.usuario_id, func.sum(Pontuacao.pontos))
        .filter(Pontuacao.data_hora >= inicio_da_semana(), Pontuacao.usuario_id.in_(ids))
        .group_by(Pontuacao.usuario_id)
        .all()
    )

    pessoas = [
        {"nome": nome, "xpSemana": int(xp_semana.get(i, 0) or 0), "voce": i == usuario.id}
        for i, nome in linhas
    ]
    pessoas.sort(key=lambda p: (-p["xpSemana"], p["nome"].lower()))
    posicao = next((i + 1 for i, p in enumerate(pessoas) if p["voce"]), len(pessoas))
    return liga, posicao, pessoas


def _data(valor):
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor))


def _dias_estudados(usuario_id):
    return {
        _data(d) for (d,) in
        db.session.query(func.date(Resultado.data_hora))
        .filter(Resultado.usuario_id == usuario_id, Resultado.data_hora.isnot(None))
        .distinct()
    }


def sequencia_de_dias(usuario_id, tem_protetor=False):
    """Quantos dias seguidos a pessoa praticou (aceita hoje ou ontem; protetor cobre 1 dia pulado)."""
    dias = _dias_estudados(usuario_id)
    if not dias:
        return 0

    dia = date.today()
    if dia not in dias:
        dia -= timedelta(days=1)
        if dia not in dias and tem_protetor:
            dia -= timedelta(days=1)

    sequencia = 0
    usou_protetor = False
    while True:
        if dia in dias:
            sequencia += 1
            dia -= timedelta(days=1)
        elif tem_protetor and not usou_protetor and (dia - timedelta(days=1)) in dias:
            usou_protetor = True
            dia -= timedelta(days=1)
        else:
            break
    return sequencia


def _acertos_hoje(usuario_id):
    inicio_hoje = agora().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.session.query(func.count(Resultado.id))
        .filter(Resultado.usuario_id == usuario_id,
                Resultado.acertou.is_(True),
                Resultado.data_hora >= inicio_hoje)
        .scalar() or 0
    )


def resumo_do_progresso(usuario):
    """Tudo que o perfil, o menu, a loja e o ranking precisam saber do usuário."""
    progresso = obter_progresso(usuario.id)
    xp = progresso.experiencia or 0
    nivel_real = nivel_por_xp(xp)
    if progresso.nivel != nivel_real:
        progresso.nivel = nivel_real
    db.session.commit()

    liga, posicao, _ = ranking_da_liga(usuario)
    itens, molduras = _inventario_do_usuario(usuario.id)

    pontos_totais = (db.session.query(func.coalesce(func.sum(Pontuacao.pontos), 0))
                     .filter(Pontuacao.usuario_id == usuario.id).scalar())

    sinais_aprendidos = (
        db.session.query(func.count(func.distinct(Exercicio.sinal_id)))
        .join(Resultado, Resultado.exercicio_id == Exercicio.id)
        .filter(Resultado.usuario_id == usuario.id, Resultado.acertou.is_(True))
        .scalar()
    )

    por_status = dict(
        db.session.query(SessaoTreinamento.status, func.count(SessaoTreinamento.id))
        .filter(SessaoTreinamento.usuario_id == usuario.id)
        .group_by(SessaoTreinamento.status)
        .all()
    )
    concluidas = por_status.get("concluida", 0)
    encerradas = concluidas + por_status.get("abandonada", 0)
    taxa = round(100 * concluidas / encerradas) if encerradas else None

    acertos_dia = _acertos_hoje(usuario.id)
    xp_dobro_ativo = bool(progresso.xp_dobro_ate and progresso.xp_dobro_ate > agora())

    return {
        "usuarioId": usuario.id,
        "nome": usuario.nome,
        "fotoUrl": usuario.foto_url,
        "nivel": nivel_real,
        "xpTotal": xp,
        "moedas": int(progresso.moedas or 0),
        "itens": itens,
        "molduras": molduras,
        "moldura": progresso.moldura_ativa,
        "xpDobroAtivo": xp_dobro_ativo,
        "xpDobroAte": progresso.xp_dobro_ate.isoformat() if xp_dobro_ativo else None,
        "liga": liga,
        "posicaoRanking": posicao,
        "pontosTotais": int(pontos_totais or 0),
        "sinaisAprendidos": int(sinais_aprendidos or 0),
        "taxaAcerto": taxa,
        "sequenciaDias": sequencia_de_dias(usuario.id, tem_protetor=itens.get("protetor", 0) > 0),
        "desafioDia": {
            "atual": min(acertos_dia, META_DESAFIO_DIA),
            "total": META_DESAFIO_DIA,
            "concluido": acertos_dia >= META_DESAFIO_DIA,
        },
    }


# ================== SESSÕES E TENTATIVAS ==================

class TentativaInvalida(Exception):
    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def abrir_sessao(usuario, letra):
    """
    Abre uma sessão de treino. Sessões anteriores em aberto sem nenhuma tentativa
    são removidas (navegar pelas letras não derruba a taxa de acerto); as que
    tiveram tentativa viram 'abandonada'.
    """
    sinal = buscar_sinal(letra)
    exercicio = Exercicio.query.filter_by(sinal_id=sinal.id).order_by(Exercicio.id).first() if sinal else None
    if exercicio is None:
        raise TentativaInvalida("Essa letra não tem exercício cadastrado.", 404)

    momento = agora()
    abertas = SessaoTreinamento.query.filter_by(usuario_id=usuario.id, status="em_andamento").all()
    for aberta in abertas:
        tem_tentativa = Resultado.query.filter_by(sessao_id=aberta.id).first() is not None
        if tem_tentativa:
            aberta.status = "abandonada"
            aberta.fim = momento
        else:
            db.session.delete(aberta)

    sessao = SessaoTreinamento(usuario_id=usuario.id, exercicio_id=exercicio.id,
                               status="em_andamento", inicio=momento)
    db.session.add(sessao)
    db.session.commit()
    return sessao, exercicio


def registrar_tentativa(usuario, sessao_id, sinal_previsto, certeza, certeza_minima=None):
    """
    Guarda o que o modelo reconheceu numa sessão de treino com lock na linha da sessão
    para impedir pontuação duplicada em requisições simultâneas.
    """
    sessao = (
        db.session.query(SessaoTreinamento)
        .filter_by(id=sessao_id)
        .with_for_update()
        .first()
    )
    if sessao is None or sessao.usuario_id != usuario.id:
        raise TentativaInvalida("Sessão não encontrada.", 404)
    if sessao.status != "em_andamento":
        raise TentativaInvalida("Essa sessão já foi encerrada.", 409)

    exercicio = db.session.get(Exercicio, sessao.exercicio_id)
    sinal = db.session.get(Sinal, exercicio.sinal_id)

    sinal_previsto = (sinal_previsto or "").strip()
    minima = CERTEZA_MINIMA if certeza_minima is None else certeza_minima
    acertou = sinal_previsto.lower() == sinal.nome.lower() and certeza >= minima

    progresso = obter_progresso(usuario.id, bloquear=True)
    nivel_antes = nivel_por_xp(progresso.experiencia or 0)
    pontos = 0
    multiplicador = 1
    tipo_pontos = None
    if acertou:
        multiplicador = 2 if (progresso.xp_dobro_ate and progresso.xp_dobro_ate > agora()) else 1
        pontos_base, tipo_pontos = pontos_do_acerto(usuario.id, exercicio, sinal)
        pontos = pontos_base * multiplicador

    resultado = Resultado(usuario_id=usuario.id, exercicio_id=exercicio.id,
                          sessao_id=sessao.id, sinal_identificado=sinal_previsto[:50],
                          confianca=float(certeza), acertou=acertou, pontos_obtidos=pontos)
    db.session.add(resultado)
    db.session.flush()

    moedas_ganhas = 0
    if acertou:
        db.session.add(Pontuacao(usuario_id=usuario.id, resultado_id=resultado.id,
                                 origem="reconhecimento", pontos=pontos))
        progresso.experiencia = (progresso.experiencia or 0) + pontos
        novo_nivel = nivel_por_xp(progresso.experiencia)
        if novo_nivel > nivel_antes:
            moedas_ganhas = MOEDAS_POR_NIVEL * (novo_nivel - nivel_antes)
            progresso.moedas = (progresso.moedas or 0) + moedas_ganhas
        progresso.nivel = novo_nivel
        sessao.status = "concluida"
        sessao.fim = agora()

    novas_conquistas = verificar_conquistas(usuario, progresso, commit=False)
    db.session.commit()

    return {
        "acertou": acertou,
        "sinalEsperado": sinal.nome,
        "pontosGanhos": pontos,
        "tipoPontos": tipo_pontos,      # "novo", "revisao" ou "repeticao"
        "xpDobro": multiplicador == 2,
        "moedasGanhas": moedas_ganhas,
        "xpTotal": progresso.experiencia,
        "nivel": progresso.nivel,
        "subiuDeNivel": progresso.nivel > nivel_antes,
        "novasConquistas": novas_conquistas,
    }


# ================== LOJA ==================

def dados_da_loja(usuario):
    progresso = obter_progresso(usuario.id)
    itens, molduras = _inventario_do_usuario(usuario.id)
    xp_dobro_ativo = bool(progresso.xp_dobro_ate and progresso.xp_dobro_ate > agora())
    return {
        "moedas": int(progresso.moedas or 0),
        "itens": ITENS_LOJA,
        "molduras": MOLDURAS_LOJA,
        "inventario": {
            "itens": itens,
            "molduras": molduras,
            "moldura": progresso.moldura_ativa,
            "xpDobroAtivo": xp_dobro_ativo,
            "xpDobroAte": progresso.xp_dobro_ate.isoformat() if xp_dobro_ativo else None,
        },
    }


def comprar_na_loja(usuario, tipo, item_id):
    progresso = obter_progresso(usuario.id, bloquear=True)

    if tipo == "item":
        item = _ITENS_POR_ID.get(item_id)
        if not item:
            raise TentativaInvalida("Item não encontrado.", 404)
        reg = UsuarioItem.query.filter_by(usuario_id=usuario.id, item_id=item_id).first()
        qtd = reg.quantidade if reg else 0
        if qtd >= item["maximo"]:
            raise TentativaInvalida("Você já atingiu o limite desse item.", 409)
        if (progresso.moedas or 0) < item["preco"]:
            raise TentativaInvalida("Moedas insuficientes.", 400)
        progresso.moedas -= item["preco"]
        if reg is None:
            db.session.add(UsuarioItem(usuario_id=usuario.id, item_id=item_id, quantidade=1))
        else:
            reg.quantidade += 1
        nome = item["nome"]
        preco = item["preco"]
    elif tipo == "moldura":
        moldura = _MOLDURAS_POR_ID.get(item_id)
        if not moldura:
            raise TentativaInvalida("Moldura não encontrada.", 404)
        if UsuarioMoldura.query.filter_by(usuario_id=usuario.id, moldura_id=item_id).first():
            raise TentativaInvalida("Você já possui essa moldura.", 409)
        if (progresso.moedas or 0) < moldura["preco"]:
            raise TentativaInvalida("Moedas insuficientes.", 400)
        progresso.moedas -= moldura["preco"]
        db.session.add(UsuarioMoldura(usuario_id=usuario.id, moldura_id=item_id))
        progresso.moldura_ativa = item_id
        nome = f"Moldura {moldura['nome']}"
        preco = moldura["preco"]
    else:
        raise TentativaInvalida("Tipo de compra inválido.", 422)

    novas = verificar_conquistas(usuario, progresso, commit=False)
    db.session.commit()
    return {"ok": True, "nome": nome, "preco": preco, "moedas": progresso.moedas, "novasConquistas": novas}


def usar_item(usuario, item_id):
    if item_id != "xpDobro":
        raise TentativaInvalida("Esse item é usado automaticamente.", 422)
    progresso = obter_progresso(usuario.id, bloquear=True)
    reg = UsuarioItem.query.filter_by(usuario_id=usuario.id, item_id=item_id).first()
    if reg is None or reg.quantidade <= 0:
        raise TentativaInvalida("Você não tem esse item.", 400)

    reg.quantidade -= 1
    base = progresso.xp_dobro_ate if (progresso.xp_dobro_ate and progresso.xp_dobro_ate > agora()) else agora()
    progresso.xp_dobro_ate = base + timedelta(minutes=15)
    db.session.commit()
    return {"ok": True, "xpDobroAte": progresso.xp_dobro_ate.isoformat(), "restante": reg.quantidade}


def trocar_moldura(usuario, moldura_id):
    progresso = obter_progresso(usuario.id, bloquear=True)
    if moldura_id is not None:
        if not UsuarioMoldura.query.filter_by(usuario_id=usuario.id, moldura_id=moldura_id).first():
            raise TentativaInvalida("Você não possui essa moldura.", 403)
    progresso.moldura_ativa = moldura_id
    db.session.commit()
    return {"ok": True, "moldura": moldura_id}


# ================== MISSÕES DA SEMANA ==================

MISSOES_DEFINICAO = [
    {"id": 1, "icone": "bi-calendar-check", "texto": "Pratique em 5 dias desta semana", "total": 5, "moedas": 40, "xp": 50},
    {"id": 2, "icone": "bi-check-circle", "texto": "Acerte 20 sinais nesta semana", "total": 20, "moedas": 30, "xp": 40},
    {"id": 3, "icone": "bi-bullseye", "texto": "Aprenda 5 sinais diferentes na semana", "total": 5, "moedas": 50, "xp": 60},
    {"id": 4, "icone": "bi-patch-check-fill", "texto": "Conclua 10 sessões de treino", "total": 10, "moedas": 40, "xp": 50},
]


def _progresso_missoes(usuario_id):
    inicio = inicio_da_semana()
    dias_semana = int(
        db.session.query(func.count(func.distinct(func.date(Resultado.data_hora))))
        .filter(Resultado.usuario_id == usuario_id, Resultado.data_hora >= inicio)
        .scalar() or 0
    )
    acertos_semana = int(
        db.session.query(func.count(Resultado.id))
        .filter(Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True), Resultado.data_hora >= inicio)
        .scalar() or 0
    )
    sinais_semana = int(
        db.session.query(func.count(func.distinct(Exercicio.sinal_id)))
        .join(Resultado, Resultado.exercicio_id == Exercicio.id)
        .filter(Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True), Resultado.data_hora >= inicio)
        .scalar() or 0
    )
    sessoes_semana = int(
        db.session.query(func.count(SessaoTreinamento.id))
        .filter(SessaoTreinamento.usuario_id == usuario_id,
                SessaoTreinamento.status == "concluida",
                SessaoTreinamento.fim >= inicio)
        .scalar() or 0
    )
    return {1: dias_semana, 2: acertos_semana, 3: sinais_semana, 4: sessoes_semana}


def listar_missoes_semana(usuario):
    semana = inicio_da_semana().date()
    resgatadas = {
        r.missao_id for r in
        MissaoResgatada.query.filter_by(usuario_id=usuario.id, semana_inicio=semana).all()
    }
    contagens = _progresso_missoes(usuario.id)
    lista = []
    for m in MISSOES_DEFINICAO:
        atual = min(contagens.get(m["id"], 0), m["total"])
        lista.append({
            **m,
            "atual": atual,
            "resgatada": m["id"] in resgatadas,
        })
    return lista


def resgatar_missao(usuario, missao_id):
    definicao = next((m for m in MISSOES_DEFINICAO if m["id"] == missao_id), None)
    if definicao is None:
        raise TentativaInvalida("Missão não encontrada.", 404)

    semana = inicio_da_semana().date()
    progresso = obter_progresso(usuario.id, bloquear=True)

    ja = MissaoResgatada.query.filter_by(
        usuario_id=usuario.id, semana_inicio=semana, missao_id=missao_id
    ).first()
    if ja is not None:
        raise TentativaInvalida("Você já resgatou essa missão nesta semana.", 409)

    atual = _progresso_missoes(usuario.id).get(missao_id, 0)
    if atual < definicao["total"]:
        raise TentativaInvalida("Missão ainda não foi concluída.", 400)

    nivel_antes = nivel_por_xp(progresso.experiencia or 0)
    db.session.add(MissaoResgatada(usuario_id=usuario.id, semana_inicio=semana, missao_id=missao_id))
    db.session.add(Pontuacao(usuario_id=usuario.id, resultado_id=None, origem="missao", pontos=definicao["xp"]))
    progresso.experiencia = (progresso.experiencia or 0) + definicao["xp"]
    progresso.moedas = (progresso.moedas or 0) + definicao["moedas"]
    novo_nivel = nivel_por_xp(progresso.experiencia)
    if novo_nivel > nivel_antes:
        progresso.moedas += MOEDAS_POR_NIVEL * (novo_nivel - nivel_antes)
    progresso.nivel = novo_nivel

    novas = verificar_conquistas(usuario, progresso, commit=False)
    db.session.commit()
    return {
        "ok": True,
        "moedasGanhas": definicao["moedas"],
        "xpGanho": definicao["xp"],
        "moedas": progresso.moedas,
        "xpTotal": progresso.experiencia,
        "nivel": progresso.nivel,
        "subiuDeNivel": progresso.nivel > nivel_antes,
        "novasConquistas": novas,
    }


# ================== CONQUISTAS ==================

def _metricas_conquistas(usuario_id, progresso):
    total_alfabeto = max(1, int(Sinal.query.filter_by(categoria="Alfabeto").count() or len(LETRAS)))
    sinais_aprendidos = int(
        db.session.query(func.count(func.distinct(Exercicio.sinal_id)))
        .join(Resultado, Resultado.exercicio_id == Exercicio.id)
        .filter(Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True))
        .scalar() or 0
    )
    alfabeto_aprendido = int(
        db.session.query(func.count(func.distinct(Sinal.id)))
        .join(Exercicio, Exercicio.sinal_id == Sinal.id)
        .join(Resultado, Resultado.exercicio_id == Exercicio.id)
        .filter(Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True), Sinal.categoria == "Alfabeto")
        .scalar() or 0
    )
    pontos_totais = int(
        db.session.query(func.coalesce(func.sum(Pontuacao.pontos), 0))
        .filter(Pontuacao.usuario_id == usuario_id).scalar() or 0
    )
    dias_totais = len(_dias_estudados(usuario_id))
    itens, molduras = _inventario_do_usuario(usuario_id)
    sequencia = sequencia_de_dias(usuario_id, tem_protetor=itens.get("protetor", 0) > 0)
    compras = sum(itens.values()) + len(molduras)
    semana = inicio_da_semana().date()
    missoes_semana = int(MissaoResgatada.query.filter_by(usuario_id=usuario_id, semana_inicio=semana).count())
    nivel = nivel_por_xp(progresso.experiencia or 0)
    liga = liga_do_nivel(nivel)

    # horas dos acertos (calculado aqui, e não com HOUR() do MySQL, pra funcionar em qualquer banco)
    horas = {d.hour for (d,) in db.session.query(Resultado.data_hora).filter(
        Resultado.usuario_id == usuario_id, Resultado.acertou.is_(True)) if d}
    madrugador = any(h < 7 for h in horas)
    coruja = any(h >= 22 for h in horas)

    return {
        "sinais_aprendidos": sinais_aprendidos,
        "alfabeto_aprendido": alfabeto_aprendido,
        "total_alfabeto": total_alfabeto,
        "pontos_totais": pontos_totais,
        "dias_totais": dias_totais,
        "sequencia": sequencia,
        "compras": compras,
        "missoes_semana": missoes_semana,
        "nivel": nivel,
        "liga_ouro": 1 if liga in ("ouro", "diamante") else 0,
        "madrugador": 1 if madrugador else 0,
        "coruja": 1 if coruja else 0,
        "desafio_hoje": 1 if _acertos_hoje(usuario_id) >= META_DESAFIO_DIA else 0,
    }


def _catalogo_conquistas(m):
    return [
        {"id": 1, "icone": "bi-hand-index-thumb", "nome": "Primeiro Sinal", "pontos": 20,
         "descricao": "Faça seu primeiro sinal certo na câmera.",
         "requisito": "Acerte pelo menos 1 sinal em Libras.",
         "como": "Você acertou seu primeiro sinal em Libras.",
         "atual": m["sinais_aprendidos"], "total": 1},
        {"id": 2, "icone": "bi-fire", "nome": "Sequência de 5", "pontos": 30,
         "descricao": "Estude 5 dias seguidos.",
         "requisito": "Pratique 5 dias seguidos sem pular.",
         "como": "Você manteve 5 dias seguidos de estudo.",
         "atual": m["sequencia"], "total": 5},
        {"id": 3, "icone": "bi-bullseye", "nome": "Desafio do Dia", "pontos": 40,
         "descricao": "Complete o desafio do dia (5 acertos).",
         "requisito": "Acerte 5 sinais no mesmo dia.",
         "como": "Você completou o desafio de 5 acertos no dia.",
         "atual": m["desafio_hoje"], "total": 1},
        {"id": 4, "icone": "bi-calendar-check", "nome": "Estudante Dedicado", "pontos": 50,
         "descricao": "Estude por 10 dias no total.",
         "requisito": "Pratique em 10 dias diferentes no SignEdu.",
         "como": "Você chegou a 10 dias de estudo no SignEdu.",
         "atual": m["dias_totais"], "total": 10},
        {"id": 5, "icone": "bi-fonts", "nome": "Alfabeto Completo", "pontos": 60,
         "descricao": f"Aprenda todas as {m['total_alfabeto']} letras disponíveis do alfabeto.",
         "requisito": f"Acerte todas as {m['total_alfabeto']} letras cadastradas pelo menos uma vez.",
         "como": "Você completou todas as letras disponíveis do alfabeto.",
         "atual": m["alfabeto_aprendido"], "total": m["total_alfabeto"]},
        {"id": 6, "icone": "bi-lightning-charge", "nome": "Sequência de 15", "pontos": 60,
         "descricao": "Estude 15 dias seguidos.",
         "requisito": "Pratique todos os dias por 15 dias seguidos.",
         "como": "Você manteve 15 dias seguidos de estudo.",
         "atual": m["sequencia"], "total": 15},
        {"id": 7, "icone": "bi-star-fill", "nome": "500 Pontos", "pontos": 50,
         "descricao": "Junte 500 pontos.",
         "requisito": "Some 500 pontos praticando e completando missões.",
         "como": "Você alcançou 500 pontos totais.",
         "atual": m["pontos_totais"], "total": 500},
        {"id": 8, "icone": "bi-gem", "nome": "1000 Pontos", "pontos": 100,
         "descricao": "Junte 1000 pontos.",
         "requisito": "Some 1000 pontos praticando e completando missões.",
         "como": "Você alcançou 1000 pontos totais.",
         "atual": m["pontos_totais"], "total": 1000},
        {"id": 9, "icone": "bi-mortarboard", "nome": "Nível 5", "pontos": 60,
         "descricao": "Chegue ao nível 5.",
         "requisito": "Ganhe XP praticando até chegar ao nível 5.",
         "como": "Você atingiu o nível 5 (Comunicador).",
         "atual": m["nivel"], "total": 5},
        {"id": 10, "icone": "bi-award-fill liga-ouro", "nome": "Liga Ouro", "pontos": 80,
         "descricao": "Alcance a Liga Ouro.",
         "requisito": "Chegue ao nível 5 para entrar na Liga Ouro.",
         "como": "Você alcançou a Liga Ouro.",
         "atual": m["liga_ouro"], "total": 1},
        {"id": 11, "icone": "bi-clipboard-check", "nome": "Semana Completa", "pontos": 60,
         "descricao": "Resgate todas as 4 missões da semana.",
         "requisito": "Resgate as 4 missões da semana antes de domingo 23h59.",
         "como": "Você resgatou todas as missões da semana.",
         "atual": m["missoes_semana"], "total": 4},
        {"id": 12, "icone": "bi-bag-check", "nome": "Primeira Compra", "pontos": 20,
         "descricao": "Compre algo na loja.",
         "requisito": "Troque suas moedas por qualquer item ou moldura.",
         "como": "Você fez sua primeira compra na loja.",
         "atual": m["compras"], "total": 1},
        {"id": 13, "icone": "bi-sunrise", "nome": "Madrugador", "pontos": 20,
         "descricao": "Estude antes das 7h da manhã.",
         "requisito": "Acerte um sinal antes das 7h.",
         "como": "Você praticou antes das 7h da manhã.",
         "atual": m["madrugador"], "total": 1},
        {"id": 14, "icone": "bi-moon-stars", "nome": "Coruja", "pontos": 20,
         "descricao": "Estude depois das 22h.",
         "requisito": "Acerte um sinal depois das 22h.",
         "como": "Você praticou depois das 22h.",
         "atual": m["coruja"], "total": 1},
    ]


def verificar_conquistas(usuario, progresso=None, commit=True):
    """Confere conquistas ainda não desbloqueadas, registra no banco e soma pontos."""
    if progresso is None:
        progresso = obter_progresso(usuario.id, bloquear=True)
    existentes = {
        r.conquista_id for r in UsuarioConquista.query.filter_by(usuario_id=usuario.id).all()
    }
    catalogo = _catalogo_conquistas(_metricas_conquistas(usuario.id, progresso))
    novas = []
    for c in catalogo:
        if c["id"] in existentes:
            continue
        if c["atual"] >= c["total"]:
            db.session.add(UsuarioConquista(
                usuario_id=usuario.id, conquista_id=c["id"], como_conseguiu=c["como"]
            ))
            db.session.add(Pontuacao(
                usuario_id=usuario.id, resultado_id=None, origem="conquista", pontos=c["pontos"]
            ))
            novas.append({"id": c["id"], "icone": c["icone"], "nome": c["nome"], "pontos": c["pontos"]})
    if commit and novas:
        db.session.commit()
    return novas


def listar_conquistas(usuario):
    progresso = obter_progresso(usuario.id)
    verificar_conquistas(usuario, progresso, commit=True)

    salvas = {
        r.conquista_id: r for r in UsuarioConquista.query.filter_by(usuario_id=usuario.id).all()
    }
    catalogo = _catalogo_conquistas(_metricas_conquistas(usuario.id, progresso))
    lista = []
    for c in catalogo:
        reg = salvas.get(c["id"])
        if reg:
            lista.append({
                "id": c["id"], "icone": c["icone"], "nome": c["nome"], "pontos": c["pontos"],
                "descricao": c["descricao"], "conquistada": True,
                "dataConquista": reg.data_conquista.isoformat() if reg.data_conquista else None,
                "comoConseguiu": reg.como_conseguiu or c["como"],
            })
        else:
            lista.append({
                "id": c["id"], "icone": c["icone"], "nome": c["nome"], "pontos": c["pontos"],
                "descricao": c["descricao"], "conquistada": False,
                "requisito": c["requisito"],
                "progressoAtual": min(c["atual"], c["total"]),
                "progressoTotal": c["total"],
            })
    return lista


# ================== CONFIGURAÇÕES ==================

CONFIG_PADRAO = {
    "meta": "10",
    "avisoMeta": True,
    "velocidade": "1",
    "lembrete": False,
    "horario": "19:00",
    "avisoConquista": True,
    "fonte": "100",
}


def obter_configuracoes(usuario_id):
    reg = UsuarioConfiguracao.query.filter_by(usuario_id=usuario_id).first()
    if reg is None:
        return dict(CONFIG_PADRAO)
    return {
        "meta": reg.meta,
        "avisoMeta": bool(reg.aviso_meta),
        "velocidade": reg.velocidade,
        "lembrete": bool(reg.lembrete),
        "horario": reg.horario,
        "avisoConquista": bool(reg.aviso_conquista),
        "fonte": reg.fonte,
    }


def salvar_configuracoes(usuario_id, dados):
    meta = str(dados.get("meta", "10"))
    if meta not in ("5", "10", "15", "20"):
        raise TentativaInvalida("Meta inválida.", 422)
    velocidade = str(dados.get("velocidade", "1"))
    if velocidade not in ("0.5", "0.75", "1"):
        raise TentativaInvalida("Velocidade inválida.", 422)
    fonte = str(dados.get("fonte", "100"))
    if fonte not in ("90", "100", "110", "120", "130"):
        raise TentativaInvalida("Tamanho de fonte inválido.", 422)
    horario = str(dados.get("horario", "19:00"))
    if not re.fullmatch(r"\d{2}:\d{2}", horario):
        raise TentativaInvalida("Horário inválido.", 422)

    reg = UsuarioConfiguracao.query.filter_by(usuario_id=usuario_id).first()
    if reg is None:
        reg = UsuarioConfiguracao(usuario_id=usuario_id)
        db.session.add(reg)

    reg.meta = meta
    reg.aviso_meta = bool(dados.get("avisoMeta", True))
    reg.velocidade = velocidade
    reg.lembrete = bool(dados.get("lembrete", False))
    reg.horario = horario
    reg.aviso_conquista = bool(dados.get("avisoConquista", True))
    reg.fonte = fonte
    db.session.commit()
    return obter_configuracoes(usuario_id)


# ================== EXCLUSÃO DE CONTA ==================

def excluir_usuario_completo(usuario, motivo, comentario):
    """Apaga todos os dados do usuário na ordem das FKs e guarda o motivo anonimizado."""
    uid = usuario.id
    if motivo:
        db.session.add(ExclusaoConta(motivo=str(motivo)[:50], comentario=(comentario or "")[:500]))

    Pontuacao.query.filter_by(usuario_id=uid).delete()
    Resultado.query.filter_by(usuario_id=uid).delete()
    SessaoTreinamento.query.filter_by(usuario_id=uid).delete()
    UsuarioItem.query.filter_by(usuario_id=uid).delete()
    UsuarioMoldura.query.filter_by(usuario_id=uid).delete()
    UsuarioConfiguracao.query.filter_by(usuario_id=uid).delete()
    MissaoResgatada.query.filter_by(usuario_id=uid).delete()
    UsuarioConquista.query.filter_by(usuario_id=uid).delete()
    db.session.delete(usuario)
    db.session.commit()
