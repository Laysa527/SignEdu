"""
Aumento de dados ("data augmentation") para os modelos de sinais com movimento.

Por que existe: os vídeos de treino são todos do Wallyson, cortados do começo ao fim do
sinal e gravados numa câmera 4:3 deitada. Ao vivo o site é diferente:
  - a câmera manda "janelas" de 2 a 3 segundos que pegam só um pedaço do que foi feito
    (às vezes o começo, às vezes o meio do sinal);
  - a câmera pode ser 16:9 (notebook) ou estar em pé (celular, 3:4), o que estica ou
    achata a mão nos números que o modelo recebe;
  - cada pessoa inclina a mão um pouco diferente.
Para o modelo aprender a lidar com isso, cada vídeo de treino vira várias versões:
janelas de 2, 2,5 e 3 s e "câmeras" simuladas com outro formato e a mão um pouco girada.
Nada aqui inventa sinais novos: são os mesmos movimentos do especialista, só vistos
de outro jeito. Os testes que mostram o ganho estão em avaliar_aumento.py.
"""
import math

import numpy as np

# Câmeras simuladas no treino: (proporção largura/altura, giro da mão em radianos)
CAMERAS_TREINO = (
    (16 / 9, 0.15),    # notebook, mão um pouco girada para um lado
    (3 / 4, -0.15),    # celular em pé, mão girada para o outro lado
    (16 / 9, -0.20),
)
DURACOES_JANELA = (2.0, 2.5, 3.0)   # segundos (o site olha os últimos 3 s, mínimo 2 s)


def mudar_camera(quadros, nova_proporcao, giro=0.0):
    """Mostra a mesma sequência como se viesse de uma câmera com outra proporção
    (largura/altura) e com a mão girada 'giro' radianos em volta do pulso.
    Funciona nos dois formatos de quadro: com "maos" (vários) ou com "pontos" (uma mão)."""
    c, s = math.cos(giro), math.sin(giro)

    def mao_nova(pontos, r):
        convertidos = [(p["x"] * r, p["y"], p["z"] * r) for p in pontos]
        x0, y0, _ = convertidos[0]
        saida = []
        for x, y, z in convertidos:
            dx, dy = x - x0, y - y0
            saida.append({"x": (x0 + c * dx - s * dy) / nova_proporcao,
                          "y": y0 + s * dx + c * dy,
                          "z": z / nova_proporcao})
        return saida

    novos = []
    for quadro in quadros:
        if not quadro:
            novos.append(quadro)
            continue
        r = float(quadro.get("proporcao") or 1.0)
        escala = r / nova_proporcao        # x em fração da largura: muda com a câmera
        novo = dict(quadro)
        novo["proporcao"] = nova_proporcao
        if "maos" in quadro:
            novo["maos"] = [dict(m, pontos=mao_nova(m["pontos"], r)) for m in quadro["maos"]]
        if "pontos" in quadro:
            novo["pontos"] = mao_nova(quadro["pontos"], r)
        if quadro.get("corpo"):
            novo["corpo"] = [[p[0] * escala, p[1]] + list(p[2:]) for p in quadro["corpo"]]
        if quadro.get("rosto") and quadro["rosto"].get("pontos"):
            novo["rosto"] = dict(quadro["rosto"],
                                 pontos=[[p[0] * escala, p[1]] for p in quadro["rosto"]["pontos"]])
        novos.append(novo)
    return novos


def janelas(quadros, quadros_por_segundo, passo=3):
    """Pedaços contínuos de 2, 2,5 e 3 s da sequência (como a câmera ao vivo enxerga)."""
    saida = []
    for duracao in DURACOES_JANELA:
        tamanho = int(round(duracao * quadros_por_segundo))
        if tamanho >= len(quadros):
            continue
        for inicio in range(0, len(quadros) - tamanho + 1, passo):
            saida.append(quadros[inicio:inicio + tamanho])
    return saida


def versoes_para_treino(quadros, quadros_por_segundo):
    """O vídeo inteiro + janelas, na câmera original e nas câmeras simuladas."""
    cameras = [quadros] + [mudar_camera(quadros, r, g) for r, g in CAMERAS_TREINO]
    saida = []
    for sequencia in cameras:
        saida.append(sequencia)
        saida.extend(janelas(sequencia, quadros_por_segundo))
    return saida


