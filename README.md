# 🎬 mestre-clipador — cortes automáticos de lives

**Criado por @kauan.ssw**

O **mestre-clipador** fica de olho numa live (YouTube, Twitch ou Kick), grava e acha sozinho os melhores momentos: gritos, risadas, explosões. Cada momento vira um **clipe vertical (9:16) com legenda automática** e é enviado para o seu **Telegram**, para você revisar e postar no TikTok, Reels ou Shorts.

> ⚠️ Ele **nunca posta sozinho**. Você sempre assiste e aprova antes, para não publicar spoiler, um momento fora de contexto ou conteúdo de quem não autorizou.

---

## 🆕 Versão app (v2): tudo dentro de uma janela

Agora o mestre-clipador também é um **aplicativo**: sem pastas, sem `config.ini`, sem janela preta.

**Jeito mais fácil:** baixe o instalador em [Releases](https://github.com/Kauan-berry/mestre-clipador/releases/latest) (`mestre-clipador-setup-*.exe`), abra e clique em Avançar. Já vem tudo junto (FFmpeg, yt-dlp, legenda): não precisa instalar Python. Se o Windows avisar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo** (o app não tem assinatura digital paga). Na primeira legenda ele baixa o modelo (uns 500 MB), então o primeiro clipe demora um pouco mais.

**Sem instalador (para quem mexe no código):** baixe o projeto, rode o **`APP_1_INSTALAR.bat`** e abra pelo atalho que ele cria.

O app tem 4 telas:
   - **Início:** dividido em **Lives**, **Vídeos** e **Streamers**. Cada streamer pode ter **vários canais** (YouTube, Twitch, Kick…). O botão **Clipar live** verifica em quais canais ele está ao vivo e você escolhe um (uma live por streamer de cada vez); se ninguém estiver ao vivo, o app espera a live começar. **Clipar vídeo** clipa vídeos já publicados numa fila separada, ao mesmo tempo que a live. Lives finalizadas e vídeos já clipados vão para grupos de **arquivados**, recolhidos.
   - **Galeria (Kanban):** cada momento chega como **prévia crua**. Você assiste e **aprova** ou **descarta**. Só o aprovado é emoldurado e vai pro Telegram.
   - **Ajustes:** um perfil por streamer — formato, moldura, câmera (marcada arrastando um retângulo na imagem da live), créditos, tamanho e quantidade de clipes. A prévia 9:16 muda na hora.
   - **Telegram:** 3 passos para conectar o bot, com teste de envio.

**Prazos da Galeria** (o app apaga sozinho):

| Coluna | Fica | Depois |
| --- | --- | --- |
| Clipados | 2 dias úteis | vai para Arquivados |
| Autorizados | 1 dia | apagado do PC (já está no Telegram) |
| Descartados | 1 hora (ou 2, nos Ajustes) | apagado |
| Arquivados | 1 semana | apagado |

Os dados do app ficam em `%LOCALAPPDATA%\mestre-clipador`. A versão antiga (com `.bat` e `config.ini`) continua abaixo e funcionando.

---

## ✨ O que ele faz

- 🔴 **Espera a live começar sozinho** e grava em blocos.
- 🔊 **Encontra os melhores momentos** pelos picos de volume da live.
- ✂️ **Corta clipes de 30 segundos** (você escolhe o tamanho) em formato vertical.
- 💬 **Legenda automática em português**, que roda no seu PC e não depende de internet.
- 🖼️ **Moldura personalizada** (opcional), com a cara da sua página.
- 🎥 **Câmera do streamer** recortada e colocada embaixo do jogo (opcional).
- 📺 **Também clipa vídeos comuns** do YouTube, não só lives.
- 📲 **Manda tudo pro Telegram** com uma sugestão de legenda para copiar e colar.
- 💸 **É grátis**: tudo roda no seu PC, sem assinatura.

## 💻 Requisitos

- Windows 10 ou 11.
- Uns 20 GB livres no disco.
- Internet estável (cabo é melhor).
- Qualquer processador razoável (um Ryzen 5 / i5 sobra). Placa de vídeo não é obrigatória.

---

## 🚀 Passo a passo

### 1. Baixar
Clique em **Code → Download ZIP**, aqui em cima no GitHub, e extraia numa pasta fácil, por exemplo `C:\clipador`.
Evite a Área de Trabalho e pastas do OneDrive, porque a gravação é pesada para sincronizar.

### 2. Instalar (só na primeira vez)
Dê dois cliques em **`1_INSTALAR.bat`**.
- Na **primeira vez**, ele instala Python 3.12, FFmpeg e Deno. Quando pedir, **feche a janela e rode de novo**.
- Na **segunda vez**, ele instala as bibliotecas e baixa o modelo de legenda (uns 500 MB).
- Espere aparecer **"TUDO PRONTO!"**.

> Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

### 3. Criar o seu bot do Telegram
1. No Telegram, fale com o **@BotFather**, mande `/newbot` e siga as instruções.
2. Ele te dá um **token**. **Clique no token para copiar**, não digite, porque é fácil confundir `0` com `O` e `l` com `I`.
3. Abra o `config.ini` com o Bloco de Notas e cole em `telegram_token = ...`, numa linha só e sem espaços.
4. Abra o **seu** bot no Telegram e mande "oi".
5. Rode o **`3_DESCOBRIR_CHAT_TELEGRAM.bat`**. Ele mostra um número: cole em `telegram_chat_id = ...`, salve e aperte uma tecla para testar.

> 🔒 **Nunca compartilhe o seu token.** Quem tiver o token controla o seu bot.

### 4. Configurar a live
No `config.ini`:
```ini
link_da_live = https://www.youtube.com/@nomedocanal/live
credito_no_video = via @nomedocanal
credito_na_legenda = 🎥 @nomedocanal
```

### 5. Testar
Rode o **`TESTAR.bat`**, cole o link de **qualquer live** que esteja no ar e espere uns 15 minutos. Devem chegar clipes no Telegram.
Depois, feche a janela e rode o **`LIMPAR_TESTE.bat`**.

### 6. Usar de verdade
1. Configure o PC para **não suspender**: Configurações → Sistema → Energia.
2. Rode o **`2_INICIAR.bat`** e **deixe a janela aberta**. Ele espera a live entrar sozinho.

### 🎞️ Clipar um vídeo comum (não live)
Rode o **`CLIPAR_VIDEO.bat`** e cole o link do vídeo do YouTube. Ele baixa, escolhe os melhores momentos e manda tudo pro Telegram.

---

## 🎨 Personalizando

### Formato do vídeo (`formato`)
| Valor | Como fica |
|---|---|
| `desfocado` (padrão) | Mostra o jogo inteiro, com fundo desfocado em cima e embaixo |
| `quadrado` | Jogo maior, corta um pouco das laterais |
| `cheio` | Ocupa a tela toda, corta bastante das laterais |

### Moldura (`moldura`)
1. Use o **`molde_moldura.png`** como guia: ele mostra onde entram o jogo, a legenda e as áreas que o TikTok cobre.
2. Crie a sua imagem em **PNG 1080x1920** e salve na pasta como `moldura.png`.
3. No `config.ini`: `moldura = moldura.png`

Sem moldura (linha vazia), o fundo fica desfocado.

> 💡 Evite usar logos e artes oficiais de jogos e marcas na moldura. Isso pode fazer a sua página parecer oficial e gerar denúncias.

### Câmera do streamer (`camera`)
Recorta a câmera do canto da live e coloca embaixo do jogo. Funciona melhor com `formato = quadrado`.
O valor são 4 números, em **%** da tela da live: `x, y, largura, altura`.
```ini
camera = 74.5,1.2,24.8,30
```
Esse exemplo pega uma câmera no **canto superior direito**. Para achar os números do seu streamer, tire um print da live em tela cheia e veja onde a câmera começa e quanto ela ocupa.

### Quantidade e tamanho dos clipes
| Opção | O que faz |
|---|---|
| `segundos_antes_do_pico` + `segundos_depois_do_pico` | Tamanho do clipe (padrão 20 + 10 = 30s) |
| `minimo_clipes_por_bloco` / `max_clipes_por_bloco` | Quantos clipes a cada bloco de live |
| `intervalo_minimo_entre_clipes` | Distância mínima entre clipes. Deixe **≥ tamanho do clipe**, para não repetir |
| `rigor` | 95 = mais clipes; 99 = só momentos muito fortes |

> Para o **Programa de Recompensas do TikTok**, os vídeos precisam ter **mais de 1 minuto**: use 45 + 20. Para crescer a conta, clipes curtos (15 a 35 segundos) costumam performar melhor.

---

## 🛠️ Problemas comuns

| Problema | Solução |
|---|---|
| `No module named numpy` / `yt_dlp` | A instalação não terminou. Rode o `1_INSTALAR.bat` até aparecer "TUDO PRONTO". |
| "Live ainda não está no ar" com a live no ar | Use o link **exato** da live (`youtube.com/watch?v=...`). |
| "Sign in to confirm you're not a bot" | `cookies_do_navegador = firefox` (e esteja logado no YouTube no Firefox). |
| Telegram "Unauthorized" | O token está errado. Copie de novo **clicando** nele no BotFather. |
| `cublas64_12.dll` | Normal em PCs com placa NVIDIA: ele usa o processador automaticamente. |
| PC travando | `modelo_legenda = base` |
| Muitos clipes ruins | Aumente o `rigor` para 99. |
| Trocou de streamer e chegam clipes do anterior | Na v1.1+ ele limpa sozinho quando o `link_da_live` muda. Em versões antigas, rode o `LIMPAR_TESTE.bat` antes de iniciar. |
| Emoji aparece como quadradinho no vídeo | A fonte do vídeo não tem emoji: deixe o `credito_no_video` só com texto. No `credito_na_legenda` pode usar emoji. |
| Clipes repetindo o mesmo trecho | Deixe `intervalo_minimo_entre_clipes` maior ou igual ao tamanho do clipe (antes + depois). |
| Erro `3221225786` no log | A janela foi fechada no meio de um corte. Não é bug. |
| Chegam clipes demais | Ex.: `minutos_por_bloco = 20`, `minimo_clipes_por_bloco = 1`, `max_clipes_por_bloco = 2`, `rigor = 99` (uns 3 a 6 por hora). |

Os clipes também ficam salvos na pasta **`clipes_prontos`**.

---

## ⚖️ Uso responsável

- **O conteúdo é de quem fez a live.** Peça permissão ao criador antes de postar cortes e **sempre dê o crédito**.
- Se alguém pedir para remover um corte, remova.
- Não use para conteúdo pirata, vazado ou transmissões de TV e esportes, que dão strike rápido.
- Siga as regras de cada plataforma (TikTok, Instagram, YouTube).

O autor não se responsabiliza pelo uso que cada pessoa faz da ferramenta.

---

## 📜 Licença e créditos

Projeto de código aberto sob a **licença MIT** (veja o arquivo `LICENSE`).
Você pode usar, modificar e compartilhar, **mantendo os créditos ao autor original**.

Os clipes saem com a marca discreta **"Feito com mestre-clipador"**. Se a ferramenta te ajudou, deixa uma ⭐ no repositório! 🙌

Feito com: [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [FFmpeg](https://ffmpeg.org) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
