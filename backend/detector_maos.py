"""
Detector de mãos do SignEdu (MediaPipe Hand Landmarker + Random Forest).

Recebe uma imagem (os bytes de um JPEG/PNG vindo do navegador), roda o
MediaPipe e devolve os 21 pontos (landmarks) de cada mão encontrada.

Se o modelo treinado (modelo_letras.joblib) existir, também diz qual letra
do alfabeto em Libras a primeira mão está fazendo (sinais parados, 1 foto).

Sinais com MOVIMENTO (Z, H, J, K, X, saudações...) não dá pra reconhecer com
uma foto só. E muitos sinais usam o CORPO e o ROSTO, não só as mãos (onde a mão
fica em relação ao rosto e ao peito, movimento da cabeça, expressão facial).
Pra eles o detector também sabe:
  - ler um VÍDEO (ler_video) e achar a mão, o corpo (MediaPipe Pose) e o rosto
    (MediaPipe Face) em cada quadro;
  - transformar a sequência de quadros em características
    (sequencia_para_caracteristicas): formato da mão, caminho do pulso, posição
    da mão no corpo e no rosto, movimento da cabeça e expressão do rosto;
  - classificar o movimento com o modelo_movimento.joblib (prever_movimento).
"""

import os
import tempfile
import threading
from collections import Counter
from pathlib import Path

import cv2
import joblib
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# Traduz o lado da mão que o MediaPipe devolve em inglês
LADOS = {"Left": "Esquerda", "Right": "Direita"}

# ---- Configurações dos sinais com movimento ----
# (o extrair_sequencias.py, o treinar_modelo_movimento.py e o app usam os mesmos valores)
N_QUADROS_FORMA = 8          # quantos "instantes" do formato da mão entram no modelo
N_QUADROS_TRAJETORIA = 16    # quantos "instantes" do caminho do pulso entram no modelo
MIN_QUADROS_COM_MAO = 6      # menos que isso: a mão quase não apareceu, não dá pra julgar
N_AMOSTRAS_VIDEO = 48        # quadros analisados por vídeo (espalhados do início ao fim)
LIMITE_QUADROS_VIDEO = 5400  # ~3 min a 30 fps: vídeos maiores são recusados
LARGURA_MAXIMA_VIDEO = 640   # quadros maiores são reduzidos (mais rápido, mesmo resultado)
EXTENSOES_VIDEO = {".mp4", ".mov", ".avi", ".webm", ".mkv"}

# ---- Corpo e rosto (sinais que usam mais que as mãos) ----
N_QUADROS_CORPO = 8          # quantos "instantes" do corpo/rosto entram no modelo
VISIBILIDADE_MINIMA = 0.5    # os dois ombros precisam aparecer com pelo menos isso

# Pontos do MediaPipe Pose que importam (o resto é perna/pé): nariz, ombros, cotovelos, pulsos
PONTOS_CORPO = (0, 11, 12, 13, 14, 15, 16)
# posições dentro de PONTOS_CORPO
NARIZ_CORPO, OMBRO_E, OMBRO_D = 0, 1, 2

# Pontos do MediaPipe Face Mesh: ponta do nariz, queixo, testa, boca, bochecha esquerda e direita
PONTOS_ROSTO = (1, 152, 10, 13, 234, 454)
NARIZ_ROSTO, QUEIXO, TESTA, BOCA, BOCHECHA_E, BOCHECHA_D = range(6)

# Expressões do rosto (blendshapes do MediaPipe, de 0 a 1). Pares esquerda/direita são
# tirados em média: assim a mão esquerda espelhada e a direita ficam iguais.
EXPRESSOES = (
    ("browInnerUp",),                        # sobrancelhas levantadas no meio
    ("browDownLeft", "browDownRight"),       # sobrancelhas franzidas
    ("browOuterUpLeft", "browOuterUpRight"), # sobrancelhas levantadas nas pontas
    ("cheekPuff",),                          # bochechas infladas
    ("eyeBlinkLeft", "eyeBlinkRight"),       # olhos fechados
    ("eyeWideLeft", "eyeWideRight"),         # olhos arregalados
    ("jawOpen",),                            # boca aberta
    ("mouthFunnel",),                        # boca em "O"
    ("mouthPucker",),                        # boca em bico
    ("mouthSmileLeft", "mouthSmileRight"),   # sorriso
    ("mouthFrownLeft", "mouthFrownRight"),   # boca pra baixo
    ("mouthPressLeft", "mouthPressRight"),   # lábios apertados
    ("mouthClose",),                         # boca fechada
)

# Tamanho do vetor de características do modelo de movimento (precisa bater com o
# sequencia_para_caracteristicas; um modelo treinado com outro tamanho é recusado)
_POR_INSTANTE_CORPO = 2 * len(PONTOS_CORPO) + 4 + 8 + 2 + len(EXPRESSOES)
N_CARACTERISTICAS_MOVIMENTO = (
    N_QUADROS_FORMA * 63 + N_QUADROS_TRAJETORIA * 2
    + (N_QUADROS_TRAJETORIA - 1) * 2 + 4
    + N_QUADROS_CORPO * _POR_INSTANTE_CORPO + 6
)
# Só a mão (formato + caminho do pulso): é o começo do vetor completo. Usado nas letras com
# movimento e quando o corpo/rosto não aparecem (pessoa sentada ou perto da câmera).
N_CARACTERISTICAS_MAO = N_QUADROS_FORMA * 63 + N_QUADROS_TRAJETORIA * 2 + (N_QUADROS_TRAJETORIA - 1) * 2 + 4

# Grupos dos sinais com movimento (a tela sabe qual sinal a pessoa quer fazer, então o modelo
# só precisa escolher entre os sinais do mesmo grupo):
#   Alfabeto  (H, J, K, X, Z, Ç): só a mão;
#   Saudações: mão + corpo + rosto quando aparecem; senão, só a mão.
def grupo_do_movimento(sinal):
    return "Alfabeto" if sinal and len(sinal) == 1 and sinal.isalpha() else "Saudações"


