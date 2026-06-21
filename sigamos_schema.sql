-- ============================================================
--  SIGAMOS — Esquema de Base de Datos PostgreSQL v2.2
--  Proyecto: Sistema de Recomendación Financiera con ML
--  Universidad: UPC — Ingeniería de Sistemas de Información
--  Base de datos: sigamos_db
--  Generado para: Vertabelo
--
--  Modelo ML: XGBoost Classifier binario (Déficit=0 / Ahorra=1).
--  NO hay K-Means ni regresión de montos (eliminados por completo).
--
--  Decisiones de diseño:
--  - Tabla PerfilFinanciero ELIMINADA: campos integrados en accounts_usuario
--  - Bonificación integrada como columna en financiero_registromensual
--    (no es tabla aparte): se suma al ingreso de planilla antes del ML
--  - ResultadoML guarda la CLASIFICACIÓN (clase/label/prob/confianza) + un JSON
--    ligero de top features SHAP; las opciones de recorte se recomputan on-demand
--  - ResultadoML separa mes_referencia_id (mes clasificado) de registro_id
--    (mes actual sobre el que se genera el plan counterfactual)
--  - RBAC con tabla accounts_rol (FK directa, no ManyToMany)
--  - Gamificación funcional: Racha + Logro + LogroUsuario con lógica de desbloqueo
--  - PlanSeleccionado: un único plan activo por usuario garantizado por
--    índice único parcial (WHERE activo)
--
--  NOTA: este esquema documenta las 13 tablas de NEGOCIO. Las tablas internas
--  de Django (auth_*, django_*) las crea el framework con `migrate` y no se
--  modelan aquí.
-- ============================================================


-- ============================================================
--  1. accounts_rol
--     Catálogo de roles del sistema (RBAC).
--     Exactamente 2 filas: USUARIO y ADMIN.
-- ============================================================
CREATE TABLE accounts_rol (
    id          BIGSERIAL       NOT NULL,
    nombre      VARCHAR(20)     NOT NULL,
    descripcion VARCHAR(200)    NOT NULL    DEFAULT '',

    CONSTRAINT pk_rol           PRIMARY KEY (id),
    CONSTRAINT uq_rol_nombre    UNIQUE      (nombre),
    CONSTRAINT ck_rol_nombre    CHECK       (nombre IN ('USUARIO', 'ADMIN'))
);

COMMENT ON TABLE  accounts_rol        IS 'Catálogo de roles del sistema SIGAMOS (RBAC).';
COMMENT ON COLUMN accounts_rol.nombre IS 'USUARIO = acceso normal. ADMIN = gestión y métricas.';


-- ============================================================
--  2. accounts_usuario
--     Tabla central del sistema.
--     Integra directamente los campos de perfil financiero
--     (edad, nivel_educ, miembros_hogar) que consume predict.py.
--     Login por email. Rol via FK.
-- ============================================================
CREATE TABLE accounts_usuario (
    id              BIGSERIAL       NOT NULL,
    -- Credenciales
    email           VARCHAR(254)    NOT NULL,
    password        VARCHAR(128)    NOT NULL,
    -- Identificadores
    nickname        VARCHAR(30)     NOT NULL,
    username        VARCHAR(150)    NOT NULL,
    -- Nombre real
    first_name      VARCHAR(150)    NOT NULL    DEFAULT '',
    last_name       VARCHAR(150)    NOT NULL    DEFAULT '',
    -- Control de acceso
    rol_id          BIGINT,
    is_active       BOOLEAN         NOT NULL    DEFAULT TRUE,
    is_staff        BOOLEAN         NOT NULL    DEFAULT FALSE,
    is_superuser    BOOLEAN         NOT NULL    DEFAULT FALSE,
    -- Fechas
    date_joined     TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    -- Perfil financiero (campos requeridos por src/predict.py)
    edad            SMALLINT,
    nivel_educ      SMALLINT,
    miembros_hogar  SMALLINT        NOT NULL    DEFAULT 1,
    -- Contacto (UI, no usados en ML)
    telefono        VARCHAR(20)     NOT NULL    DEFAULT '',
    ciudad          VARCHAR(100)    NOT NULL    DEFAULT 'Lima',

    CONSTRAINT pk_usuario               PRIMARY KEY (id),
    CONSTRAINT uq_usuario_email         UNIQUE      (email),
    CONSTRAINT uq_usuario_nickname      UNIQUE      (nickname),
    CONSTRAINT uq_usuario_username      UNIQUE      (username),
    CONSTRAINT fk_usuario_rol           FOREIGN KEY (rol_id)
                                        REFERENCES  accounts_rol (id)
                                        ON DELETE   RESTRICT,
    CONSTRAINT ck_usuario_edad          CHECK (edad IS NULL OR (edad BETWEEN 15 AND 80)),
    CONSTRAINT ck_usuario_nivel_educ    CHECK (nivel_educ IS NULL OR nivel_educ BETWEEN 1 AND 6),
    CONSTRAINT ck_usuario_miembros      CHECK (miembros_hogar BETWEEN 1 AND 20)
);

