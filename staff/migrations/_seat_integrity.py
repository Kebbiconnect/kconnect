"""Migration-owned write guard: preserve old duplicates, reject new occupied seats.

No member rows are modified. Keep this helper stable for historical migrations.
"""
INDEX_NAMES = (
    'unique_verified_state_seat', 'unique_verified_zonal_seat',
    'unique_verified_lga_seat', 'unique_verified_ward_seat',
)
PG_TRIGGER = 'kpn_verified_seat_guard'
PG_FUNCTION = 'kpn_guard_verified_seat'
SQLITE_TRIGGERS = ('kpn_verified_seat_insert_guard', 'kpn_verified_seat_update_guard')


def install_guard(apps, schema_editor):
    q = schema_editor.quote_name
    user_table = q(apps.get_model('staff', 'User')._meta.db_table)
    role_table = q(apps.get_model('leadership', 'RoleDefinition')._meta.db_table)
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(f'LOCK TABLE {user_table} IN SHARE ROW EXCLUSIVE MODE')
    for name in INDEX_NAMES:
        schema_editor.execute(f'DROP INDEX IF EXISTS {q(name)}')
    active = "NEW.status = 'VERIFIED' AND NEW.role_definition_id IS NOT NULL AND NEW.role IN ('STATE','ZONAL','LGA','WARD')"
    occupied = f"""SELECT 1 FROM {user_table} u
        WHERE u.id <> NEW.id AND u.status = 'VERIFIED'
          AND u.role = NEW.role AND u.role_definition_id = NEW.role_definition_id
          AND (NEW.role = 'STATE'
            OR (NEW.role = 'ZONAL' AND u.zone_id = NEW.zone_id)
            OR (NEW.role = 'LGA' AND u.lga_id = NEW.lga_id)
            OR (NEW.role = 'WARD' AND u.ward_id = NEW.ward_id))"""
    if vendor == 'postgresql':
        same = """OLD.status = 'VERIFIED' AND OLD.role = NEW.role
            AND OLD.role_definition_id IS NOT DISTINCT FROM NEW.role_definition_id
            AND (NEW.role = 'STATE'
              OR (NEW.role = 'ZONAL' AND OLD.zone_id IS NOT DISTINCT FROM NEW.zone_id)
              OR (NEW.role = 'LGA' AND OLD.lga_id IS NOT DISTINCT FROM NEW.lga_id)
              OR (NEW.role = 'WARD' AND OLD.ward_id IS NOT DISTINCT FROM NEW.ward_id))"""
        schema_editor.execute(f"""CREATE OR REPLACE FUNCTION {q(PG_FUNCTION)}()
            RETURNS trigger LANGUAGE plpgsql VOLATILE SET search_path FROM CURRENT AS $guard$
            BEGIN
              IF NOT ({active}) THEN RETURN NEW; END IF;
              IF TG_OP = 'UPDATE' THEN
                IF {same} THEN RETURN NEW; END IF;
              END IF;
              -- All contenders for this role definition serialize before the
              -- occupancy query. VOLATILE queries see the committed winner.
              PERFORM 1 FROM {role_table} WHERE id = NEW.role_definition_id FOR UPDATE;
              IF EXISTS ({occupied}) THEN
                RAISE EXCEPTION USING ERRCODE = '23505',
                  MESSAGE = 'This verified leadership seat is already occupied.',
                  CONSTRAINT = 'kpn_verified_seat_guard';
              END IF;
              RETURN NEW;
            END;
            $guard$""")
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {q(PG_TRIGGER)} ON {user_table}')
        schema_editor.execute(f"""CREATE TRIGGER {q(PG_TRIGGER)} BEFORE INSERT OR
            UPDATE OF status, role, role_definition_id, zone_id, lga_id, ward_id
            ON {user_table} FOR EACH ROW EXECUTE FUNCTION {q(PG_FUNCTION)}()""")
    elif vendor == 'sqlite':
        same = """OLD.status = 'VERIFIED' AND OLD.role = NEW.role
            AND OLD.role_definition_id IS NEW.role_definition_id
            AND (NEW.role = 'STATE'
              OR (NEW.role = 'ZONAL' AND OLD.zone_id IS NEW.zone_id)
              OR (NEW.role = 'LGA' AND OLD.lga_id IS NEW.lga_id)
              OR (NEW.role = 'WARD' AND OLD.ward_id IS NEW.ward_id))"""
        for name in SQLITE_TRIGGERS:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {q(name)}')
        schema_editor.execute(f"""CREATE TRIGGER {q(SQLITE_TRIGGERS[0])}
            BEFORE INSERT ON {user_table}
            WHEN ({active}) AND EXISTS ({occupied})
            BEGIN SELECT RAISE(ABORT, 'This verified leadership seat is already occupied.'); END""")
        schema_editor.execute(f"""CREATE TRIGGER {q(SQLITE_TRIGGERS[1])}
            BEFORE UPDATE OF status, role, role_definition_id, zone_id, lga_id, ward_id ON {user_table}
            WHEN ({active}) AND NOT ({same}) AND EXISTS ({occupied})
            BEGIN SELECT RAISE(ABORT, 'This verified leadership seat is already occupied.'); END""")
    else:
        raise RuntimeError('Verified-seat compatibility guard supports PostgreSQL and SQLite only.')


def remove_guard(apps, schema_editor):
    q = schema_editor.quote_name
    if schema_editor.connection.vendor == 'postgresql':
        table = q(apps.get_model('staff', 'User')._meta.db_table)
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {q(PG_TRIGGER)} ON {table}')
        schema_editor.execute(f'DROP FUNCTION IF EXISTS {q(PG_FUNCTION)}()')
    elif schema_editor.connection.vendor == 'sqlite':
        for name in SQLITE_TRIGGERS:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {q(name)}')


def guard_is_installed(connection, table):
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute('SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname=%s AND tgrelid=%s::regclass AND NOT tgisinternal)', [PG_TRIGGER, table])
            return cursor.fetchone()[0]
        if connection.vendor == 'sqlite':
            cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=%s", [table])
            return set(SQLITE_TRIGGERS).issubset({r[0] for r in cursor.fetchall()})
    return False
