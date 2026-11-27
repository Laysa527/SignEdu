"""
Configuração dos testes automáticos do SignEdu (pytest).

Os testes usam um banco SQLite temporário (não mexem no MySQL de verdade) e os modelos que
estão na pasta backend. Como rodar, na pasta do projeto:
    pip install pytest
    python -m pytest -v
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

PASTA_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(PASTA_BACKEND))

_banco_temporario = Path(tempfile.mkdtemp()) / "signedu_teste.db"
os.environ["SIGNEDU_DATABASE_URL"] = f"sqlite:///{_banco_temporario}"
os.environ.setdefault("SECRET_KEY", "chave-so-para-os-testes")

TEM_MODELOS_MEDIAPIPE = all((PASTA_BACKEND / f).exists() for f in
                            ("hand_landmarker.task", "pose_landmarker.task", "face_landmarker.task"))
precisa_mediapipe = pytest.mark.skipif(not TEM_MODELOS_MEDIAPIPE,
                                       reason="faltam os arquivos .task do MediaPipe na pasta backend")


@pytest.fixture(scope="session")
def app_signedu():
    import app as modulo_app
    import banco
    modulo_app.app.config.update(TESTING=True)
    with modulo_app.app.app_context():
        banco.db.create_all()
        banco.semear_alfabeto()
        banco.semear_sinais_movimento(modulo_app.detector.sinais_movimento)
        banco.semear_numeros(modulo_app.detector.numeros)
    return modulo_app


@pytest.fixture()
def cliente(app_signedu):
    app_signedu._historico_taxa.clear()          # zera o limite de tentativas entre os testes
    return app_signedu.app.test_client()