COMMENT ON TABLE  accounts_usuario                 IS 'Usuarios del sistema SIGAMOS. Login por email. Rol via FK.';
COMMENT ON COLUMN accounts_usuario.email           IS 'Campo principal de autenticación (USERNAME_FIELD).';
COMMENT ON COLUMN accounts_usuario.nickname        IS 'Nombre visible único. Máx 30 caracteres.';
COMMENT ON COLUMN accounts_usuario.rol_id          IS 'FK a accounts_rol. Determina is_staff automáticamente.';
COMMENT ON COLUMN accounts_usuario.edad            IS 'Requerido para análisis ML (EDAD en predict.py).';
COMMENT ON COLUMN accounts_usuario.nivel_educ      IS '1=Sin educ 2=Primaria 3=Secundaria 4=Técnico 5=Univ. 6=Posgrado. Requerido para ML.';
COMMENT ON COLUMN accounts_usuario.miembros_hogar  IS 'Personas que dependen del ingreso. Requerido para ML.';


-- ============================================================
--  3. financiero_registromensual
--     Ingresos y gastos mensuales del usuario.
--     Contiene los 13 campos de entrada de src/predict.py:
--       3 del perfil (en accounts_usuario) + 2 ingresos + 8 gastos.
--     bonif_monto: ingreso extraordinario del mes (CTS, gratificación,
--     otro bono). Se SUMA a ing_planilla antes de ejecutar el ML.
--     Restricción: un solo registro por usuario por mes.
-- ============================================================
CREATE TABLE financiero_registromensual (
    id                          BIGSERIAL       NOT NULL,
    usuario_id                  BIGINT          NOT NULL,
    periodo                     DATE            NOT NULL,
    -- Ingresos
    ing_planilla                NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    ing_informal                NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    -- Bonificación / ingreso extraordinario del período
    bonif_monto                 NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    -- Gastos (exactamente los 8 de GASTO_COLS en predict.py)
    gasto_alimentos             NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_vestido               NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_vivienda_servicios    NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_salud                 NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_transporte            NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_comunicaciones        NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_educacion             NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    gasto_otros_bienes          NUMERIC(10,2)   NOT NULL    DEFAULT 0,
    -- Auditoría
    creado_en                   TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),
    actualizado_en              TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_registromensual           PRIMARY KEY (id),
    CONSTRAINT uq_registro_usuario_periodo  UNIQUE      (usuario_id, periodo),
    CONSTRAINT fk_registro_usuario          FOREIGN KEY (usuario_id)
                                            REFERENCES  accounts_usuario (id)
                                            ON DELETE   CASCADE,
    CONSTRAINT ck_registro_ingresos         CHECK ((ing_planilla + ing_informal + bonif_monto) > 0),
    CONSTRAINT ck_registro_bonif            CHECK (bonif_monto >= 0),
    CONSTRAINT ck_registro_gastos           CHECK (
        gasto_alimentos >= 0 AND gasto_vestido >= 0 AND
        gasto_vivienda_servicios >= 0 AND gasto_salud >= 0 AND
        gasto_transporte >= 0 AND gasto_comunicaciones >= 0 AND
        gasto_educacion >= 0 AND gasto_otros_bienes >= 0
    )
);

