from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS "gamificacion_logroupsuario" (
                    "id"          BIGSERIAL    NOT NULL PRIMARY KEY,
                    "usuario_id"  BIGINT       NOT NULL,
                    "logro_id"    BIGINT       NOT NULL,
                    "obtenido_en" TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_logroupsuario_usuario_logro UNIQUE ("usuario_id", "logro_id"),
                    CONSTRAINT fk_logroupsuario_usuario FOREIGN KEY ("usuario_id")
                        REFERENCES "accounts_usuario" ("id") ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                    CONSTRAINT fk_logroupsuario_logro FOREIGN KEY ("logro_id")
                        REFERENCES "gamificacion_logro" ("id") ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
                );
            """,
            reverse_sql='DROP TABLE IF EXISTS "gamificacion_logroupsuario";',
        ),
    ]
