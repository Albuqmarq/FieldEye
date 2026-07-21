
-- init.sql — estrutura inicial do banco FieldEye.
-- Executado automaticamente pelo contêiner do Postgres na PRIMEIRA subida
-- (arquivos em /docker-entrypoint-initdb.d/ rodam uma vez, no banco vazio).


-- Extensão para gerar UUIDs (usada na tabela de jobs).
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- usuários: quem faz login e envia vídeos.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,   -- login (único)
    password_hash VARCHAR(255) NOT NULL,          -- hash bcrypt (nunca a senha pura)
    team_name     VARCHAR(255),                   -- nome do time/clube do usuário
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- jobs: cada análise de vídeo solicitada.
-- O video-service cria o job; o worker atualiza status/progress.

CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|processing|done|failed
    progress      INTEGER NOT NULL DEFAULT 0,              -- 0 a 100 (%)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    video_path    TEXT,            -- caminho do vídeo de entrada (em /data/uploads)
    output_path   TEXT,            -- caminho do vídeo anotado (em /data/outputs)
    error_message TEXT,            -- preenchido se status='failed'
    options       JSONB            -- opções da análise (modelo, calibração, etc.)
);

-- Índice para listar rapidamente os jobs de um usuário.
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);


-- player_tracks: resultado AGREGADO por jogador em um job.
-- (uma linha por jogador rastreado)

CREATE TABLE IF NOT EXISTS player_tracks (
    id             SERIAL PRIMARY KEY,
    job_id         UUID REFERENCES jobs(id) ON DELETE CASCADE,
    player_id      INTEGER NOT NULL,        -- ID do jogador dentro do job
    team           VARCHAR(20),             -- 'A' | 'B' | 'goalkeeper'
    max_speed      REAL,                    -- km/h
    avg_speed      REAL,                    -- km/h
    total_distance REAL,                    -- metros
    trajectory     JSONB,                   -- lista de posições [{frame,x,y}, ...]
    heatmap_data   JSONB                    -- matriz/densidade do heatmap
);

CREATE INDEX IF NOT EXISTS idx_player_tracks_job_id ON player_tracks(job_id);


-- frame_data: dados FRAME A FRAME (granular).
-- Permite reconstruir gráficos de velocidade ao longo do tempo.

CREATE TABLE IF NOT EXISTS frame_data (
    id            BIGSERIAL PRIMARY KEY,
    job_id        UUID REFERENCES jobs(id) ON DELETE CASCADE,
    player_id     INTEGER NOT NULL,
    frame_number  INTEGER NOT NULL,
    timestamp     REAL,        -- segundos no vídeo
    x             REAL,        -- posição no campo (metros)
    y             REAL,
    speed         REAL         -- km/h instantânea
);

-- Índice composto: buscar a série temporal de um jogador num job.
CREATE INDEX IF NOT EXISTS idx_frame_data_job_player
    ON frame_data(job_id, player_id);