def pontos_para_caracteristicas(pontos, lado):
    """
    Transforma os 21 pontos da mão nos 63 números que o Random Forest usa.

    Os pontos são "normalizados" pra que a posição e o tamanho da mão na
    imagem não importem, só o formato da mão:
      1. o pulso (ponto 0) vira a origem (0, 0, 0);
      2. tudo é dividido pela maior distância até o pulso (mão perto ou
         longe da câmera fica igual);
      3. mão esquerda é espelhada, pra ficar igual a uma mão direita.

    Essa MESMA função é usada no treino (treinar_modelo.py) e no app.
    """
    pontos = np.array([[p["x"], p["y"], p["z"]] for p in pontos], dtype=np.float32)

    pontos = pontos - pontos[0]

    if lado == "Esquerda":
        pontos[:, 0] = -pontos[:, 0]

    maior_distancia = np.max(np.linalg.norm(pontos[:, :2], axis=1))
    if maior_distancia > 0:
        pontos = pontos / maior_distancia

    return pontos.flatten()


def _reamostrar(matriz, quantidade):
    """Estica ou encolhe uma sequência (linhas = quadros) para 'quantidade' quadros.
    Assim um sinal feito rápido ou devagar vira a mesma coisa pro modelo."""
    matriz = np.asarray(matriz, dtype=np.float32)
    if len(matriz) == 1:
        return np.repeat(matriz, quantidade, axis=0)

    antigo = np.linspace(0.0, 1.0, len(matriz))
    novo = np.linspace(0.0, 1.0, quantidade)
    return np.stack(
        [np.interp(novo, antigo, matriz[:, coluna]) for coluna in range(matriz.shape[1])],
        axis=1,
    )


def _preencher_buracos(matriz, validos):
    """Quadros em que o corpo ou o rosto não apareceu (ex.: a mão tapou o rosto) recebem o
    valor dos quadros vizinhos em que apareceu. 'validos' diz em quais quadros tem dado."""
    validos = np.asarray(validos, dtype=bool)
    matriz = np.array(matriz, dtype=np.float32)
    if validos.all():
        return matriz
    indices = np.arange(len(matriz))
    for coluna in range(matriz.shape[1]):
        matriz[:, coluna] = np.interp(indices, indices[validos], matriz[validos, coluna])
    return matriz


def _corpo_do_quadro(quadro, proporcao, espelho):
    """
    Características do corpo e do rosto de UM quadro, em "larguras de ombro":
      - pontos do corpo (nariz, ombros, cotovelos, pulsos) em relação ao meio dos ombros;
      - palma e ponta do indicador da mão em relação ao meio dos ombros;
      - palma em relação ao nariz, queixo, testa e boca;
      - inclinação/giro da cabeça;
      - as expressões do rosto.
    Devolve (vetor_corpo, vetor_rosto, indicadores_do_caminho) ou None se o corpo não apareceu.
    vetor_rosto é None se o rosto não apareceu (o buraco é preenchido depois).
    """
    corpo = quadro.get("corpo")
    if not corpo or len(corpo) != len(PONTOS_CORPO):
        return None
    if min(corpo[OMBRO_E][2], corpo[OMBRO_D][2]) < VISIBILIDADE_MINIMA:
        return None

    def ajustar(ponto):             # x e y são frações da largura e da altura: igualar as escalas
        return np.array([ponto[0] * proporcao, ponto[1]], dtype=np.float32)

    pontos_corpo = np.array([ajustar(p) for p in corpo])
    centro = (pontos_corpo[OMBRO_E] + pontos_corpo[OMBRO_D]) / 2
    largura_ombros = float(np.linalg.norm(pontos_corpo[OMBRO_E] - pontos_corpo[OMBRO_D]))
    if largura_ombros < 1e-3:
        return None

    def relativo(ponto):            # em larguras de ombro; espelhado se for mão esquerda
        r = (ponto - centro) / largura_ombros
        r[0] *= espelho
        return r

    mao = np.array([[p["x"], p["y"]] for p in quadro["pontos"]], dtype=np.float32)
    mao[:, 0] *= proporcao
    palma = mao[[0, 5, 9, 13, 17]].mean(axis=0)
    ponta = mao[8]

    partes = [relativo(p) for p in pontos_corpo]            # 7 pontos x 2
    partes += [relativo(palma), relativo(ponta)]            # 2 pontos x 2

    rosto = quadro.get("rosto")
    vetor_rosto = None
    if rosto and len(rosto.get("pontos", [])) == len(PONTOS_ROSTO) and len(rosto.get("expressao", [])) == len(EXPRESSOES):
        pontos_rosto = np.array([ajustar(p) for p in rosto["pontos"]])
        referencias = [pontos_rosto[NARIZ_ROSTO], pontos_rosto[QUEIXO], pontos_rosto[TESTA], pontos_rosto[BOCA]]

        proximidade = []
        for referencia in referencias:
            d = (palma - referencia) / largura_ombros
            d[0] *= espelho
            proximidade.append(d)

        largura_rosto = max(float(np.linalg.norm(pontos_rosto[BOCHECHA_E] - pontos_rosto[BOCHECHA_D])), 1e-6)
        meio_bochechas = (pontos_rosto[BOCHECHA_E] + pontos_rosto[BOCHECHA_D]) / 2
        giro = float((pontos_rosto[NARIZ_ROSTO][0] - meio_bochechas[0]) / largura_rosto) * espelho
        inclinacao = float((pontos_rosto[BOCHECHA_D][1] - pontos_rosto[BOCHECHA_E][1]) / largura_rosto) * espelho

        vetor_rosto = np.concatenate([
            np.concatenate(proximidade),                    # 4 pontos x 2
            [giro, inclinacao],                             # 2
            np.asarray(rosto["expressao"], dtype=np.float32),
        ]).astype(np.float32)

    return np.concatenate(partes).astype(np.float32), vetor_rosto, (relativo(palma), relativo(pontos_corpo[NARIZ_CORPO]))


