class LegacyRouter:
    """
    Keeps the 'legacy' database connection (the old PHP app's live MySQL
    database) strictly read-only and isolated from Django's own migration
    system. It exists for exactly one purpose: the `import_legacy_data`
    management command reads from it with raw SQL. No Django model is ever
    registered against it, so there's nothing for this router to route —
    it just refuses migrations on that alias as a hard safety rail in case
    a future model ever accidentally targets it.
    """

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == 'legacy':
            return False
        return db == 'default'
