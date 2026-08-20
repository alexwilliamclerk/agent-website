-- 能力诊断与学习资源生成系统 - 数据库初始化脚本

CREATE DATABASE IF NOT EXISTS capability_diagnosis DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE capability_diagnosis;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    target_job VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email)
);

-- 职业表
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    job_title VARCHAR(100) NOT NULL,
    description TEXT,
    required_skills JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 能力评估表
CREATE TABLE IF NOT EXISTS assessments (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    job_id VARCHAR(36) NOT NULL,
    user_input TEXT,
    overall_mastery DECIMAL(5,4),
    ability_vector JSON,
    ability_matrix JSON,
    knowledge_gaps JSON,
    gap_validation JSON,
    confidence DECIMAL(5,4),
    requirement_scores JSON,
    calibration_status VARCHAR(30) DEFAULT 'unvalidated',
    calibration_summary JSON,
    material_ids JSON,
    agent_trace JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    INDEX idx_user_id (user_id)
);

-- 用户上传的学习资料：原文件与解析状态分离，只有 parsed 文本才会被送入 Agent。
CREATE TABLE IF NOT EXISTS user_materials (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    job_id VARCHAR(36),
    assessment_id VARCHAR(36),
    original_name VARCHAR(255) NOT NULL,
    storage_name VARCHAR(255),
    content_type VARCHAR(120),
    size_bytes INT DEFAULT 0,
    status VARCHAR(24) NOT NULL DEFAULT 'uploaded',
    extracted_text TEXT,
    source_url VARCHAR(1000),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (assessment_id) REFERENCES assessments(id),
    INDEX idx_material_user (user_id),
    INDEX idx_material_assessment (assessment_id)
);

-- 真实结果校准记录：保存 AI 判断与客观/专家结果的逐能力项差异
CREATE TABLE IF NOT EXISTS calibration_records (
    id VARCHAR(36) PRIMARY KEY,
    assessment_id VARCHAR(36) NOT NULL,
    requirement_id VARCHAR(120) NOT NULL,
    requirement_name VARCHAR(120) NOT NULL,
    predicted_score DECIMAL(5,4),
    gold_score DECIMAL(5,4),
    absolute_error DECIMAL(5,4),
    predicted_status VARCHAR(20),
    gold_status VARCHAR(20),
    status VARCHAR(20) NOT NULL,
    is_correct TINYINT DEFAULT 0,
    trusted TINYINT DEFAULT 1,
    source_type VARCHAR(30) DEFAULT 'expert',
    reference_answer TEXT,
    evidence_ids JSON,
    details JSON,
    calibration_version VARCHAR(60) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id),
    INDEX idx_calibration_assessment (assessment_id),
    INDEX idx_calibration_requirement (requirement_id)
);

-- 学习会话表
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    job_id VARCHAR(36) NOT NULL,
    status VARCHAR(24) DEFAULT 'active',
    current_step INT DEFAULT 1,
    progress DECIMAL(5,4) DEFAULT 0,
    turn_count INT NOT NULL DEFAULT 0,
    minimum_turns INT NOT NULL DEFAULT 2,
    ready_for_diagnosis TINYINT NOT NULL DEFAULT 0,
    review_state JSON,
    assessment_id VARCHAR(36),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (assessment_id) REFERENCES assessments(id),
    INDEX idx_user_id (user_id)
);

-- 资料审查多轮对话：仅保存学习者输入、Agent 追问与有界上下文快照。
CREATE TABLE IF NOT EXISTS session_messages (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    turn_index INT NOT NULL DEFAULT 0,
    context_snapshot JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_session_message_session (session_id),
    INDEX idx_session_message_user (user_id)
);

-- 学习路径表
CREATE TABLE IF NOT EXISTS learning_paths (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    job_id VARCHAR(36) NOT NULL,
    steps JSON,
    current_step INT DEFAULT 1,
    status ENUM('active', 'completed', 'abandoned') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    INDEX idx_user_id (user_id)
);

-- 学习资源表
CREATE TABLE IF NOT EXISTS resources (
    id VARCHAR(36) PRIMARY KEY,
    assessment_id VARCHAR(36),
    knowledge_point VARCHAR(100) NOT NULL,
    content_type ENUM('讲义', '练习', '案例', '视频脚本') NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    difficulty INT CHECK (difficulty BETWEEN 1 AND 5),
    source_chunk_id VARCHAR(100),
    source_text TEXT,
    source_title VARCHAR(255),
    source_score DECIMAL(6,4),
    review_status VARCHAR(20),
    review_reason TEXT,
    is_legacy TINYINT DEFAULT 0,
    generation_method VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id),
    INDEX idx_assessment_id (assessment_id),
    INDEX idx_knowledge_point (knowledge_point),
    INDEX idx_source_chunk_id (source_chunk_id),
    INDEX idx_review_status (review_status)
);

-- 学习记录表
CREATE TABLE IF NOT EXISTS learning_records (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    resource_id VARCHAR(36) NOT NULL,
    status ENUM('not_started', 'in_progress', 'completed') DEFAULT 'not_started',
    score DECIMAL(5,4),
    time_spent INT DEFAULT 0,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (resource_id) REFERENCES resources(id),
    INDEX idx_user_id (user_id),
    INDEX idx_session_id (session_id)
);