COMMENT ON TABLE  financiero_registromensual              IS 'Registro financiero mensual. Un registro por usuario por mes.';
COMMENT ON COLUMN financiero_registromensual.periodo      IS 'Siempre el día 01 del mes: YYYY-MM-01.';
COMMENT ON COLUMN financiero_registromensual.bonif_monto  IS 'Bonificación del mes (CTS, gratificación, etc.). Se suma a ing_planilla para el ML.';


-- ============================================================
--  4. recomendaciones_metamensual
--     Meta de ahorro mensual. Parámetro meta_ahorro de recommend().
-- ============================================================
CREATE TABLE recomendaciones_metamensual (
    id          BIGSERIAL       NOT NULL,
    usuario_id  BIGINT          NOT NULL,
    periodo     DATE            NOT NULL,
    monto       NUMERIC(10,2)   NOT NULL,

    CONSTRAINT pk_metamensual           PRIMARY KEY (id),
    CONSTRAINT uq_meta_usuario_periodo  UNIQUE      (usuario_id, periodo),
    CONSTRAINT fk_metamensual_usuario   FOREIGN KEY (usuario_id)
                                        REFERENCES  accounts_usuario (id)
                                        ON DELETE   CASCADE,
    CONSTRAINT ck_metamensual_monto     CHECK (monto >= 0)
);

COMMENT ON TABLE recomendaciones_metamensual IS 'Meta de ahorro mensual. Se pasa como meta_ahorro a recommend().';


-- ============================================================
--  5. recomendaciones_metalargoplazo
--     Objetivos de ahorro a largo plazo del usuario (UI-only).
--     No se pasan al ML — son motivacionales.
-- ============================================================
CREATE TABLE recomendaciones_metalargoplazo (
    id              BIGSERIAL       NOT NULL,
    usuario_id      BIGINT          NOT NULL,
    nombre          VARCHAR(100)    NOT NULL,
    icono           VARCHAR(20)     NOT NULL    DEFAULT '🎯',
    monto_objetivo  NUMERIC(12,2)   NOT NULL,
    monto_actual    NUMERIC(12,2)   NOT NULL    DEFAULT 0,
    fecha_limite    DATE,
    activa          BOOLEAN         NOT NULL    DEFAULT TRUE,
    creado_en       TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_metalargoplazo            PRIMARY KEY (id),
    CONSTRAINT fk_metalargo_usuario         FOREIGN KEY (usuario_id)
                                            REFERENCES  accounts_usuario (id)
                                            ON DELETE   CASCADE,
    CONSTRAINT ck_metalargo_monto_objetivo  CHECK (monto_objetivo > 0),
    CONSTRAINT ck_metalargo_monto_actual    CHECK (monto_actual >= 0)
);

COMMENT ON TABLE  recomendaciones_metalargoplazo        IS 'Metas a largo plazo (viaje, emergencia, etc.). UI-only, no se pasa al ML.';
COMMENT ON COLUMN recomendaciones_metalargoplazo.activa IS 'FALSE = soft delete. Nunca se borra físicamente.';


-- ============================================================
--  6. recomendaciones_resultadoml
--     Resultado ESCALARES de cada ejecución de recommend().
--
--     Modelo nuevo: XGBoost Classifier binario (Déficit/Ahorra).
--     NO hay K-Means ni montos predichos.
--     Diseño deliberado: NO almacena opciones ni SHAP completo.
--     Las estrategias (Suave/Equilibrado/Decidido) y el SHAP
--     se recomputan llamando a recommend() desde el RegistroMensual
--     original cuando el usuario consulta el detalle.
--     Esto mantiene la BD ligera y desacoplada de predict.py.
-- ============================================================
CREATE TABLE recomendaciones_resultadoml (
    id                  BIGSERIAL           NOT NULL,
    usuario_id          BIGINT              NOT NULL,
    registro_id         BIGINT              NOT NULL,
    mes_referencia_id   BIGINT,
    meta_id             BIGINT,
    -- Escalares de recommend()
    ahorro_actual       DOUBLE PRECISION    NOT NULL,   -- identidad contable real (no predicho)
    meta_validada       DOUBLE PRECISION    NOT NULL,
    necesita_recortar   DOUBLE PRECISION    NOT NULL    DEFAULT 0,
    -- Clasificación binaria (XGBoost Classifier)
    clase_predicha      INTEGER             NOT NULL    DEFAULT 0,   -- 0=Déficit, 1=Ahorra
    label_predicha      VARCHAR(20)         NOT NULL    DEFAULT '',
    prob_ahorra         DOUBLE PRECISION    NOT NULL    DEFAULT 0,
    confianza           VARCHAR(250)        NOT NULL,
    shap_top_features   JSONB               NOT NULL    DEFAULT '[]',
    creado_en           TIMESTAMPTZ         NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_resultadoml           PRIMARY KEY (id),
    CONSTRAINT fk_resultado_usuario     FOREIGN KEY (usuario_id)
                                        REFERENCES  accounts_usuario (id)
                                        ON DELETE   CASCADE,
    CONSTRAINT fk_resultado_registro    FOREIGN KEY (registro_id)
                                        REFERENCES  financiero_registromensual (id)
                                        ON DELETE   CASCADE,
    CONSTRAINT fk_resultado_mes_ref     FOREIGN KEY (mes_referencia_id)
                                        REFERENCES  financiero_registromensual (id)
                                        ON DELETE   SET NULL,
    CONSTRAINT fk_resultado_meta        FOREIGN KEY (meta_id)
                                        REFERENCES  recomendaciones_metamensual (id)
                                        ON DELETE   SET NULL,
    CONSTRAINT ck_resultado_clase       CHECK (clase_predicha IN (0, 1))
);

