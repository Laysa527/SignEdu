"""Testes dos modelos treinados e do reconhecimento com um vídeo real de exemplo."""
from pathlib import Path

import joblib
import pytest

import detector_maos as d
from conftest import PASTA_BACKEND, precisa_mediapipe

LETRAS = set("A B C D E F G I L M N O P Q R S T U V W Y".split())
NUMEROS = {str(i) for i in range(10)}
SINAIS_MOVIMENTO = {"H", "J", "K", "X", "Z", "Ç",
                    "Oi", "Tchau", "Bom dia", "Boa tarde", "Boa noite", "Obrigado", "Por favor",
                    "Desculpa", "Tudo bem", "Sim", "Não", "Nome"}


def test_modelo_das_letras_conhece_as_21_letras():
    modelo = joblib.load(PASTA_BACKEND / "modelo_letras.joblib")
    assert set(map(str, modelo.classes_)) == LETRAS | {d.SEM_SINAL}   # + "Nenhum sinal"
    assert modelo.n_features_in_ == 63


def test_modelo_dos_numeros_conhece_0_a_9_como_sinais_parados():
    modelo = joblib.load(PASTA_BACKEND / "modelo_numeros.joblib")
    assert set(map(str, modelo.classes_)) == NUMEROS | {d.SEM_SINAL}  # + "Nenhum sinal"
    assert modelo.n_features_in_ == 63          # mesmas características das letras


def test_todo_numero_tem_foto_de_exemplo():
    pasta = PASTA_BACKEND.parent / "frontend" / "img" / "numeros"
    if not pasta.exists():
        pytest.skip("pasta frontend/img/numeros não está nesta cópia (ela não vai para o GitHub)")
    assert not [n for n in NUMEROS if not (pasta / f"{n}.jpg").exists()]


def test_modelos_de_movimento_por_grupo_conhecem_os_18_sinais():
    modelo = joblib.load(PASTA_BACKEND / "modelo_movimento.joblib")
    assert modelo.n_features_in_ == d.N_CARACTERISTICAS_MOVIMENTO == 904
    grupos = joblib.load(PASTA_BACKEND / "modelo_movimento_grupos.joblib")
    letras = {"H", "J", "K", "X", "Z", "Ç"}
    nenhum = {d.SEM_SINAL}      # classe extra "não é nenhum destes"
    assert set(map(str, grupos["Alfabeto"]["mao"].classes_)) == letras | nenhum
    assert set(map(str, grupos["Saudações"]["mao"].classes_)) == (SINAIS_MOVIMENTO - letras) | nenhum
    assert set(map(str, grupos["Saudações"]["completo"].classes_)) == (SINAIS_MOVIMENTO - letras) | nenhum
    assert grupos["Alfabeto"]["mao"].n_features_in_ == d.N_CARACTERISTICAS_MAO
    assert grupos["Saudações"]["completo"].n_features_in_ == d.N_CARACTERISTICAS_MOVIMENTO


def test_todo_sinal_com_movimento_tem_video_de_exemplo():
    pasta = PASTA_BACKEND.parent / "frontend" / "videos"
    if not pasta.exists():
        pytest.skip("pasta frontend/videos não está nesta cópia (ela não vai para o GitHub)")
    faltando = [s for s in SINAIS_MOVIMENTO if not (pasta / f"{s}.mp4").exists()]
    assert not faltando


@precisa_mediapipe
@pytest.mark.parametrize("sinal", ["Bom dia", "Nome", "Z"])
def test_reconhece_o_video_de_exemplo(sinal):
    video = PASTA_BACKEND.parent / "frontend" / "videos" / f"{sinal}.mp4"
    if not video.exists():
        pytest.skip("vídeo de exemplo não está nesta cópia")
    detector = d.DetectorDeMaos(PASTA_BACKEND / "hand_landmarker.task",
                                caminho_movimento=PASTA_BACKEND / "modelo_movimento.joblib",
                                caminho_grupos=PASTA_BACKEND / "modelo_movimento_grupos.joblib",
                                caminho_corpo=PASTA_BACKEND / "pose_landmarker.task",
                                caminho_rosto=PASTA_BACKEND / "face_landmarker.task")
    try:
        assert set(detector.sinais_movimento) == SINAIS_MOVIMENTO
        resultado = detector.prever_movimento(detector.ler_video(video), alvo=sinal)
    finally:
        detector.fechar()
    assert resultado["sinal"] == sinal
