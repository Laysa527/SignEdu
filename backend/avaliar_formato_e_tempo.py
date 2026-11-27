"""
Teste do modelo das letras estáticas com as imagens de TESTE da cnn-libras colocadas em quadros
de proporções diferentes (como chegariam de webcams diferentes), e do tempo de processamento
de cada quadro no servidor (DetectorDeMaos.detectar, o mesmo usado pela rota /api/maos/detectar).

Cada imagem (64x64) é ampliada para 480x480 e colocada no centro de um quadro:
  - 4:3  (640x480): proporção das imagens de treino;
  - 16:9 (854x480): proporção comum em webcams de notebook.
Desde a versão 2.4 o servidor recorta o centro 4:3 de quadros mais largos (recortar_4_3), e o
site faz o mesmo antes de enviar. Com --sem-recorte o teste roda sem esse recorte, para comparar.

Como rodar (precisa da pasta dataset/test da cnn-libras dentro de backend/):
    python avaliar_formato_e_tempo.py
    python avaliar_formato_e_tempo.py --sem-recorte
O tempo depende do computador: anote em qual máquina o teste foi feito.
"""
import argparse
import platform
import time
from pathlib import Path

import cv2
import numpy as np

import detector_maos
from detector_maos import DetectorDeMaos

PASTA = Path(__file__).resolve().parent


def no_quadro(imagem, largura):
    grande = cv2.resize(imagem, (480, 480))
    sobra = largura - 480
    return cv2.copyMakeBorder(grande, 0, 0, sobra // 2, sobra - sobra // 2, cv2.BORDER_CONSTANT, value=(0, 0, 0))


def main():
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--pasta", default=str(PASTA / "dataset" / "test"))
    argumentos.add_argument("--sem-recorte", action="store_true")
    opcoes = argumentos.parse_args()
    if opcoes.sem_recorte:
        detector_maos.recortar_4_3 = lambda quadro: quadro

    detector = DetectorDeMaos(PASTA / "hand_landmarker.task", PASTA / "modelo_letras.joblib")
    fotos = sorted(Path(opcoes.pasta).glob("*/*.png"))
    print(f"{len(fotos)} imagens de teste | {platform.processor() or platform.machine()} | "
          f"recorte 4:3 {'desligado' if opcoes.sem_recorte else 'ligado'}")

    for nome, largura in (("4:3 (640x480)", 640), ("16:9 (854x480)", 854)):
        certos = com_mao = 0
        tempos = []
        for foto in fotos:
            quadro = no_quadro(cv2.imread(str(foto)), largura)
            dados = cv2.imencode(".jpg", quadro, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
            inicio = time.perf_counter()
            resposta = detector.detectar(dados)
            tempos.append((time.perf_counter() - inicio) * 1000)
            if resposta["maos"]:
                com_mao += 1
                certos += resposta.get("letra") == foto.parent.name
        print(f"  {nome:15} acerto {certos / max(com_mao, 1) * 100:5.1f}% ({certos}/{com_mao} com mão detectada) | "
              f"tempo por quadro: mediana {np.median(tempos):.0f} ms, 95% em até {np.percentile(tempos, 95):.0f} ms")
    detector.fechar()


if __name__ == "__main__":
    main()