COMMENT ON TABLE  recomendaciones_resultadoml                   IS 'Escalares del pipeline ML (clasificación binaria). Opciones/SHAP se recomputan on-demand.';
COMMENT ON COLUMN recomendaciones_resultadoml.necesita_recortar IS 'max(meta_validada - ahorro_actual, 0). 0 = ya cumple.';
COMMENT ON COLUMN recomendaciones_resultadoml.clase_predicha    IS '0 = Déficit, 1 = Ahorra (XGBoost Classifier binary:logistic).';
COMMENT ON COLUMN recomendaciones_resultadoml.confianza         IS '"Alta" / "Media" / "Baja" según margen sobre 0.5.';


-- ============================================================
--  7. recomendaciones_planseleccionado
--     Plan de optimización elegido por el usuario desde ML Insights.
--     Solo puede haber UN plan activo por usuario a la vez
--     (garantizado por índice único parcial WHERE activo).
-- ============================================================
CREATE TABLE recomendaciones_planseleccionado (
    id                  BIGSERIAL           NOT NULL,
    usuario_id          BIGINT              NOT NULL,
    resultado_id        BIGINT,
    nombre_plan         VARCHAR(20)         NOT NULL,
    ahorro_proyectado   DOUBLE PRECISION    NOT NULL,
    meta_ahorro         DOUBLE PRECISION    NOT NULL,
    gastos_sugeridos    JSONB               NOT NULL,
    activo              BOOLEAN             NOT NULL    DEFAULT TRUE,
    fecha_seleccion     TIMESTAMPTZ         NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_planseleccionado      PRIMARY KEY (id),
    CONSTRAINT fk_plansel_usuario       FOREIGN KEY (usuario_id)
                                        REFERENCES  accounts_usuario (id)
                                        ON DELETE   CASCADE,
    CONSTRAINT fk_plansel_resultado     FOREIGN KEY (resultado_id)
                                        REFERENCES  recomendaciones_resultadoml (id)
                                        ON DELETE   SET NULL,
    CONSTRAINT ck_plansel_nombre        CHECK (nombre_plan IN ('Suave', 'Equilibrado', 'Decidido'))
);

COMMENT ON TABLE  recomendaciones_planseleccionado                  IS 'Plan de optimización activo elegido por el usuario. Uno activo por usuario.';
COMMENT ON COLUMN recomendaciones_planseleccionado.gastos_sugeridos IS 'Dict {GASTO_X: valor_optimizado} con los 8 gastos del plan.';


