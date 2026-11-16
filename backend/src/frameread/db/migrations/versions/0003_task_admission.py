from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    common = """
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        deleted_at timestamptz,
        version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
    """
    op.execute(f"""CREATE TABLE tasks ({common},
        kind text NOT NULL CHECK (kind IN ('video','qa','export','probe')),
        pool text NOT NULL CHECK (pool IN ('video','qa','utility')),
        intent text NOT NULL CHECK (intent IN ('new','reinterpret','retry')),
        status text NOT NULL CHECK (status IN
            ('queued','running','cancel_requested','retry_wait','succeeded','failed','canceled')),
        stage text,
        accepted_instance_epoch uuid NOT NULL,
        operation_scope text NOT NULL,
        idempotency_key uuid NOT NULL,
        request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{{64}}$'),
        effective_input_json jsonb NOT NULL,
        input_hash char(64) NOT NULL CHECK (input_hash ~ '^[0-9a-f]{{64}}$'),
        retry_of_task_id uuid REFERENCES tasks(id) ON DELETE RESTRICT,
        deadline_at timestamptz NOT NULL,
        not_before_at timestamptz NOT NULL,
        admission_class text NOT NULL CHECK (admission_class IN ('execution','waiting')),
        dispatch_generation integer NOT NULL CHECK (dispatch_generation > 0),
        attempt_no integer NOT NULL CHECK (attempt_no >= 0),
        fence bigint NOT NULL CHECK (fence >= 0),
        lease_token uuid,
        lease_until timestamptz,
        worker_id text,
        cancel_requested_at timestamptz,
        state_revision bigint NOT NULL CHECK (state_revision > 0),
        event_seq bigint NOT NULL CHECK (event_seq > 0),
        progress_json jsonb NOT NULL,
        budget_json jsonb NOT NULL,
        reserved_usage_json jsonb NOT NULL,
        known_usage_json jsonb NOT NULL,
        result_json jsonb,
        error_json jsonb,
        restore_original_json jsonb,
        UNIQUE(operation_scope, idempotency_key)
    )""")
    op.execute(f"""CREATE TABLE task_outbox ({common},
        task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        instance_epoch uuid NOT NULL,
        generation integer NOT NULL CHECK (generation > 0),
        queue text NOT NULL,
        available_at timestamptz NOT NULL,
        claim_token uuid,
        claim_until timestamptz,
        delivery_status text NOT NULL CHECK (delivery_status IN
            ('pending','blocked','claimed','published','superseded')),
        publish_attempts integer NOT NULL CHECK (publish_attempts >= 0),
        delivered_at timestamptz,
        last_error_code text,
        last_publish_at timestamptz,
        UNIQUE(task_id, generation)
    )""")
    op.execute(f"""CREATE TABLE task_events ({common},
        task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        seq bigint NOT NULL CHECK (seq > 0),
        state_revision bigint NOT NULL CHECK (state_revision > 0),
        instance_epoch uuid NOT NULL,
        event_type text NOT NULL CHECK (event_type IN
            ('accepted','claimed','stage_completed','cancel_requested','requeued','retry_wait',
             'succeeded','failed','canceled')),
        payload_json jsonb NOT NULL,
        occurred_at timestamptz NOT NULL,
        UNIQUE(task_id, seq)
    )""")
    op.execute(f"""CREATE TABLE resource_slots ({common},
        resource_key text NOT NULL,
        slot_no integer NOT NULL CHECK (slot_no >= 1),
        assigned_task_id uuid REFERENCES tasks(id) ON DELETE RESTRICT,
        assigned_fence bigint,
        owner_token uuid,
        lease_until timestamptz,
        slot_state text NOT NULL CHECK (slot_state IN ('active','retired')),
        UNIQUE(resource_key, slot_no),
        CHECK ((assigned_task_id IS NULL) = (assigned_fence IS NULL))
    )""")
    op.execute("CREATE INDEX tasks_schedule_idx ON tasks (pool,status,not_before_at,created_at,id)")
    op.execute("CREATE INDEX tasks_history_idx ON tasks (created_at DESC,id DESC)")
    op.execute("CREATE INDEX tasks_lease_idx ON tasks (lease_until) WHERE status IN ('running','cancel_requested')")
    op.execute(
        "CREATE INDEX tasks_deadline_idx ON tasks (deadline_at) "
        "WHERE status IN ('queued','running','cancel_requested','retry_wait')"
    )
    op.execute("CREATE INDEX outbox_available_idx ON task_outbox (available_at,id) WHERE delivery_status = 'pending'")
    op.execute("CREATE INDEX task_events_retention_idx ON task_events (occurred_at)")
    for table in ("tasks", "task_outbox", "resource_slots"):
        op.execute(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION frameread_touch_updated_at()"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO frameread_app")
    op.execute("""CREATE FUNCTION frameread_event_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'task events are immutable' USING ERRCODE = '55000';
        END $$""")
    op.execute(
        "CREATE TRIGGER task_events_immutable BEFORE UPDATE ON task_events "
        "FOR EACH ROW EXECUTE FUNCTION frameread_event_immutable()"
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON task_events TO frameread_app")


def downgrade() -> None:
    raise NotImplementedError