# ---- Escolha da mão que faz o sinal ----
# A câmera e os vídeos podem mostrar as duas mãos: muita gente deixa a outra mão parada
# no peito ou na barriga enquanto sinaliza. Antes, o sistema usava sempre a "primeira mão"
# que o MediaPipe devolvia (maos[0]), e às vezes era justamente a mão parada.
# Agora as duas mãos são acompanhadas pela sequência e fica a que mais se mexe e fica mais
# alta (a mão parada costuma ficar embaixo, na cintura ou na barriga). Nos sinais feitos com
# as duas mãos, a outra continua representada pelos pontos dos pulsos e cotovelos do corpo.
PESO_ALTURA_MAO = 4.0        # peso da altura na escolha da mão (veja escolher_mao_na_sequencia)
RECORTE_PROPORCAO = 4 / 3    # quadros mais largos que 4:3 (16:9 dos notebooks) são recortados no centro


def recortar_4_3(frame):
    """Recorta o centro de um quadro mais largo que 4:3 (ex.: 16:9) para 4:3.
    O modelo das letras foi treinado com imagens 4:3 e erra mais em 16:9.
    Quadros 4:3 ou em pé (celular na vertical) ficam como estão."""
    altura, largura = frame.shape[:2]
    if largura / altura <= RECORTE_PROPORCAO + 1e-3:
        return frame
    nova_largura = int(round(altura * RECORTE_PROPORCAO))
    inicio = (largura - nova_largura) // 2
    return frame[:, inicio:inicio + nova_largura]


def _palma(pontos, proporcao):
    m = np.array([[pontos[i]["x"] * proporcao, pontos[i]["y"]] for i in (0, 5, 9, 13, 17)], dtype=np.float32)
    return m.mean(axis=0)


def _tamanho_mao(pontos, proporcao):
    m = np.array([[p["x"] * proporcao, p["y"]] for p in pontos], dtype=np.float32)
    return max(float(np.max(np.linalg.norm(m - m[0], axis=1))), 1e-6)


def escolher_mao_na_sequencia(quadros):
    """
    Recebe quadros no formato {"maos": [{"lado", "pontos"}, ...], "proporcao", "corpo", "rosto"}
    (ou None) e devolve a lista no formato que o modelo usa, com UMA mão por quadro:
    {"lado", "pontos", "proporcao", "corpo", "rosto"} (ou None onde a mão escolhida não apareceu).

    As mãos são acompanhadas de um quadro pro outro pela posição da palma (a mais perto da
    posição anterior é a mesma mão). Fica a trilha com a maior nota de movimento + altura.
    Quadros que já vêm no formato antigo (com "pontos" e sem "maos") passam direto.
    """
    if not any(q and "maos" in q for q in quadros):
        return quadros

    trilhas = []          # cada trilha: {"ultima": palma, "itens": {indice_quadro: mao}}
    for indice, quadro in enumerate(quadros):
        if not quadro or not quadro.get("maos"):
            continue
        proporcao = float(quadro.get("proporcao") or 1.0)
        livres = list(range(len(trilhas)))
        for mao in quadro["maos"][:2]:
            palma = _palma(mao["pontos"], proporcao)
            melhor, distancia = None, None
            for t in livres:
                d = float(np.linalg.norm(trilhas[t]["ultima"] - palma))
                if distancia is None or d < distancia:
                    melhor, distancia = t, d
            # longe demais de qualquer trilha (mais de 1,5 tamanho de mão): é outra mão
            if melhor is not None and distancia <= 1.5 * _tamanho_mao(mao["pontos"], proporcao) + 0.15:
                livres.remove(melhor)
            elif len(trilhas) < 2:
                trilhas.append({"ultima": palma, "itens": {}})
                melhor = len(trilhas) - 1
            elif melhor is not None:
                livres.remove(melhor)
            else:
                continue
            trilhas[melhor]["ultima"] = palma
            trilhas[melhor]["itens"][indice] = mao

    def movimento(trilha):
        """Quanto a palma andou por quadro, em tamanhos de mão."""
        indices = sorted(trilha["itens"])
        if len(indices) < 2:
            return 0.0
        total, anterior = 0.0, None
        for i in indices:
            mao = trilha["itens"][i]
            proporcao = float(quadros[i].get("proporcao") or 1.0)
            palma = _palma(mao["pontos"], proporcao)
            if anterior is not None:
                total += float(np.linalg.norm(palma - anterior)) / _tamanho_mao(mao["pontos"], proporcao)
            anterior = palma
        return total / (len(indices) - 1)

    def altura(trilha):
        """Quanto mais alta a mão (pulso mais perto do topo da imagem), maior o valor."""
        return -float(np.mean([trilha["itens"][i]["pontos"][0]["y"] for i in trilha["itens"]]))

    # Nota = movimento + peso x altura. Só o movimento não bastava: a mão parada na cintura,
    # meio fora da imagem, "treme" e parecia se mexer. A mão que sinaliza fica mais alta.
    # O peso (4) foi escolhido testando nos vídeos do especialista (treino com uma luz,
    # teste com a outra): 45% só com movimento, 77% com movimento + altura.
    candidatas = [t for t in trilhas if len(t["itens"]) >= MIN_QUADROS_COM_MAO] or trilhas
    if not candidatas:
        return [None] * len(quadros)
    escolhida = max(candidatas, key=lambda t: movimento(t) + PESO_ALTURA_MAO * altura(t))

    # O MediaPipe às vezes troca o lado (direita/esquerda) da mesma mão em alguns quadros, e o
    # lado decide se o sinal é espelhado. A trilha inteira usa o lado mais frequente.
    lado = Counter(m["lado"] for m in escolhida["itens"].values()).most_common(1)[0][0]

    saida = []
    for indice, quadro in enumerate(quadros):
        mao = escolhida["itens"].get(indice)
        if not quadro or mao is None:
            saida.append(None)
            continue
        saida.append({
            "lado": lado,
            "pontos": mao["pontos"],
            "proporcao": quadro.get("proporcao"),
            "corpo": quadro.get("corpo"),
            "rosto": quadro.get("rosto"),
        })
    return saida