-- ============================================================
--  8. gamificacion_racha
--     Racha de días consecutivos con actividad. 1:1 con usuario.
--     Se crea automáticamente al registrar usuario (signal Django).
-- ============================================================
CREATE TABLE gamificacion_racha (
    id                  BIGSERIAL   NOT NULL,
    usuario_id          BIGINT      NOT NULL,
    dias_consecutivos   INTEGER     NOT NULL    DEFAULT 0,
    racha_maxima        INTEGER     NOT NULL    DEFAULT 0,
    ultimo_registro     DATE,

    CONSTRAINT pk_racha             PRIMARY KEY (id),
    CONSTRAINT uq_racha_usuario     UNIQUE      (usuario_id),
    CONSTRAINT fk_racha_usuario     FOREIGN KEY (usuario_id)
                                    REFERENCES  accounts_usuario (id)
                                    ON DELETE   CASCADE,
    CONSTRAINT ck_racha_dias        CHECK (dias_consecutivos >= 0),
    CONSTRAINT ck_racha_consistencia CHECK (racha_maxima >= dias_consecutivos)
);

COMMENT ON TABLE gamificacion_racha IS 'Racha de días consecutivos. 1:1 con usuario. Se crea via signal.';


-- ============================================================
--  9. gamificacion_logro
--     Catálogo de logros desbloqueables (12 logros).
--     Tabla de referencia — se carga con datos iniciales.
-- ============================================================
CREATE TABLE gamificacion_logro (
    id          BIGSERIAL       NOT NULL,
    codigo      VARCHAR(50)     NOT NULL,
    nombre      VARCHAR(100)    NOT NULL,
    descripcion TEXT            NOT NULL,
    icono       VARCHAR(10)     NOT NULL,
    puntos      SMALLINT        NOT NULL    DEFAULT 10,
    orden       SMALLINT        NOT NULL    DEFAULT 0,

    CONSTRAINT pk_logro         PRIMARY KEY (id),
    CONSTRAINT uq_logro_codigo  UNIQUE      (codigo),
    CONSTRAINT ck_logro_puntos  CHECK (puntos >= 0)
);

COMMENT ON TABLE gamificacion_logro IS 'Catálogo de logros desbloqueables. Tabla estática, 12 registros.';


-- ============================================================
-- 10. gamificacion_logrousuario
--     Logros desbloqueados por usuario (relación N:M).
--     Se inserta desde gamificacion/services.py → _otorgar().
-- ============================================================
CREATE TABLE gamificacion_logrousuario (
    id          BIGSERIAL   NOT NULL,
    usuario_id  BIGINT      NOT NULL,
    logro_id    BIGINT      NOT NULL,
    obtenido_en TIMESTAMPTZ NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_logrousuario          PRIMARY KEY (id),
    CONSTRAINT uq_logro_usuario         UNIQUE      (usuario_id, logro_id),
    CONSTRAINT fk_logrousuario_usuario  FOREIGN KEY (usuario_id)
                                        REFERENCES  accounts_usuario (id)
                                        ON DELETE   CASCADE,
    CONSTRAINT fk_logrousuario_logro    FOREIGN KEY (logro_id)
                                        REFERENCES  gamificacion_logro (id)
                                        ON DELETE   CASCADE
);

COMMENT ON TABLE gamificacion_logrousuario IS 'Logros desbloqueados por usuario. Un logro no se repite (N:M).';


-- ============================================================
-- 11. panel_admin_auditlog
--     Log inmutable de acciones administrativas.
-- ============================================================
CREATE TABLE panel_admin_auditlog (
    id                  BIGSERIAL       NOT NULL,
    admin_id            BIGINT,
    accion              VARCHAR(30)     NOT NULL,
    usuario_objetivo_id BIGINT,
    detalle             TEXT            NOT NULL    DEFAULT '',
    ip_address          VARCHAR(45),
    fecha               TIMESTAMPTZ     NOT NULL    DEFAULT NOW(),

    CONSTRAINT pk_auditlog          PRIMARY KEY (id),
    CONSTRAINT fk_audit_admin       FOREIGN KEY (admin_id)
                                    REFERENCES  accounts_usuario (id)
                                    ON DELETE   SET NULL,
    CONSTRAINT fk_audit_objetivo    FOREIGN KEY (usuario_objetivo_id)
                                    REFERENCES  accounts_usuario (id)
                                    ON DELETE   SET NULL,
    CONSTRAINT ck_audit_accion      CHECK (accion IN (
                                        'LOGIN_ADMIN', 'LOGOUT_ADMIN',
                                        'CREAR_USUARIO', 'VER_USUARIO',
                                        'ACTIVAR_USUARIO', 'DESACTIVAR_USUARIO',
                                        'CAMBIAR_ROL', 'EXPORTAR_DATOS',
                                        'VER_ESTADISTICAS'
                                    ))
);

