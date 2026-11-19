# -*- coding: utf-8 -*-
"""Abre o mestre-clipador: liga o motor, o servidor local e a janela do app."""
import os
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from banco import Banco  # noqa: E402
from motor import Motor  # noqa: E402
from servidor import criar_servidor  # noqa: E402


def pasta_dados():
    if os.environ.get("MC_DADOS"):
        p = Path(os.environ["MC_DADOS"])
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        p = Path(os.environ["LOCALAPPDATA"]) / "mestre-clipador"
    else:
        p = Path.home() / ".mestre-clipador"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main():
    dados = pasta_dados()
    banco = Banco(dados / "dados.db")
    motor = Motor(banco, dados)
    motor.iniciar()
    porta = int(os.environ.get("MC_PORTA", "0"))
    srv = criar_servidor(motor, porta)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    motor.log(f"App aberto em {url}")
    sem_janela = "--navegador" in sys.argv or os.environ.get("MC_SEM_JANELA")
    try:
        if sem_janela:
            raise ImportError
        import webview  # pywebview: janela propria do app
        webview.create_window("mestre-clipador", url, width=1320, height=860, min_size=(900, 640))
        webview.start()
    except Exception as ex:  # sem pywebview (ou sem WebView2): abre no navegador
        if not isinstance(ex, ImportError):
            motor.log(f"Janela própria indisponível ({ex}); abrindo no navegador.")
        if not os.environ.get("MC_SEM_JANELA"):
            webbrowser.open(url)
        print("Feche esta janela (ou aperte Ctrl+C) para desligar o mestre-clipador.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    motor.desligar()
    srv.shutdown()


if __name__ == "__main__":
    main()
