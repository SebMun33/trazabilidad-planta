"""Los modelos del kiosco viven solo en la base `local` (SQLite); el resto, en `default`."""

LOCAL = "local"


class KioscoRouter:
    app = "kiosco"

    def db_for_read(self, model, **hints):
        return LOCAL if model._meta.app_label == self.app else None

    db_for_write = db_for_read

    def allow_relation(self, obj1, obj2, **hints):
        locales = {obj1._meta.app_label == self.app, obj2._meta.app_label == self.app}
        return None if len(locales) == 1 else False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.app:
            return db == LOCAL
        return db != LOCAL