COMMENT ON TABLE panel_admin_auditlog IS 'Log de auditoría de acciones administrativas. Inmutable.';


-- ============================================================
-- 12-13. Tablas JWT (djangorestframework-simplejwt)
--        Gestionadas automáticamente por Django al hacer migrate.
-- ============================================================
CREATE TABLE token_blacklist_outstandingtoken (
    id          BIGSERIAL       NOT NULL,
    token       TEXT            NOT NULL,
    user_id     BIGINT,
    jti         VARCHAR(255)    NOT NULL    UNIQUE,
    created_at  TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ     NOT NULL,

    CONSTRAINT pk_outstanding_token     PRIMARY KEY (id),
    CONSTRAINT fk_outstanding_user      FOREIGN KEY (user_id)
                                        REFERENCES  accounts_usuario (id)
                                        ON DELETE   CASCADE
);

CREATE TABLE token_blacklist_blacklistedtoken (
    id              BIGSERIAL   NOT NULL,
    blacklisted_at  TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
    token_id        BIGINT      NOT NULL    UNIQUE,

    CONSTRAINT pk_blacklisted_token     PRIMARY KEY (id),
    CONSTRAINT fk_blacklisted_token     FOREIGN KEY (token_id)
                                        REFERENCES  token_blacklist_outstandingtoken (id)
                                        ON DELETE   CASCADE
);

COMMENT ON TABLE token_blacklist_outstandingtoken IS 'Refresh tokens emitidos. Gestionado por simplejwt.';
COMMENT ON TABLE token_blacklist_blacklistedtoken IS 'Tokens invalidados por POST /auth/logout/.';


-- ============================================================
--  ÍNDICES
-- ============================================================
CREATE INDEX idx_usuario_rol            ON accounts_usuario (rol_id);
CREATE INDEX idx_registro_usuario       ON financiero_registromensual (usuario_id);
CREATE INDEX idx_registro_periodo       ON financiero_registromensual (periodo DESC);
-- ResultadoML: índices para historial (usuario+fecha) y métricas (clase Ahorra/Déficit)
CREATE INDEX idx_resultado_usuario      ON recomendaciones_resultadoml (usuario_id);
CREATE INDEX idx_resultado_creado       ON recomendaciones_resultadoml (creado_en DESC);
CREATE INDEX idx_resml_user_fecha       ON recomendaciones_resultadoml (usuario_id, creado_en DESC);
CREATE INDEX idx_resml_clase            ON recomendaciones_resultadoml (label_predicha);
CREATE INDEX idx_metamensual_usuario    ON recomendaciones_metamensual (usuario_id);
CREATE INDEX idx_metalargo_usuario      ON recomendaciones_metalargoplazo (usuario_id);
CREATE INDEX idx_metalargo_activa       ON recomendaciones_metalargoplazo (usuario_id, activa);
-- PlanSeleccionado: lookup por usuario+activo + garantía de un solo plan activo
CREATE INDEX        idx_plansel_user_activo        ON recomendaciones_planseleccionado (usuario_id, activo);
CREATE UNIQUE INDEX unico_plan_activo_por_usuario  ON recomendaciones_planseleccionado (usuario_id) WHERE activo;
CREATE INDEX idx_audit_fecha            ON panel_admin_auditlog (fecha DESC);
CREATE INDEX idx_audit_admin            ON panel_admin_auditlog (admin_id);
CREATE INDEX idx_logrousuario_usuario   ON gamificacion_logrousuario (usuario_id);
CREATE INDEX idx_outstanding_jti        ON token_blacklist_outstandingtoken (jti);


-- ============================================================
--  DATOS INICIALES
-- ============================================================

-- Roles del sistema (2 filas fijas)
INSERT INTO accounts_rol (nombre, descripcion) VALUES
('USUARIO', 'Usuario normal del sistema SIGAMOS. Accede solo a sus propios datos financieros.'),
('ADMIN',   'Administrador del sistema. Gestiona usuarios, métricas y audit log.');

