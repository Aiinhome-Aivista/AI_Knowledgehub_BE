-- ============================================================
-- STEP 1: Pura database drop karo aur fresh banao
-- ============================================================
DROP DATABASE IF EXISTS ai_knowledge_hub;
CREATE DATABASE ai_knowledge_hub;
USE ai_knowledge_hub;

-- ============================================================
-- STEP 2: Saari tables fresh banao
-- ============================================================

-- 1. Topics Table
CREATE TABLE topics (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    category    VARCHAR(255),
    description LONGTEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Articles Meta Table
CREATE TABLE articles_meta (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    title      TEXT,
    source_url VARCHAR(768) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Connectors Table
CREATE TABLE connectors (
    id         VARCHAR(255) PRIMARY KEY,
    url        VARCHAR(768) NOT NULL UNIQUE,
    type       VARCHAR(50)  NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Roles Table
CREATE TABLE roles (
    role_id    INT AUTO_INCREMENT PRIMARY KEY,
    role_name  VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 5. Users Table
CREATE TABLE users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    email      VARCHAR(255) NOT NULL UNIQUE,
    password   VARCHAR(255) NOT NULL,
    role_id    INT NOT NULL,
    name       VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

-- 5. Article Topics Table (Many-to-many: articles <-> topics)
CREATE TABLE article_topics (
    article_id INT NOT NULL,
    topic_id   INT NOT NULL,
    PRIMARY KEY (article_id, topic_id),
    FOREIGN KEY (article_id) REFERENCES articles_meta(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id)   REFERENCES topics(id)        ON DELETE CASCADE
);

-- 6. Search Logs Table
CREATE TABLE search_logs (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    query         VARCHAR(255) NOT NULL UNIQUE,
    count         INT          DEFAULT 1,
    last_searched TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 7. Scheduler Logs Table
CREATE TABLE scheduler_logs (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    run_at             DATETIME    NOT NULL,
    next_run_at        DATETIME    DEFAULT NULL,
    interval_hours     INT         NOT NULL DEFAULT 6,
    status             VARCHAR(50) NOT NULL DEFAULT 'SUCCESS',
    articles_processed INT         DEFAULT 0,
    nodes_added        INT         DEFAULT 0,
    nodes_updated      INT         DEFAULT 0,
    edges_added        INT         DEFAULT 0,
    errors             TEXT        DEFAULT NULL,
    triggered_by       VARCHAR(50) DEFAULT 'scheduler',
    created_at         TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- STEP 3: Default data insert karo
-- ============================================================
INSERT INTO roles (role_name) VALUES ('admin'), ('viewer');

INSERT INTO users (email, password, role_id, name)
    VALUES ('sonia123@gmail.com', 'sonia@123', 1, 'Sonia');

INSERT INTO users (email, password, role_id, name)
    VALUES ('anindita@gmail.com', 'anindita@123', 2, 'Anindita');

-- ============================================================
-- Verification: Saari tables check karo
-- ============================================================
SHOW TABLES;
