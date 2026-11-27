"""Testes das funções de reconhecimento (backend/detector_maos.py), sem câmera."""
import numpy as np
import pytest

import detector_maos as d


def mao(cx, cy, lado="Direita", escala=0.05, giro=0.0):
    """Uma mão falsa com 21 pontos em volta de (cx, cy)."""
    pontos = []
    for i in range(21):
        ang = 2 * np.pi * i / 21 + giro
        pontos.append({"x": cx + escala * np.cos(ang), "y": cy + escala * np.sin(ang), "z": 0.01 * i})
    pontos[0] = {"x": cx, "y": cy + escala * 1.2, "z": 0.0}      # pulso
    return {"lado": lado, "pontos": pontos}


def test_caracteristicas_da_mao_tem_63_valores_e_pulso_na_origem():
    c = d.pontos_para_caracteristicas(mao(0.5, 0.5)["pontos"], "Direita")
    assert c.shape == (63,)
    assert np.allclose(c[:3], 0.0)                     # pulso transladado para a origem
    xy = c.reshape(21, 3)[:, :2]
    assert np.isclose(np.linalg.norm(xy, axis=1).max(), 1.0, atol=1e-5)   # maior distância até o pulso = 1


def test_mao_esquerda_e_espelhada():
    pts = mao(0.5, 0.5)["pontos"]
    direita = d.pontos_para_caracteristicas(pts, "Direita").reshape(21, 3)
    esquerda = d.pontos_para_caracteristicas(pts, "Esquerda").reshape(21, 3)
    assert np.allclose(direita[:, 0], -esquerda[:, 0])
    assert np.allclose(direita[:, 1:], esquerda[:, 1:])


def test_caracteristicas_nao_dependem_do_tamanho_nem_da_posicao():
    a = d.pontos_para_caracteristicas(mao(0.3, 0.4, escala=0.05)["pontos"], "Direita")
    b = d.pontos_para_caracteristicas(mao(0.7, 0.6, escala=0.10)["pontos"], "Direita")
    assert np.allclose(a.reshape(21, 3)[:, :2], b.reshape(21, 3)[:, :2], atol=1e-5)


@pytest.mark.parametrize("largura,altura,esperado", [
    (1280, 720, (720, 960)),     # 16:9 vira 4:3
    (640, 480, (480, 640)),      # 4:3 fica igual
    (720, 1280, (1280, 720)),    # celular em pé fica igual
])
def test_recorte_4_3(largura, altura, esperado):
    quadro = np.zeros((altura, largura, 3), dtype=np.uint8)
    assert d.recortar_4_3(quadro).shape[:2] == esperado


def _sequencia_com_duas_maos(n=30):
    quadros = []
    for t in range(n):
        parada = mao(0.40, 0.85, "Esquerda")                                   # mão parada, embaixo
        sinal = mao(0.55 + 0.08 * np.sin(t / 4), 0.40 + 0.002 * t, "Direita", giro=t / 8)
        maos = [parada, sinal] if t % 2 else [sinal, parada]                   # ordem muda
        quadros.append({"maos": maos, "proporcao": 4 / 3, "corpo": None, "rosto": None})
    return quadros


def test_escolhe_a_mao_que_sinaliza_e_nao_a_parada():
    escolhidos = d.escolher_mao_na_sequencia(_sequencia_com_duas_maos())
    assert all(q is not None and q["lado"] == "Direita" for q in escolhidos)
    assert all(q["pontos"][0]["y"] < 0.6 for q in escolhidos)                 # a mão de cima


def test_lado_fica_igual_na_sequencia_inteira():
    quadros = _sequencia_com_duas_maos()
    quadros[5]["maos"][0 if 5 % 2 == 0 else 1]["lado"] = "Esquerda"           # MediaPipe "troca" o lado
    escolhidos = d.escolher_mao_na_sequencia(quadros)
    assert {q["lado"] for q in escolhidos} == {"Direita"}


def test_formato_antigo_de_uma_mao_continua_aceito():
    antigo = [{"lado": "Direita", "pontos": mao(0.5, 0.5)["pontos"], "proporcao": 1.33} for _ in range(3)]
    assert d.escolher_mao_na_sequencia(antigo) is antigo


def test_poucos_quadros_com_mao_sao_recusados():
    with pytest.raises(ValueError):
        d.sequencia_para_caracteristicas([None] * 10 + [{"lado": "Direita", "pontos": mao(0.5, 0.5)["pontos"],
                                                         "proporcao": 1.33}] * 3)