def _resumo_do_caminho(caminho, passos):
    return np.array([
        np.linalg.norm(passos, axis=1).sum(),       # distância total percorrida
        np.linalg.norm(caminho[-1] - caminho[0]),   # quanto saiu do lugar (início → fim)
        caminho[:, 0].max() - caminho[:, 0].min(),  # largura do desenho
        caminho[:, 1].max() - caminho[:, 1].min(),  # altura do desenho
    ], dtype=np.float32)


# Sinal com movimento precisa de movimento: abaixo disso a mão ficou parada (ou só tremeu).
# Medido nos vídeos do especialista e em mãos paradas com tremor (veja calibrar_movimento.py).
SEM_SINAL = "Nenhum sinal"      # classe extra dos modelos de movimento: "não é nenhum destes"
ESCALA_DESLOCAMENTO = 0.45      # quanto o pulso andou, em tamanhos de mão
ESCALA_FORMATO = 0.55           # quanto o formato da mão mudou (dedos/giro)
MOVIMENTO_MINIMO = 1.0          # valor de referência da escala (usado na calibração e nos testes)

# Mínimo de movimento POR SINAL, calibrado com a câmera de verdade (modo de coleta do site,
# dados/coleta_testes.jsonl): mão parada no formato do sinal x sinal feito do jeito certo.
#   - sinais de movimento pequeno (Ç, Sim, Não, Oi, Tchau...): a mão parada dá 0,1 a 0,4 e o
#     sinal certo dá 0,3 a 0,8 -> mínimo 0,45 (Não, que é só o indicador balançando: 0,25);
#   - letras de movimento grande (J, K, X, Z) e o H: com a mão parada o MediaPipe "treme"
#     mais nos dedos dobrados (X parado chega a 0,7), e o sinal certo passa de 1,0 -> 0,9.
MOVIMENTO_MINIMO_PADRAO = 0.45
MOVIMENTO_MINIMO_POR_SINAL = {"Não": 0.25, "H": 0.7, "J": 0.9, "K": 0.9, "X": 0.9, "Z": 0.9}


def movimento_minimo(sinal):
    return MOVIMENTO_MINIMO_POR_SINAL.get(sinal, MOVIMENTO_MINIMO_PADRAO)


# Letra B: a palma aberta com o polegar DOBRADO sobre a palma. Sem essa regra, a palma
# aberta comum (polegar para fora) virava B. Distância da ponta do polegar (ponto 4) até a
# base do dedo médio (ponto 9), em "tamanhos de mão": nas fotos de B da base fica abaixo de
# 0,14 em 90% dos casos; na palma aberta (vídeos de Tchau) fica acima de 0,23 em 90%.
POLEGAR_B_MAXIMO = 0.2


def polegar_dobrado(caracteristicas):
    pontos = np.asarray(caracteristicas, dtype=np.float32).reshape(21, 3)
    return float(np.linalg.norm(pontos[4, :2] - pontos[9, :2])) <= POLEGAR_B_MAXIMO


def quantidade_de_movimento(quadros):
    """Nota de movimento da sequência (1,0 = o mínimo para contar como sinal com movimento).
    Junta duas medidas, as duas suavizadas para o tremor da mão e do MediaPipe não contar:
      - deslocamento: o maior "tamanho do desenho" do pulso (largura ou altura), em tamanhos de mão;
      - formato: o quanto o formato da mão se afastou do formato mais comum na sequência
        (pega sinais que giram a mão ou mexem os dedos sem sair do lugar, como H e X).
    Devolve 0 se a mão apareceu em poucos quadros."""
    validos = [q for q in escolher_mao_na_sequencia(quadros) if q]
    if len(validos) < 3:
        return 0.0
    pontos = np.array([[[p["x"] * float(q.get("proporcao") or 1.0), p["y"]] for p in q["pontos"]]
                       for q in validos], dtype=np.float32)
    tamanho = float(np.median(np.max(np.linalg.norm(pontos - pontos[:, :1], axis=2), axis=1)))
    tamanho = max(tamanho, 1e-6)

    def suavizar(matriz):
        return np.array([matriz[max(0, i - 1):i + 2].mean(axis=0) for i in range(len(matriz))])

    pulso = suavizar(pontos[:, 0])
    deslocamento = float(np.max(pulso.max(axis=0) - pulso.min(axis=0)) / tamanho)
    formas = suavizar(np.array([pontos_para_caracteristicas(q["pontos"], q["lado"]).reshape(21, 3)[:, :2].flatten()
                                for q in validos]))
    formato = float(np.max(np.linalg.norm(formas - np.median(formas, axis=0), axis=1)))
    return max(deslocamento / ESCALA_DESLOCAMENTO, formato / ESCALA_FORMATO)


