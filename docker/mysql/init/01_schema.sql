-- pgx-rag 元数据库初始化（MySQL 首次启动自动执行）
-- 对应「电商问数」里 meta 库的角色：存结构化元数据，而不是正文检索数据本身。

CREATE DATABASE IF NOT EXISTS pgx_meta
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

USE pgx_meta;

-- 药物与「基因-药物」配对（来自 CPIC 清单，供检索过滤与报告统计用）
CREATE TABLE IF NOT EXISTS drugs (
  drug          VARCHAR(64)  NOT NULL COMMENT '通用名，如 clopidogrel',
  drug_class    VARCHAR(128)          DEFAULT NULL,
  genes         JSON                  DEFAULT NULL COMMENT 'CPIC 期望基因数组',
  topic         VARCHAR(255)          DEFAULT NULL,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (drug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 说明书（一份 SPL 标签 = 一行），chunk 通过 set_id 关联
CREATE TABLE IF NOT EXISTS documents (
  set_id           VARCHAR(64)  NOT NULL,
  drug             VARCHAR(64)  NOT NULL,
  label_id         VARCHAR(64)           DEFAULT NULL,
  brand_name       VARCHAR(255)          DEFAULT NULL,
  manufacturer     VARCHAR(255)          DEFAULT NULL,
  route            VARCHAR(64)           DEFAULT NULL,
  effective_date   DATE                  DEFAULT NULL,
  ingredient_count TINYINT               DEFAULT 1,
  api_url          TEXT                  DEFAULT NULL,
  dailymed_url     TEXT                  DEFAULT NULL,
  PRIMARY KEY (set_id),
  KEY idx_documents_drug (drug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 切片：正文块与表格块统一存放；表格的完整结构在 label_tables 里
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id         VARCHAR(128) NOT NULL,
  set_id           VARCHAR(64)           DEFAULT NULL,
  drug             VARCHAR(64)  NOT NULL,
  drug_class       VARCHAR(128)          DEFAULT NULL,
  section          VARCHAR(128) NOT NULL,
  section_label    VARCHAR(255)          DEFAULT NULL,
  section_priority TINYINT      NOT NULL DEFAULT 5,
  kind             ENUM('text','table') NOT NULL,
  heading          VARCHAR(255)          DEFAULT NULL,
  text             MEDIUMTEXT   NOT NULL,
  chars            INT          NOT NULL DEFAULT 0,
  est_tokens       INT          NOT NULL DEFAULT 0,
  pgx_genes        JSON                  DEFAULT NULL,
  pgx_phenotypes   JSON                  DEFAULT NULL,
  pgx_alleles      JSON                  DEFAULT NULL,
  is_pgx           TINYINT      NOT NULL DEFAULT 0,
  table_id         VARCHAR(64)           DEFAULT NULL,
  row_start        INT                   DEFAULT NULL,
  row_end          INT                   DEFAULT NULL,
  evidence         JSON                  DEFAULT NULL,
  PRIMARY KEY (chunk_id),
  KEY idx_chunks_drug (drug),
  KEY idx_chunks_section (section),
  KEY idx_chunks_kind (kind),
  KEY idx_chunks_pgx (is_pgx),
  FULLTEXT KEY ft_chunks_text (text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 表格结构：行列矩阵 + 原始 HTML（阶段 3 引用时可直接渲染成表）
CREATE TABLE IF NOT EXISTS label_tables (
  table_id      VARCHAR(64) NOT NULL,
  drug          VARCHAR(64) NOT NULL,
  section       VARCHAR(128) NOT NULL,
  caption       TEXT                 DEFAULT NULL,
  headers       JSON                 DEFAULT NULL,
  rows          LONGTEXT             DEFAULT NULL COMMENT '二维数组 JSON',
  n_rows        INT         NOT NULL DEFAULT 0,
  n_cols        INT         NOT NULL DEFAULT 0,
  header_source VARCHAR(16)          DEFAULT NULL,
  has_rowspan   TINYINT     NOT NULL DEFAULT 0,
  has_colspan   TINYINT     NOT NULL DEFAULT 0,
  footnotes     JSON                 DEFAULT NULL,
  html_sha      CHAR(40)             DEFAULT NULL,
  html          MEDIUMTEXT           DEFAULT NULL,
  PRIMARY KEY (table_id),
  KEY idx_tables_drug (drug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 索引构建记录（向量/全文索引的可追溯版本）
CREATE TABLE IF NOT EXISTS index_builds (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  target    VARCHAR(32)  NOT NULL COMMENT 'qdrant | es',
  model     VARCHAR(128)          DEFAULT NULL,
  chunks    INT                   DEFAULT 0,
  built_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
