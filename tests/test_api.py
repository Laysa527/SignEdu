"""Testes da API (backend/app.py e backend/banco.py) com um banco SQLite temporário."""
import itertools

import banco

_contador = itertools.count()


def novo_usuario(cliente, aceite=True):
    n = next(_contador)
    dados = {"nome": f"Teste {n}", "email": f"teste{n}@exemplo.com", "senha": "senha-segura-123"}
    if aceite is not None:
        dados["aceiteTermos"] = aceite
    return dados, cliente.post("/api/auth/cadastro", json=dados)


def test_cadastro_sem_aceitar_os_termos_e_recusado(cliente):
    _, resposta = novo_usuario(cliente, aceite=None)
    assert resposta.status_code == 422
    assert "Termos de Uso" in resposta.get_json()["erro"]
    _, resposta = novo_usuario(cliente, aceite=False)
    assert resposta.status_code == 422


def test_cadastro_com_aceite_cria_conta_e_guarda_a_data(cliente, app_signedu):
    dados, resposta = novo_usuario(cliente)
    assert resposta.status_code == 201
    with app_signedu.app.app_context():
        usuario = banco.Usuario.query.filter_by(email=dados["email"]).first()
        assert usuario.termos_aceitos_em is not None
        assert usuario.senha != dados["senha"]                     # senha guardada em hash


def test_email_repetido_e_recusado(cliente):
    dados, _ = novo_usuario(cliente)
    resposta = cliente.post("/api/auth/cadastro", json=dados)
    assert resposta.status_code == 409


def test_login_certo_e_errado(cliente):
    dados, _ = novo_usuario(cliente)
    cliente.post("/api/auth/logout")
    errado = cliente.post("/api/auth/login", json={"email": dados["email"], "senha": "outra-senha"})
    assert errado.status_code == 401
    certo = cliente.post("/api/auth/login", json={"email": dados["email"], "senha": dados["senha"]})
    assert certo.status_code == 200


def test_rotas_protegidas_exigem_login(app_signedu):
    cliente = app_signedu.app.test_client()
    for rota in ("/api/usuarios/me", "/api/usuarios/progresso", "/api/loja", "/api/sinais/movimento",
                 "/api/sinais/numeros"):
        assert cliente.get(rota).status_code == 401


def test_categorias_dos_sinais():
    assert banco.categoria_do_sinal("A") == "Alfabeto"
    assert banco.categoria_do_sinal("Ç") == "Alfabeto"
    assert banco.categoria_do_sinal("7") == "Números"
    assert banco.categoria_do_sinal("Bom dia") == "Saudações"


def test_lista_de_sinais_com_movimento_tem_categorias_e_videos(cliente):
    novo_usuario(cliente)
    dados = cliente.get("/api/sinais/movimento").get_json()
    assert dados["disponivel"] is True
    por_nome = {s["nome"]: s for s in dados["sinais"]}
    assert por_nome["Z"]["categoria"] == "Alfabeto"
    assert "3" not in por_nome                   # números agora são sinais parados
    assert por_nome["Obrigado"]["categoria"] == "Saudações"
    assert por_nome["Bom dia"]["video"] == "videos/Bom%20dia.mp4"


def test_lista_de_numeros_parados(cliente):
    novo_usuario(cliente)
    dados = cliente.get("/api/sinais/numeros").get_json()
    assert dados["disponivel"] is True
    assert [s["nome"] for s in dados["sinais"]] == [str(i) for i in range(10)]
    assert all(s["categoria"] == "Números" for s in dados["sinais"])


def test_movimento_recusa_quadros_invalidos(cliente):
    novo_usuario(cliente)
    resposta = cliente.post("/api/maos/movimento", json={"quadros": [{"maos": [{"lado": "Cima"}]}]})
    assert resposta.status_code == 422


def test_detectar_imagem_sem_mao(cliente):
    import cv2
    import numpy as np
    novo_usuario(cliente)
    _, jpeg = cv2.imencode(".jpg", np.full((480, 640, 3), 200, dtype=np.uint8))
    resposta = cliente.post("/api/maos/detectar",
                            data={"frame": (__import__("io").BytesIO(jpeg.tobytes()), "frame.jpg")},
                            content_type="multipart/form-data")
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["maos"] == [] and abs(corpo["proporcao"] - 4 / 3) < 0.01


def test_excluir_conta_apaga_o_usuario(cliente, app_signedu):
    dados, _ = novo_usuario(cliente)
    assert cliente.delete("/api/usuarios/me", json={"senhaAtual": "senha-errada"}).status_code == 403
    resposta = cliente.delete("/api/usuarios/me", json={"senhaAtual": dados["senha"]})
    assert resposta.status_code == 200
    with app_signedu.app.app_context():
        assert banco.Usuario.query.filter_by(email=dados["email"]).first() is None


def test_verificar_movimento_nao_salva_tentativa(cliente, app_signedu):
    """Reconhecimento automático: o modo "verificar" responde o sinal, mas não grava tentativa."""
    from pathlib import Path
    import pytest
    from conftest import TEM_MODELOS_MEDIAPIPE
    video = Path(__file__).resolve().parent.parent / "frontend" / "videos" / "Oi.mp4"
    if not (TEM_MODELOS_MEDIAPIPE and video.exists()):
        pytest.skip("precisa dos modelos do MediaPipe e do vídeo de exemplo")
    novo_usuario(cliente)
    quadros = app_signedu.detector.ler_video(video)
    sessao = cliente.post("/api/sessoes", json={"letra": "Oi"}).get_json()
    sessao_id = sessao.get("sessaoId") or sessao.get("id")
    with app_signedu.app.app_context():
        antes = banco.Resultado.query.count()
    resposta = cliente.post("/api/maos/movimento", json={"quadros": quadros, "verificar": True, "sessaoId": sessao_id})
    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert dados["sinal"] == "Oi"
    assert dados["resultado"] is None
    assert dados["certezaMinima"] == banco.CERTEZA_MINIMA_MOVIMENTO
    with app_signedu.app.app_context():
        assert banco.Resultado.query.count() == antes


def test_c_cedilha_e_c_sao_sinais_diferentes(app_signedu):
    """No MySQL, "Ç" e "C" eram comparados como iguais e o Ç abria a sessão da letra C."""
    with app_signedu.app.app_context():
        banco.semear_sinais_movimento(["Ç"])
        c, cedilha = banco.buscar_sinal("C"), banco.buscar_sinal("Ç")
        assert c is not None and cedilha is not None
        assert c.id != cedilha.id and cedilha.nome == "Ç"


def test_pontos_sinal_novo_e_repeticao_no_dia(cliente, app_signedu):
    """1º acerto do sinal: pontos cheios + bônus; repetir no mesmo dia vale pouco."""
    dados, _ = novo_usuario(cliente)
    resultados = []
    for _ in range(2):
        sessao = cliente.post("/api/sessoes", json={"letra": "B"}).get_json()
        with app_signedu.app.app_context():
            usuario = banco.Usuario.query.filter_by(email=dados["email"]).first()
            resultados.append(banco.registrar_tentativa(usuario, sessao["sessaoId"], "B", 0.99))
    assert resultados[0]["tipoPontos"] == "novo"
    assert resultados[0]["pontosGanhos"] == banco.PONTOS_POR_NIVEL_EXERCICIO[1] + banco.BONUS_SINAL_NOVO
    assert resultados[1]["tipoPontos"] == "repeticao"
    assert resultados[1]["pontosGanhos"] == banco.PONTOS_REPETICAO_NO_DIA