def sequencia_para_caracteristicas(quadros, so_mao=False):
    """
    Transforma uma sequência de quadros nas características do modelo de movimento.

    'quadros' é uma lista com um item por quadro do vídeo/câmera:
        {"lado": "Direita", "pontos": [21 x {x, y, z}], "proporcao": largura/altura,
         "corpo": [7 x [x, y, visibilidade]], "rosto": {"pontos": [6 x [x, y]], "expressao": [13]}}
    ou None quando a mão não apareceu naquele quadro (esses quadros são ignorados).
    "corpo" e "rosto" vêm do MediaPipe Pose e Face (veja DetectorDeMaos).

    O que entra no modelo:
      1. o FORMATO da mão em 8 instantes (mesma normalização da foto parada);
      2. o CAMINHO do pulso em 16 instantes: onde o pulso foi, em relação ao
         ponto de partida, medido em "tamanhos de mão", a velocidade desse caminho
         e alguns resumos (distância percorrida, deslocamento, tamanho do desenho);
      3. o CORPO e o ROSTO em 8 instantes: onde estão a mão, os braços e a cabeça em
         relação aos ombros (medido em "larguras de ombro", então não depende da
         distância da câmera), a distância da mão até o nariz, queixo, testa e boca,
         o giro/inclinação da cabeça e a expressão do rosto;
      4. quanto a mão e a cabeça andaram em "larguras de ombro".

    A mão esquerda é espelhada na horizontal, como na foto parada: quem usa a
    mão esquerda faz o sinal espelhado. Essa MESMA função é usada no treino e no app.

    Com so_mao=True devolve só os itens 1 e 2 (não precisa de corpo nem de rosto).
    """
    validos = [q for q in escolher_mao_na_sequencia(quadros) if q]
    if len(validos) < MIN_QUADROS_COM_MAO:
        raise ValueError(
            f"A mão apareceu em só {len(validos)} quadros (mínimo {MIN_QUADROS_COM_MAO}). "
            "Deixe a mão bem visível durante o sinal todo."
        )

    formas, pulsos, tamanhos = [], [], []
    corpos, rostos, validos_corpo, validos_rosto, palmas, narizes = [], [], [], [], [], []
    for quadro in validos:
        pontos = np.array([[p["x"], p["y"]] for p in quadro["pontos"]], dtype=np.float32)
        proporcao = float(quadro.get("proporcao") or 1.0)
        lado = quadro["lado"]
        espelho = -1.0 if lado == "Esquerda" else 1.0

        formas.append(pontos_para_caracteristicas(quadro["pontos"], lado))

        # x e y são frações da largura e da altura: a proporção iguala as duas escalas
        pontos[:, 0] *= proporcao
        pulso = pontos[0].copy()
        if lado == "Esquerda":
            pulso[0] = -pulso[0]
        pulsos.append(pulso)

        tamanhos.append(float(np.max(np.linalg.norm(pontos - pontos[0], axis=1))))

        if so_mao:
            continue
        corpo = _corpo_do_quadro(quadro, proporcao, espelho)
        validos_corpo.append(corpo is not None)
        if corpo is None:
            corpos.append(np.zeros(2 * len(PONTOS_CORPO) + 4, dtype=np.float32))
            rostos.append(np.zeros(8 + 2 + len(EXPRESSOES), dtype=np.float32))
            validos_rosto.append(False)
            palmas.append(np.zeros(2, dtype=np.float32))
            narizes.append(np.zeros(2, dtype=np.float32))
        else:
            vetor_corpo, vetor_rosto, (palma, nariz) = corpo
            corpos.append(vetor_corpo)
            validos_rosto.append(vetor_rosto is not None)
            rostos.append(vetor_rosto if vetor_rosto is not None
                          else np.zeros(8 + 2 + len(EXPRESSOES), dtype=np.float32))
            palmas.append(palma)
            narizes.append(nariz)

    if so_mao:
        tamanho_da_mao = max(float(np.mean(tamanhos)), 1e-6)
        pulsos = np.array(pulsos, dtype=np.float32)
        caminho = _reamostrar((pulsos - pulsos[0]) / tamanho_da_mao, N_QUADROS_TRAJETORIA)
        passos = np.diff(caminho, axis=0)
        return np.concatenate([_reamostrar(formas, N_QUADROS_FORMA).flatten(), caminho.flatten(),
                               passos.flatten(), _resumo_do_caminho(caminho, passos)])

    if sum(validos_corpo) < MIN_QUADROS_COM_MAO:
        raise ValueError(
            "Não consegui ver seu corpo. Fique com o tronco e os dois ombros no enquadramento "
            "da câmera (da cintura pra cima), de frente, durante o sinal todo."
        )
    if sum(validos_rosto) < MIN_QUADROS_COM_MAO:
        raise ValueError(
            "Não consegui ver seu rosto. Deixe o rosto inteiro visível, de frente, com boa luz."
        )

    # quadros sem corpo/rosto herdam dos vizinhos; o rosto também é preenchido onde só o corpo apareceu
    corpos = _preencher_buracos(corpos, validos_corpo)
    rostos = _preencher_buracos(rostos, [a and b for a, b in zip(validos_corpo, validos_rosto)])
    palmas = _preencher_buracos(palmas, validos_corpo)
    narizes = _preencher_buracos(narizes, validos_corpo)

    tamanho_da_mao = max(float(np.mean(tamanhos)), 1e-6)
    pulsos = np.array(pulsos, dtype=np.float32)
    caminho = (pulsos - pulsos[0]) / tamanho_da_mao

    formas = _reamostrar(formas, N_QUADROS_FORMA)
    caminho = _reamostrar(caminho, N_QUADROS_TRAJETORIA)
    passos = np.diff(caminho, axis=0)
    corpo_e_rosto = _reamostrar(np.concatenate([corpos, rostos], axis=1), N_QUADROS_CORPO)

    resumo = _resumo_do_caminho(caminho, passos)

    # quanto a mão e a cabeça andaram em relação ao corpo (em larguras de ombro)
    movimento_corpo = np.array([
        np.linalg.norm(np.diff(palmas, axis=0), axis=1).sum(),   # caminho da palma no corpo
        np.linalg.norm(palmas[-1] - palmas[0]),                  # palma: início → fim
        narizes[:, 0].max() - narizes[:, 0].min(),               # cabeça: vai e volta pro lado (não)
        narizes[:, 1].max() - narizes[:, 1].min(),               # cabeça: vai e volta pra baixo (sim)
        np.linalg.norm(np.diff(narizes, axis=0), axis=1).sum(),  # caminho total da cabeça
        np.linalg.norm(narizes[-1] - narizes[0]),                # cabeça: início → fim
    ], dtype=np.float32)

    return np.concatenate([
        formas.flatten(), caminho.flatten(), passos.flatten(), resumo,
        corpo_e_rosto.flatten(), movimento_corpo,
    ])


