"""SQL for the partition functions (01 §1.2). Revision ``b01_02`` installs them.

Both functions are ``SECURITY DEFINER`` and owned by the migration role, so the maintenance job
(running as ``app_rw``, which cannot create tables) can create and drop partitions, and nothing
else. New partitions copy ``app_rw``'s privileges from their parent, so append-only tables such
as ``ops.audit_log`` stay append-only even when a partition is addressed directly.
"""

from __future__ import annotations

CREATE_RANGE_PARTITIONS = """
CREATE OR REPLACE FUNCTION platform.create_range_partitions(
    parent text, period text, ahead int, start_on date DEFAULT current_date
) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    sch text := split_part(parent, '.', 1);
    tbl text := split_part(parent, '.', 2);
    base date;
    lo date;
    hi date;
    child text;
    created int := 0;
    priv text;
BEGIN
    IF period NOT IN ('day', 'month') THEN
        RAISE EXCEPTION 'period must be day or month, got %', period;
    END IF;
    IF to_regclass(parent) IS NULL THEN
        RAISE EXCEPTION 'no table %', parent;
    END IF;
    base := CASE period WHEN 'day' THEN start_on ELSE date_trunc('month', start_on)::date END;
    FOR i IN 0..ahead LOOP
        IF period = 'day' THEN
            lo := base + i;
            hi := lo + 1;
            child := tbl || '_p' || to_char(lo, 'YYYYMMDD');
        ELSE
            lo := (base + make_interval(months => i))::date;
            hi := (lo + interval '1 month')::date;
            child := tbl || '_p' || to_char(lo, 'YYYYMM');
        END IF;
        IF to_regclass(format('%I.%I', sch, child)) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
                sch, child, sch, tbl, lo, hi
            );
            EXECUTE format('REVOKE ALL ON %I.%I FROM app_rw', sch, child);
            FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
                IF has_table_privilege('app_rw', parent, priv) THEN
                    EXECUTE format('GRANT %s ON %I.%I TO app_rw', priv, sch, child);
                END IF;
            END LOOP;
            created := created + 1;
        END IF;
    END LOOP;
    RETURN created;
END
$fn$;
"""

DROP_PARTITIONS_BEFORE = """
CREATE OR REPLACE FUNCTION platform.drop_partitions_before(parent text, cutoff date)
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    sch text := split_part(parent, '.', 1);
    child record;
    suffix text;
    hi date;
    dropped int := 0;
BEGIN
    -- Defence in depth: audit history is kept at least 3 years whatever the caller asks.
    IF parent = 'ops.audit_log' AND cutoff > (current_date - interval '36 months')::date THEN
        RAISE EXCEPTION 'ops.audit_log partitions are kept for 36 months';
    END IF;
    FOR child IN
        SELECT c.relname FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = to_regclass(parent)
    LOOP
        suffix := substring(child.relname from '_p([0-9]{6,8})$');
        CONTINUE WHEN suffix IS NULL;
        IF length(suffix) = 8 THEN
            hi := to_date(suffix, 'YYYYMMDD') + 1;
        ELSE
            hi := (to_date(suffix, 'YYYYMM') + interval '1 month')::date;
        END IF;
        IF hi <= cutoff THEN
            EXECUTE format('DROP TABLE %I.%I', sch, child.relname);
            dropped := dropped + 1;
        END IF;
    END LOOP;
    RETURN dropped;
END
$fn$;
"""

FUNCTIONS = ("create_range_partitions(text, text, int, date)", "drop_partitions_before(text, date)")


def grant_sql() -> list[str]:
    statements = []
    for signature in FUNCTIONS:
        statements.append(f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC")
        statements.append(f"GRANT EXECUTE ON FUNCTION platform.{signature} TO app_rw")
    return statements


def create_partitions_sql(parent: str, period: str, ahead: int) -> str:
    return f"SELECT platform.create_range_partitions('{parent}', '{period}', {ahead})"