def test_caracteristicas_so_da_mao_sao_o_comeco_do_vetor_completo():
    """O modelo "só mão" usa exatamente o começo do vetor do modelo completo."""
    import math
    quadros = []
    for i in range(12):
        dx = 0.02 * math.sin(i / 2)
        pontos = [{"x": 0.5 + dx + 0.01 * (k % 5), "y": 0.4 + 0.01 * (k // 5), "z": 0.0} for k in range(21)]
        corpo = [[0.5, 0.2, 1.0], [0.6, 0.45, 1.0], [0.4, 0.45, 1.0], [0.65, 0.7, 1.0], [0.35, 0.7, 1.0],
                 [0.5 + dx, 0.42, 1.0], [0.35, 0.9, 1.0]]
        rosto = {"pontos": [[0.5, 0.2], [0.5, 0.25], [0.5, 0.12], [0.5, 0.22], [0.47, 0.18], [0.53, 0.18]],
                 "expressao": [0.0] * 13}
        quadros.append({"lado": "Direita", "pontos": pontos, "proporcao": 4 / 3, "corpo": corpo, "rosto": rosto})
    completo = d.sequencia_para_caracteristicas(quadros)
    so_mao = d.sequencia_para_caracteristicas(quadros, so_mao=True)
    assert len(so_mao) == d.N_CARACTERISTICAS_MAO
    assert np.allclose(completo[:d.N_CARACTERISTICAS_MAO], so_mao, atol=1e-5)
    sem_corpo = [{k: v for k, v in q.items() if k not in ("corpo", "rosto")} for q in quadros]
    assert np.allclose(d.sequencia_para_caracteristicas(sem_corpo, so_mao=True), so_mao)


def test_grupo_do_movimento():
    assert d.grupo_do_movimento("Ç") == "Alfabeto"
    assert d.grupo_do_movimento("Z") == "Alfabeto"
    assert d.grupo_do_movimento("Bom dia") == "Saudações"


def test_aumento_mesma_camera_nao_muda_nada():
    import aumento_dados
    quadro = {"lado": "Direita", "proporcao": 4 / 3,
              "pontos": [{"x": 0.5 + i * 0.01, "y": 0.5 - i * 0.01, "z": 0.0} for i in range(21)],
              "corpo": [[0.5, 0.4, 1.0]] * 7, "rosto": {"pontos": [[0.5, 0.3]] * 6, "expressao": [0.0] * 13}}
    igual = aumento_dados.mudar_camera([quadro, None], 4 / 3, 0.0)
    assert igual[1] is None
    for antes, depois in zip(quadro["pontos"], igual[0]["pontos"]):
        assert abs(antes["x"] - depois["x"]) < 1e-9 and abs(antes["y"] - depois["y"]) < 1e-9
    # câmera 16:9: a mão fica mais estreita em fração da largura, a altura não muda
    largo = aumento_dados.mudar_camera([quadro], 16 / 9, 0.0)[0]
    assert largo["proporcao"] == 16 / 9
    assert abs(largo["pontos"][20]["y"] - quadro["pontos"][20]["y"]) < 1e-9


def test_janelas_tem_de_2_a_3_segundos():
    import aumento_dados
    quadros = list(range(52))           # 4 s a 13 quadros por segundo
    pedacos = aumento_dados.janelas(quadros, 13)
    assert pedacos and all(26 <= len(p) <= 39 for p in pedacos)


def _mao_parada(n=30, tremor=0.003, semente=0):
    gerador = np.random.default_rng(semente)
    base = [(0.5 + 0.02 * (i % 5), 0.6 - 0.03 * (i // 5)) for i in range(21)]
    return [{"lado": "Direita", "proporcao": 4 / 3,
             "pontos": [{"x": x + gerador.normal(0, tremor), "y": y + gerador.normal(0, tremor), "z": 0.0}
                        for x, y in base]} for _ in range(n)]


def test_mao_parada_tremendo_nao_conta_como_movimento():
    assert d.quantidade_de_movimento(_mao_parada()) < d.MOVIMENTO_MINIMO_PADRAO


def test_mao_que_anda_conta_como_movimento():
    quadros = _mao_parada(tremor=0.0)
    for i, quadro in enumerate(quadros):
        for ponto in quadro["pontos"]:
            ponto["x"] += 0.01 * i          # anda uns 2 tamanhos de mão para o lado
    assert d.quantidade_de_movimento(quadros) >= d.MOVIMENTO_MINIMO


def test_letra_b_precisa_do_polegar_dobrado():
    pontos = np.zeros((21, 3), dtype=np.float32)
    pontos[9, :2] = (0.0, -0.5)
    pontos[4, :2] = (0.0, -0.45)            # polegar encostado na base do dedo médio
    assert d.polegar_dobrado(pontos.flatten())
    pontos[4, :2] = (0.45, -0.3)            # polegar para fora (palma aberta)
    assert not d.polegar_dobrado(pontos.flatten())