class DetectorDeMaos:
    def __init__(self, caminho_modelo, caminho_classificador=None, caminho_movimento=None,
                 caminho_corpo=None, caminho_rosto=None, caminho_numeros=None, caminho_grupos=None):
        caminho_modelo = Path(caminho_modelo)
        if not caminho_modelo.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado em {caminho_modelo}. "
                "Coloque o arquivo hand_landmarker.task na pasta do projeto."
            )

        base_options = mp_python.BaseOptions(model_asset_path=str(caminho_modelo))

        # Modo IMAGE: cada quadro é analisado sozinho. É o mais simples pra um
        # servidor, porque não precisa controlar o tempo (timestamp) entre quadros.
        # Vale também pra vídeo: o vídeo é lido quadro a quadro e cada um é uma imagem.
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
        )
        self._detector = mp_vision.HandLandmarker.create_from_options(options)

        # O Flask pode atender mais de um pedido ao mesmo tempo; a trava garante
        # que o MediaPipe processe um quadro por vez.
        self._trava = threading.Lock()

        # Random Forest (opcional): se o arquivo não existir, o app funciona
        # normalmente, só não mostra a letra.
        self._classificador = None
        if caminho_classificador and Path(caminho_classificador).exists():
            self._classificador = joblib.load(caminho_classificador)

        # Random Forest dos NÚMEROS (opcional). Em LIBRAS os números 0 a 9 são sinais parados
        # (só o formato da mão), então usam as mesmas 63 características das letras, mas um
        # modelo separado, treinado com as mãos do especialista (treinar_modelo_numeros.py).
        # Fica separado porque alguns números têm o mesmo formato de letras (2 e V, por exemplo).
        self._numeros = None
        if caminho_numeros and Path(caminho_numeros).exists():
            self._numeros = joblib.load(caminho_numeros)

        # MediaPipe Pose (corpo) e Face (rosto): opcionais, só os sinais com movimento usam.
        # Cada um é um arquivo .task (veja o README pra baixar).
        self._corpo = self._rosto = None
        if caminho_corpo and Path(caminho_corpo).exists():
            self._corpo = mp_vision.PoseLandmarker.create_from_options(mp_vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(caminho_corpo)),
                running_mode=mp_vision.RunningMode.IMAGE,
                num_poses=1,
            ))
        if caminho_rosto and Path(caminho_rosto).exists():
            self._rosto = mp_vision.FaceLandmarker.create_from_options(mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(caminho_rosto)),
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                output_face_blendshapes=True,    # as expressões do rosto (sobrancelha, boca...)
            ))

        # Random Forest dos sinais com movimento (opcional, treinado com vídeos).
        # Só vale se o corpo e o rosto puderem ser lidos e se ele foi treinado com as mesmas
        # características que o código gera hoje.
        self._movimento = None
        if caminho_movimento and Path(caminho_movimento).exists():
            modelo = joblib.load(caminho_movimento)
            if not self.tem_corpo:
                print("Aviso: modelo_movimento.joblib existe, mas faltam pose_landmarker.task e/ou "
                      "face_landmarker.task em backend/. Sinais com movimento desligados.")
            elif getattr(modelo, "n_features_in_", None) != N_CARACTERISTICAS_MOVIMENTO:
                print("Aviso: modelo_movimento.joblib foi treinado numa versão antiga (sem corpo e rosto). "
                      "Rode de novo extrair_sequencias.py e treinar_modelo_movimento.py. "
                      "Sinais com movimento desligados.")
            else:
                self._movimento = modelo

        # Modelos por grupo (modelo_movimento_grupos.joblib), treinados pelo treinar_modelo_movimento.py:
        # {"Alfabeto": {"mao": RF}, "Saudações": {"completo": RF, "mao": RF}}
        self._grupos = None
        if self._movimento is not None and caminho_grupos and Path(caminho_grupos).exists():
            self._grupos = joblib.load(caminho_grupos)

    @property
    def tem_classificador(self):
        return self._classificador is not None

    @property
    def tem_classificador_numeros(self):
        return self._numeros is not None

    @property
    def numeros(self):
        """Números (sinais parados) que o modelo de números conhece, em ordem."""
        if self._numeros is None:
            return []
        return sorted(str(n) for n in self._numeros.classes_ if str(n) != SEM_SINAL)

    @property
    def tem_corpo(self):
        """True se os modelos de corpo (Pose) e rosto (Face) estão carregados."""
        return self._corpo is not None and self._rosto is not None

    @property
    def tem_classificador_movimento(self):
        return self._movimento is not None

    @property
    def sinais_movimento(self):
        """Nomes dos sinais com movimento que o modelo conhece (lista vazia se não treinou)."""
        if self._movimento is None:
            return []
        nomes = [str(sinal) for sinal in self._movimento.classes_]
        for modelos in (self._grupos or {}).values():      # modelos por grupo (ex.: letras só com a mão)
            for modelo in modelos.values():
                nomes += [str(sinal) for sinal in modelo.classes_ if str(sinal) not in nomes]
        return [nome for nome in nomes if nome != SEM_SINAL]     # a classe extra não é um sinal

    # ---------- imagem ----------

    def _analisar(self, frame, com_corpo=False):
        """
        Roda o MediaPipe num quadro (imagem BGR do OpenCV).
        Devolve (maos, corpo, rosto). corpo e rosto só são calculados com com_corpo=True
        (são mais lentos) e são None quando a pessoa não aparece:
          corpo = [[x, y, visibilidade] x 7]   (nariz, ombros, cotovelos, pulsos)
          rosto = {"pontos": [[x, y] x 6], "expressao": [13 números de 0 a 1]}
        """
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        with self._trava:
            resultado = self._detector.detect(mp_image)
            resultado_corpo = self._corpo.detect(mp_image) if com_corpo and self._corpo else None
            resultado_rosto = self._rosto.detect(mp_image) if com_corpo and self._rosto else None

        maos = []
        for i, hand_landmarks in enumerate(resultado.hand_landmarks):
            categoria = resultado.handedness[i][0]
            maos.append({
                "lado": LADOS.get(categoria.category_name, categoria.category_name),
                "confianca": round(categoria.score, 3),
                # x e y vão de 0 a 1 (proporção da largura/altura da imagem).
                # z é a profundidade relativa ao pulso (ponto 0).
                "pontos": [
                    {"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_landmarks
                ],
            })

        corpo = rosto = None
        if resultado_corpo is not None and resultado_corpo.pose_landmarks:
            pontos = resultado_corpo.pose_landmarks[0]
            corpo = [[round(pontos[i].x, 4), round(pontos[i].y, 4),
                      round(pontos[i].visibility or 0.0, 3)] for i in PONTOS_CORPO]

        if resultado_rosto is not None and resultado_rosto.face_landmarks:
            pontos = resultado_rosto.face_landmarks[0]
            notas = {c.category_name: c.score for c in resultado_rosto.face_blendshapes[0]} \
                if resultado_rosto.face_blendshapes else {}
            rosto = {
                "pontos": [[round(pontos[i].x, 4), round(pontos[i].y, 4)] for i in PONTOS_ROSTO],
                "expressao": [round(float(np.mean([notas.get(nome, 0.0) for nome in grupo])), 4)
                              for grupo in EXPRESSOES],
            }

        return maos, corpo, rosto

    def detectar(self, imagem_bytes, com_corpo=False, grupo="letras"):
        """Recebe os bytes de uma imagem e devolve um dicionário com as mãos.
        Com com_corpo=True devolve também "corpo" e "rosto" (null se a pessoa não aparece);
        a câmera usa isso nos sinais com movimento.
        grupo="numeros" usa o modelo dos números no lugar do modelo das letras."""
        buffer = np.frombuffer(imagem_bytes, dtype=np.uint8)
        frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Não foi possível ler a imagem enviada.")

        frame = recortar_4_3(frame)      # o site já manda 4:3; isso cobre outros clientes
        altura, largura = frame.shape[:2]
        maos, corpo, rosto = self._analisar(frame, com_corpo=com_corpo)

        # "proporcao" (largura/altura) é usada pelo modelo de movimento
        resposta = {"maos": maos, "proporcao": round(largura / altura, 4)}
        if com_corpo:
            resposta["corpo"] = corpo
            resposta["rosto"] = rosto

        # Letra: com duas mãos na imagem, vale a mão em que o modelo tem mais certeza
        # (antes era sempre a primeira mão, que às vezes era a mão parada)
        if maos and self._modelo_parado(grupo) is not None:
            previsoes = [self.prever_letra(m["pontos"], m["lado"], grupo) for m in maos]
            resposta.update(max(previsoes, key=lambda p: p["certeza"]))

        return resposta

    def _modelo_parado(self, grupo):
        """Modelo dos sinais parados: o dos números ou o das letras."""
        return self._numeros if grupo == "numeros" else self._classificador

    def prever_letra(self, pontos, lado, grupo="letras"):
        """Sinal parado (letra ou número) de uma mão. A chave continua "letra" pra não
        mudar o resto do sistema."""
        modelo = self._modelo_parado(grupo)
        caracteristicas = pontos_para_caracteristicas(pontos, lado).reshape(1, -1)
        probabilidades = modelo.predict_proba(caracteristicas)[0]
        indice = int(np.argmax(probabilidades))
        letra = str(modelo.classes_[indice])
        certeza = round(float(probabilidades[indice]), 3)
        if letra == "B" and grupo == "letras" and not polegar_dobrado(caracteristicas[0]):
            certeza = 0.0      # palma aberta com o polegar para fora não é B
        return {"letra": letra, "certeza": certeza}

    # ---------- vídeo ----------

    def ler_video(self, caminho, espelhar=True, com_corpo=True):
        if com_corpo and not self.tem_corpo:
            raise ValueError(
                "Faltam os modelos de corpo e rosto (pose_landmarker.task e face_landmarker.task "
                "na pasta backend). Veja o README."
            )
        quadros = self._ler_video(caminho, espelhar, com_corpo=com_corpo)
        if com_corpo:
            # sinal com movimento: com duas mãos na imagem, fica a que mais se mexe
            return escolher_mao_na_sequencia(quadros)
        # letra parada: cada quadro mantém as duas mãos e vota com a de maior certeza
        # (prever_letra_em_quadros), porque numa letra parada as duas mãos ficam quietas
        return quadros

    def _ler_video(self, caminho, espelhar, com_corpo=True):
        """
        Lê um arquivo de vídeo e devolve uma lista com um item por quadro analisado:
        {"maos": [{"lado", "pontos"}, ...], "proporcao", "corpo", "rosto"} com TODAS as mãos
        encontradas (e o corpo e o rosto da pessoa), ou None se não achou mão.
        Quadros mais largos que 4:3 são recortados no centro, igual à câmera do site.

        São analisados N_AMOSTRAS_VIDEO quadros espalhados do começo ao fim
        (não precisa analisar todos: o modelo estica/encolhe a sequência mesmo).

        espelhar=True vira cada quadro na horizontal, igual o praticar.js faz com a
        câmera. Assim vídeo gravado e câmera ao vivo ficam no mesmo "mundo" (e o MediaPipe
        acerta se a mão é esquerda ou direita). Use True pra vídeos normais de celular.
        """
        captura = cv2.VideoCapture(str(caminho))
        if not captura.isOpened():
            raise ValueError("Não foi possível abrir o vídeo. Use MP4, MOV, AVI, WEBM ou MKV.")

        try:
            total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total <= 0:
                # alguns formatos (ex.: webm gravado pelo navegador) não informam o tamanho:
                # conta passando pelo vídeo (grab não decodifica, é rápido)
                while captura.grab() and total < LIMITE_QUADROS_VIDEO + 1:
                    total += 1
                captura.release()
                captura = cv2.VideoCapture(str(caminho))

            if total <= 0:
                raise ValueError("O vídeo está vazio.")
            if total > LIMITE_QUADROS_VIDEO:
                raise ValueError("O vídeo é longo demais. Envie um vídeo de até 3 minutos.")

            quantidade = min(total, N_AMOSTRAS_VIDEO)
            escolhidos = set(np.linspace(0, total - 1, quantidade).round().astype(int).tolist())
            ultimo = max(escolhidos)

            quadros = []
            for numero in range(ultimo + 1):
                if not captura.grab():
                    break
                if numero not in escolhidos:
                    continue

                ok, frame = captura.retrieve()
                if not ok or frame is None:
                    quadros.append(None)
                    continue

                altura, largura = frame.shape[:2]
                if largura > LARGURA_MAXIMA_VIDEO:
                    escala = LARGURA_MAXIMA_VIDEO / largura
                    frame = cv2.resize(frame, (LARGURA_MAXIMA_VIDEO, round(altura * escala)))
                    altura, largura = frame.shape[:2]
                if espelhar:
                    frame = cv2.flip(frame, 1)
                frame = recortar_4_3(frame)          # igual à câmera do site
                altura, largura = frame.shape[:2]

                maos, corpo, rosto = self._analisar(frame, com_corpo=com_corpo)
                if maos:
                    quadros.append({
                        "maos": [{"lado": m["lado"], "pontos": m["pontos"]} for m in maos],
                        "proporcao": largura / altura,
                        "corpo": corpo,
                        "rosto": rosto,
                    })
                else:
                    quadros.append(None)
        finally:
            captura.release()

        if not quadros:
            raise ValueError("Não foi possível ler nenhum quadro do vídeo.")
        # cada quadro guarda TODAS as mãos; quem chama escolhe (veja ler_video)
        return quadros

    def ler_video_bytes(self, video_bytes, extensao=".mp4", espelhar=True, com_corpo=True):
        """Igual ao ler_video, mas recebe os bytes (upload). O OpenCV só lê de arquivo,
        então os bytes vão pra um arquivo temporário que é apagado no final."""
        if extensao not in EXTENSOES_VIDEO:
            extensao = ".mp4"

        descritor, caminho = tempfile.mkstemp(suffix=extensao)
        try:
            with os.fdopen(descritor, "wb") as arquivo:
                arquivo.write(video_bytes)
            return self.ler_video(caminho, espelhar=espelhar, com_corpo=com_corpo)
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass

    # ---------- sinais com movimento ----------

    def prever_movimento(self, quadros, alvo=None):
        """Diz qual sinal com movimento foi feito numa sequência de quadros.
        Com 'alvo' (o sinal que a pessoa escolheu na tela), usa o modelo do grupo dele:
        letras só com a mão; saudações com corpo e rosto, ou só com a mão se eles não aparecem."""
        if self._movimento is None:
            raise RuntimeError("Modelo de movimento não carregado.")

        if self._grupos and alvo in self.sinais_movimento:
            # Sinal com movimento precisa de movimento: mão parada (ou só tremendo) não vale,
            # mesmo que o formato da mão seja parecido (ex.: formato do I sem desenhar o J).
            movimento = quantidade_de_movimento(quadros)
            if movimento < movimento_minimo(alvo):
                if sum(1 for q in escolher_mao_na_sequencia(quadros) if q) < MIN_QUADROS_COM_MAO:
                    sequencia_para_caracteristicas(quadros, so_mao=True)   # erro "a mão apareceu em só..."
                return {"sinal": SEM_SINAL, "certeza": 0.0, "modo": "sem_movimento",
                        "semMovimento": True, "movimento": round(movimento, 2)}
            modelos = self._grupos.get(grupo_do_movimento(alvo), {})
            modelo, modo, caracteristicas = None, None, None
            if "completo" in modelos:
                try:
                    caracteristicas = sequencia_para_caracteristicas(quadros)
                    modelo, modo = modelos["completo"], "mao_corpo_rosto"
                except ValueError as problema:
                    if "mão apareceu" in str(problema):     # sem mão não tem o que fazer
                        raise
            if modelo is None and "mao" in modelos:
                caracteristicas = sequencia_para_caracteristicas(quadros, so_mao=True)
                modelo, modo = modelos["mao"], "mao"
            if modelo is not None:
                probabilidades = modelo.predict_proba(caracteristicas.reshape(1, -1))[0]
                indice = int(np.argmax(probabilidades))
                return {"sinal": str(modelo.classes_[indice]),
                        "certeza": round(float(probabilidades[indice]), 3), "modo": modo,
                        "movimento": round(movimento, 2)}

        if self._grupos:
            # sem alvo: cada grupo dá o seu palpite só com a mão e vale o mais certo
            caracteristicas = sequencia_para_caracteristicas(quadros, so_mao=True).reshape(1, -1)
            palpites = []
            for modelos in self._grupos.values():
                if "mao" in modelos:
                    probabilidades = modelos["mao"].predict_proba(caracteristicas)[0]
                    indice = int(np.argmax(probabilidades))
                    palpites.append({"sinal": str(modelos["mao"].classes_[indice]),
                                     "certeza": round(float(probabilidades[indice]), 3), "modo": "mao"})
            if palpites:
                return max(palpites, key=lambda p: p["certeza"])

        caracteristicas = sequencia_para_caracteristicas(quadros).reshape(1, -1)
        probabilidades = self._movimento.predict_proba(caracteristicas)[0]
        indice = int(np.argmax(probabilidades))
        return {
            "sinal": str(self._movimento.classes_[indice]),
            "certeza": round(float(probabilidades[indice]), 3),
            "modo": "mao_corpo_rosto",
        }

    def prever_letra_em_quadros(self, quadros, grupo="letras"):
        """
        Pra vídeo de uma letra PARADA (A, B, C...): cada quadro vota numa letra e
        vence a mais votada. A certeza é a certeza média dessa letra vezes a
        fração de quadros que votaram nela. Devolve None se não achou mão.
        """
        if self._modelo_parado(grupo) is None:
            return None

        votos = []
        for q in quadros:
            if not q:
                continue
            maos = q["maos"] if "maos" in q else [q]
            previsoes = [self.prever_letra(m["pontos"], m["lado"], grupo) for m in maos]
            votos.append(max(previsoes, key=lambda p: p["certeza"]))
        if not votos:
            return None

        letra, quantidade = Counter(v["letra"] for v in votos).most_common(1)[0]
        media = float(np.mean([v["certeza"] for v in votos if v["letra"] == letra]))
        return {
            "letra": letra,
            "certeza": round(media * quantidade / len(votos), 3),
            "quadros": quantidade,
        }

    def fechar(self):
        self._detector.close()
        if self._corpo:
            self._corpo.close()
        if self._rosto:
            self._rosto.close()
