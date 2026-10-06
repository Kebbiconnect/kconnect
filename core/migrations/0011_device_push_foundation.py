"""
Add the Android push-notification foundation without duplicating schema.

Some deployed databases already contain these objects from a short-lived
development migration whose filename was later replaced. Django therefore
doesn't always have a matching migration record. These operations adopt an
existing column/table/index, or create it when genuinely absent.
"""

from django.db import migrations, models
import django.db.models.deletion


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        field = model._meta.get_field(self.name)
        with schema_editor.connection.cursor() as cursor:
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(
                    cursor, model._meta.db_table
                )
            }
        if field.column not in columns:
            super().database_forwards(
                app_label, schema_editor, from_state, to_state
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Never delete a production column that this compatibility operation
        # may merely have adopted.
        return


class CreateModelIfMissing(migrations.CreateModel):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if model._meta.db_table not in (
            schema_editor.connection.introspection.table_names()
        ):
            super().database_forwards(
                app_label, schema_editor, from_state, to_state
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        return


class AddIndexIfMissing(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(
                cursor, model._meta.db_table
            )
        if self.index.name not in constraints:
            super().database_forwards(
                app_label, schema_editor, from_state, to_state
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_patron_model"),
        ("staff", "0013_user_is_trusted_reporter_user_reporter_level"),
    ]

    operations = [
        AddFieldIfMissing(
            model_name="notification",
            name="event",
            field=models.CharField(
                db_index=True,
                default="INFO",
                help_text="Stable machine-readable workflow event",
                max_length=50,
            ),
        ),
        CreateModelIfMissing(
            name="DeviceRegistration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("token", models.CharField(max_length=512, unique=True)),
                ("device_id", models.CharField(blank=True, max_length=200)),
                (
                    "platform",
                    models.CharField(
                        choices=[("ANDROID", "Android")],
                        default="ANDROID",
                        max_length=20,
                    ),
                ),
                ("app_version", models.CharField(blank=True, max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="devices",
                        to="staff.user",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        CreateModelIfMissing(
            name="PushDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SENT", "Sent"),
                            ("FAILED", "Failed"),
                            ("INVALID", "Invalid token"),
                        ],
                        default="PENDING",
                        max_length=10,
                    ),
                ),
                ("provider_message_id", models.CharField(blank=True, max_length=300)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="core.deviceregistration",
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_deliveries",
                        to="core.notification",
                    ),
                ),
            ],
        ),
        AddIndexIfMissing(
            model_name="deviceregistration",
            index=models.Index(
                fields=["user", "is_active"], name="device_user_active_idx"
            ),
        ),
    ]
