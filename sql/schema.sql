-- Draft schema for migrating the static CSVs into SQLite/PostgreSQL.
-- Adjust once the existing CSV columns are mapped.

CREATE TABLE cases (
    id              INTEGER PRIMARY KEY,
    court           TEXT NOT NULL,            -- 'SCC', 'ONCA', 'BCCA'
    docket_number   TEXT NOT NULL,
    style_of_cause  TEXT,
    citation        TEXT,
    status          TEXT,                     -- 'leave_granted', 'heard', 'decided', ...
    leave_granted_on DATE,
    decided_on      DATE,
    source_url      TEXT,
    UNIQUE (court, docket_number)
);

CREATE TABLE charter_sections (
    id      INTEGER PRIMARY KEY,
    label   TEXT NOT NULL UNIQUE              -- e.g. 's. 8'
);

CREATE TABLE case_charter_sections (
    case_id     INTEGER NOT NULL REFERENCES cases(id),
    section_id  INTEGER NOT NULL REFERENCES charter_sections(id),
    PRIMARY KEY (case_id, section_id)
);

CREATE TABLE organizations (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);

CREATE TABLE counsel (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    firm            TEXT,
    city            TEXT
);

-- One row per (case, party/intervener, counsel) relationship
CREATE TABLE appearances (
    id              INTEGER PRIMARY KEY,
    case_id         INTEGER NOT NULL REFERENCES cases(id),
    organization_id INTEGER REFERENCES organizations(id),
    counsel_id      INTEGER REFERENCES counsel(id),
    party_role      TEXT NOT NULL,            -- 'appellant', 'respondent', 'intervener'
    counsel_role    TEXT,                     -- 'counsel', 'agent'
    is_ottawa_agent INTEGER DEFAULT 0,        -- Stage 2
    is_pro_bono     INTEGER                   -- NULL = unknown
);

-- Monitor (Stage 1)
CREATE TABLE subscribers (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    confirmed   INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subscriptions (
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    section_id    INTEGER REFERENCES charter_sections(id),  -- NULL = all sections
    court         TEXT,                                     -- NULL = all courts
    UNIQUE (subscriber_id, section_id, court)
);

CREATE TABLE alerts_sent (
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
    case_id       INTEGER NOT NULL REFERENCES cases(id),
    sent_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (subscriber_id, case_id)
);

CREATE INDEX idx_appearances_case ON appearances(case_id);
CREATE INDEX idx_appearances_counsel ON appearances(counsel_id);
CREATE INDEX idx_appearances_org ON appearances(organization_id);