-- Catálogo de logros (12 logros)
INSERT INTO gamificacion_logro (codigo, nombre, descripcion, icono, puntos, orden) VALUES
('PRIMER_REGISTRO',   'Primer Paso',            'Registraste tus primeros ingresos y gastos.',         '🏆', 10,  1),
('RACHA_7',           'Racha de 7 Días',         '7 días consecutivos registrando tus finanzas.',       '🔥', 25,  2),
('RACHA_30',          'Constancia del Mes',      '30 días consecutivos con actividad registrada.',      '⚡', 100, 3),
('PRIMER_ML',         'ML Pioneer',              'Ejecutaste tu primer análisis de Machine Learning.',  '🤖', 50,  4),
('PRIMERA_META',      'Soñador Financiero',      'Creaste tu primera meta de ahorro a largo plazo.',   '🎯', 20,  5),
('META_CUMPLIDA',     'Meta Cumplida',           'Alcanzaste el 100% de una meta de ahorro.',           '🎉', 150, 6),
('AHORRADOR_20',      'Ahorrador Responsable',   'Tasa de ahorro del 20% o más en un mes.',             '💰', 75,  7),
('PERFIL_COMPLETO',   'Perfil Listo',            'Completaste todos los datos de tu perfil financiero.','✅', 15,  8),
('CINCO_REGISTROS',   'Disciplina Financiera',   'Creaste 5 registros mensuales.',                      '📊', 60,  9),
('CLUSTER_AHORRADOR', 'Clasificado Ahorrador',   'El modelo te clasificó como "Ahorra".',               '⭐', 200, 10),
('TRES_MESES_VERDE',  'Tres Meses en Verde',     'Ahorro positivo durante 3 meses consecutivos.',       '🌱', 120, 11),
('MAESTRO_AHORRO',    'Maestro del Ahorro',      'Cumpliste 5 metas de ahorro.',                        '👑', 500, 12);


-- ============================================================
--  RESUMEN DEL ESQUEMA
--
--  Tablas:       13  (11 de negocio + 2 JWT)
--  FK totales:   17
--  Índices:      16  (CREATE INDEX explícitos; incl. 1 único parcial: plan activo)
--  Roles:         2  (USUARIO, ADMIN)
--  Logros:       12
--
--  Cambios v2.2 (migración a XGBoost Classifier — sin K-Means ni regresión):
--  - ✅ recomendaciones_resultadoml: −cluster_id, −cluster_label, −gap
--       +clase_predicha, +label_predicha, +prob_ahorra, +necesita_recortar,
--       +shap_top_features (JSONB), +mes_referencia_id (FK)
--       índice idx_resml_cluster → idx_resml_clase (sobre label_predicha)
--  - ✅ recomendaciones_planseleccionado: nombre_plan
--       'Conservador/Balanceado/Agresivo' → 'Suave/Equilibrado/Decidido'
--  - ✅ gamificacion_logro: logro CLUSTER_AHORRADOR renombrado a "Clasificado
--       Ahorrador" (se otorga cuando el clasificador predice clase 1)
--
--  Cambios v2.1 (respecto a v2.0):
--  - ✅ financiero_registromensual: +bonif_monto (bonificación del mes,
--       integrada como columna; se suma a ing_planilla antes del ML)
--  - ✅ recomendaciones_planseleccionado: tabla documentada (faltaba en v2.0)
--       + índice único parcial 'unico_plan_activo_por_usuario'
--  - 🔧 recomendaciones_metalargoplazoo  → recomendaciones_metalargoplazo (typo)
--  - 🔧 gamificacion_logroupsuario       → gamificacion_logrousuario (typo)
--
--  Relaciones principales:
--    accounts_rol 1───N accounts_usuario
--    accounts_usuario 1───N registromensual / metamensual / metalargoplazo /
--                            resultadoml / planseleccionado / auditlog
--    accounts_usuario 1───1 gamificacion_racha
--    accounts_usuario N───M gamificacion_logro  (via gamificacion_logrousuario)
--    registromensual 1───N resultadoml (registro_id = mes actual, CASCADE)
--    registromensual 1───N resultadoml (mes_referencia_id = mes clasificado, SET NULL)
--    metamensual     1───N resultadoml          (SET NULL)
--    resultadoml     1───N planseleccionado      (SET NULL)
-- ============================================================
