# FieldEye

Análise de desempenho em futebol a partir de vídeo. O usuário envia a gravação
de um jogo ou treino e recebe, de volta, o vídeo com cada jogador rastreado,
métricas de velocidade e distância, e exportação dos dados em CSV e PDF — sem
GPS, coletes ou câmeras especiais.

Projeto pessoal de portfólio. O código está disponível para leitura e para uso
próprio (autohospedagem), mas **não é de uso livre** — ver [Licença](#licença).

---

## Funcionalidades

- Upload de vídeo (MP4, MOV, AVI, MKV) com autenticação por conta.
- Detecção e rastreamento de todos os jogadores, com um identificador por atleta.
- Classificação de time pela cor do uniforme (Time A, Time B e "outros").
- Cálculo de velocidade máxima/média e distância percorrida por jogador.
- Calibração de campo interativa: o usuário marca os quatro cantos no próprio
  vídeo e o sistema converte pixels em metros (homografia), medindo distâncias
  reais e ignorando quem está fora da área marcada.
- Vídeo anotado para download, com caixa, ID e velocidade sobre cada jogador.
- Gráfico de velocidade ao longo do tempo e exportação em CSV e PDF.
- Perfil com histórico das análises.

## Como funciona

O processamento roda em um worker assíncrono e segue estas etapas:

1. Leitura do vídeo com OpenCV (normalizado para frame rate constante).
2. Detecção de pessoas e bola com YOLOv8.
3. Classificação de time por cor (K-means sobre a cor do uniforme).
4. Rastreamento com BoT-SORT (mantém o ID do jogador ao longo do jogo).
5. Homografia: conversão de pixels para metros.
6. Física: velocidade, distância e sprints.
7. Interpolação de falhas de rastreamento e consolidação de IDs.
8. Renderização do vídeo anotado.

## Arquitetura

Microserviços orquestrados por Docker Compose, com Traefik como gateway.

| Serviço | Papel | Stack |
|---|---|---|
| `traefik` | Gateway/roteamento e rate limiting | Traefik |
| `frontend` | Interface web | Next.js, TypeScript, Tailwind |
| `auth-service` | Contas e autenticação (JWT) | FastAPI |
| `video-service` | Upload, jobs e fila | FastAPI |
| `analytics-service` | Resultados e exportações | FastAPI |
| `worker` | Processamento de IA | Celery, YOLOv8, BoT-SORT, OpenCV |
| `redis` | Fila de tarefas e cache | Redis |
| `postgres` | Banco de dados | PostgreSQL |

## Requisitos

- Docker Desktop (Windows/macOS) ou Docker Engine + Compose (Linux).
- Cerca de 8 GB de RAM.
- Espaço em disco para os modelos e os vídeos processados.
- Opcional, para o modo "Qualidade": GPU NVIDIA com drivers atualizados
  (habilita o CUDA no worker — ver [Modos de análise](#modos-de-análise)).

## Como rodar (autohospedagem)

O projeto roda inteiramente na sua máquina; não é preciso servidor nem nuvem.

```bash
# 1. Clonar o repositório
git clone <url-do-repositorio>
cd FieldEye

# 2. Criar o arquivo de ambiente a partir do modelo
cp .env.example .env
#    Edite o .env e troque as senhas/segredos (POSTGRES_PASSWORD, JWT_SECRET).
#    Opcional: defina HOST_DATA_DIR para guardar os vídeos fora do projeto.

# 3. Subir tudo (a primeira vez baixa as imagens e compila — pode demorar)
docker compose up --build
```

Quando os contêineres estiverem no ar, abra **http://localhost**, crie uma conta
e envie um vídeo. O primeiro processamento também baixa o modelo de detecção.

Para parar: `docker compose down` (os dados do banco e os vídeos são preservados).

## Como usar

1. Crie uma conta e faça login.
2. No painel, selecione um vídeo.
3. Escolha o **modo de análise** (Velocidade ou Qualidade) e a **área**
   (marcar a região no vídeo ou usar um campo oficial).
4. Se escolher marcar a região, clique nos quatro cantos do campo sobre o frame.
5. Clique em **Executar análise**. Acompanhe o progresso no painel.
6. Ao terminar, abra os resultados: vídeo anotado, métricas por jogador,
   gráfico de velocidade e exportação em CSV/PDF.

## Modos de análise

- **Velocidade**: modelo leve (YOLOv8n) em baixa resolução. Rápido e roda em
  qualquer CPU. Bom para testes e vídeos com boa visão dos jogadores.
- **Qualidade**: modelo maior (YOLOv8s) em resolução alta. Detecta jogadores
  pequenos e distantes (câmera alta/tática), ao custo de mais tempo e memória.

O worker usa GPU NVIDIA automaticamente quando disponível. Em Docker Desktop com
WSL2, basta ter os drivers NVIDIA instalados; a passagem da GPU já está
configurada no `docker-compose.yml`. Sem GPU, o modo Qualidade funciona em CPU,
porém mais lento.

## Configuração

As principais variáveis ficam no `.env` (veja o `.env.example` comentado):

- `POSTGRES_PASSWORD`, `JWT_SECRET`: **troque** antes de usar.
- `HOST_DATA_DIR`: pasta no host onde os vídeos são guardados.
- `MODEL_NAME`, `YOLO_IMGSZ`, `YOLO_CONF`: ajustes do modo Velocidade.
- `MODEL_NAME_HQ`, `YOLO_IMGSZ_HQ`, `YOLO_CONF_HQ`: ajustes do modo Qualidade.

## Estrutura do projeto

```
FieldEye/
├── docker-compose.yml        # orquestração dos serviços
├── gateway/                  # configuração do Traefik
├── frontend/                 # aplicação Next.js
└── services/
    ├── auth/                 # autenticação (FastAPI)
    ├── video/                # upload e jobs (FastAPI)
    ├── analytics/            # resultados e exportações (FastAPI)
    └── worker/               # pipeline de IA (Celery + YOLOv8)
```

## Limitações conhecidas

- A distinção entre goleiro e árbitro por cor não é perfeita; ambos podem cair
  na categoria "outros".
- Câmeras muito distantes tornam a detecção difícil, mesmo no modo Qualidade.
- Um mesmo jogador pode receber IDs diferentes após oclusões longas.

Essas frentes estão em evolução.

## Licença

© 2026 Albuqmarq. Todos os direitos reservados.

Este repositório é público apenas para fins de avaliação e portfólio. Não é
concedida permissão para copiar, modificar, redistribuir ou usar este código,
no todo ou em parte, em outros projetos sem autorização expressa do autor.
Consulte o arquivo [LICENSE](LICENSE) para os termos completos.