# ---------------------------------------------------------------------------------------
# Exemplos de "Nenhum sinal" (a classe extra dos modelos de movimento)
#
# Sem essa classe o modelo era obrigado a escolher um dos sinais do grupo, então qualquer
# coisa (palma parada, mão tremendo, dedo levantado sem mexer) virava "o sinal mais
# parecido". Aqui criamos sequências que NÃO são sinal nenhum, a partir dos próprios vídeos:
#   - parado: um formato de mão qualquer, segurado, com tremor (a mão de verdade treme
#     um pouco e o MediaPipe também oscila);
#   - sobe e para: a mão sobe até a posição e fica parada (o começo de um vídeo e depois
#     o quadro congelado), por exemplo fazer o formato do I e não desenhar o J;
#   - sacode: um formato de mão de OUTRO grupo balançando para os lados ou para cima e
#     para baixo (ex.: palma aberta sacudindo nas letras).
# ---------------------------------------------------------------------------------------

def _com_tremor(quadro, deslocamentos, gerador, tremor):
    """Repete 'quadro' uma vez para cada deslocamento (x, y) do pulso, com tremor nos pontos."""
    saida = []
    for dx, dy in deslocamentos:
        novo = dict(quadro)
        novo["pontos"] = [{"x": p["x"] + dx + gerador.normal(0, tremor),
                           "y": p["y"] + dy + gerador.normal(0, tremor),
                           "z": p["z"]} for p in quadro["pontos"]]
        saida.append(novo)
    return saida


def _tamanho_na_imagem(quadro):
    pontos = quadro["pontos"]
    return max(max(abs(p["x"] - pontos[0]["x"]) for p in pontos),
               max(abs(p["y"] - pontos[0]["y"]) for p in pontos), 1e-3)


def exemplos_sem_sinal(sequencias_do_grupo, sequencias_de_outros, quantidade, gerador,
                       quadros_por_segundo=13.0):
    """Gera 'quantidade' sequências de "Nenhum sinal" (listas de quadros, formato de uma mão).
    sequencias_do_grupo / sequencias_de_outros: listas de sequências (listas de quadros)."""
    todas = [s for s in sequencias_do_grupo + sequencias_de_outros if sum(1 for q in s if q) >= 6]
    outras = [s for s in sequencias_de_outros if sum(1 for q in s if q) >= 6] or todas
    saida = []
    for indice in range(quantidade):
        tipo = indice % 3
        tamanho = int(gerador.integers(int(2.0 * quadros_por_segundo), int(3.0 * quadros_por_segundo) + 1))
        tremor = float(gerador.uniform(0.001, 0.005))
        if tipo == 0:                                   # parado
            sequencia = todas[gerador.integers(len(todas))]
            quadros = [q for q in sequencia if q]
            quadro = quadros[gerador.integers(len(quadros))]
            deriva = np.cumsum(gerador.normal(0, 0.002, (tamanho, 2)), axis=0)
            saida.append(_com_tremor(quadro, deriva, gerador, tremor))
        elif tipo == 1:                                 # sobe e para
            sequencia = todas[gerador.integers(len(todas))]
            quadros = [q for q in sequencia if q]
            corte = int(gerador.integers(2, max(3, int(len(quadros) * 0.3))))
            subida = quadros[:corte]
            resto = max(tamanho - len(subida), int(quadros_por_segundo))
            deriva = np.cumsum(gerador.normal(0, 0.002, (resto, 2)), axis=0)
            saida.append(subida + _com_tremor(quadros[corte - 1], deriva, gerador, tremor))
        else:                                           # sacode (formato de outro grupo)
            sequencia = outras[gerador.integers(len(outras))]
            quadros = [q for q in sequencia if q]
            quadro = quadros[gerador.integers(len(quadros))]
            amplitude = float(gerador.uniform(0.2, 0.9)) * _tamanho_na_imagem(quadro)
            frequencia = float(gerador.uniform(1.5, 4.0))
            angulo = float(gerador.uniform(0, np.pi))
            t = np.arange(tamanho) / quadros_por_segundo
            onda = amplitude * np.sin(2 * np.pi * frequencia * t + gerador.uniform(0, 6.3))
            deslocamentos = np.stack([onda * np.cos(angulo), onda * np.sin(angulo)], axis=1)
            saida.append(_com_tremor(quadro, deslocamentos, gerador, tremor))
    return saida
