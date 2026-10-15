"""Seat compatibility regressions; run only against a disposable test database."""
from contextlib import contextmanager
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.apps import apps
from django.test import TransactionTestCase,override_settings
from django.db import connection,connections,transaction,IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO
from staff.models import User
from leadership.models import RoleDefinition,Zone,LGA,Ward
from staff.services.member_admin import decide_application,MemberDecisionError
from staff.migrations._seat_integrity import install_guard,remove_guard,guard_is_installed,INDEX_NAMES

@contextmanager
def without_guard():
    with connection.schema_editor() as editor:remove_guard(apps,editor)
    try:yield
    finally:
        with connection.schema_editor() as editor:install_guard(apps,editor)

class LegacyMigrationTests(TransactionTestCase):
    reset_sequences=True
    def test_pending_0014_upgrade_preserves_all_seven_duplicate_groups(self):
        executor=MigrationExecutor(connection);latest=executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([('staff','0013_user_is_trusted_reporter_user_reporter_level')])
            old=executor.loader.project_state([('staff','0013_user_is_trusted_reporter_user_reporter_level')]).apps
            U=old.get_model('staff','User');Z=old.get_model('leadership','Zone');L=old.get_model('leadership','LGA');W=old.get_model('leadership','Ward');R=old.get_model('leadership','RoleDefinition')
            z=Z.objects.create(name='Isolated legacy zone');l=L.objects.create(name='Isolated legacy LGA',zone=z);w=W.objects.create(name='Isolated legacy ward',lga=l)
            specs=[('ZONAL','Senatorial Director'),('LGA','LGA Member Support Officer'),('LGA','LGA Monitoring Officer'),('WARD','Ward Finance Officer'),('WARD','Ward Communications Officer'),('WARD','Ward Community Lead'),('WARD','Ward Monitoring Officer')]
            ids=[]
            for i,(tier,title) in enumerate(specs):
                role=R.objects.create(title=title,tier=tier,seat_number=i+1)
                for n in range(2):
                    u=U.objects.create(username=f'isolated_legacy_{i}_{n}',phone=f'isolated-{i}-{n}',role=tier,status='VERIFIED',role_definition=role,zone=z,lga=l,ward=w,password='unusable-test-password',bio='Retained history',is_active=True)
                    ids.append(u.pk)
            columns=[f.column for f in U._meta.local_fields]
            with connection.cursor() as cur:
                names=','.join(connection.ops.quote_name(c) for c in columns)
                cur.execute(f'SELECT {names} FROM {connection.ops.quote_name(U._meta.db_table)} ORDER BY id');before=cur.fetchall()
            executor=MigrationExecutor(connection);executor.migrate(latest)
            with connection.cursor() as cur:
                cur.execute(f'SELECT {names} FROM {connection.ops.quote_name(U._meta.db_table)} ORDER BY id');after=cur.fetchall()
            self.assertEqual(before,after);self.assertEqual(User.objects.filter(pk__in=ids,status='VERIFIED',is_active=True).count(),14)
            self.assertTrue(guard_is_installed(connection,User._meta.db_table))
            u=User.objects.get(pk=ids[0]);u.archive_reason='New archive fields are usable';u.save(update_fields=['archive_reason']);u.refresh_from_db();self.assertEqual(u.archive_reason,'New archive fields are usable')
            a=User.objects.get(pk=ids[0])
            with self.assertRaises(IntegrityError),transaction.atomic():
                User.objects.create(username='isolated_third',phone='third',role=a.role,status='VERIFIED',role_definition=a.role_definition,zone=a.zone,lga=a.lga,ward=a.ward)
        finally:MigrationExecutor(connection).migrate(latest)

class GuardTests(TransactionTestCase):
    def setUp(self):
        self.z=Zone.objects.create(name='Isolated guard zone');self.z2=Zone.objects.create(name='Isolated other zone');self.l=LGA.objects.create(name='Isolated guard LGA',zone=self.z);self.w=Ward.objects.create(name='Isolated guard ward',lga=self.l)
        self.r=RoleDefinition.objects.create(title='Ward Community Lead',tier='WARD',seat_number=1)
    def user(self,name,**kw):
        data=dict(username=name,phone=sha256(name.encode()).hexdigest()[:20],role='WARD',status='VERIFIED',role_definition=self.r,zone=self.z,lga=self.l,ward=self.w);data.update(kw);return User.objects.create(**data)
    def duplicates(self):
        with without_guard():return self.user('isolated_old_a'),self.user('isolated_old_b')
    def test_existing_duplicate_profile_and_active_updates_allowed(self):
        a,b=self.duplicates();a.bio='Updated biography';a.save();User.objects.filter(pk=b.pk).update(is_active=False);self.assertEqual(User.objects.get(pk=a.pk).bio,'Updated biography')
    def test_model_validation_allows_unchanged_legacy_assignment(self):
        a,b=self.duplicates();a.bio='Retained member edits';a.clean()
    def test_model_validation_rejects_new_occupied_assignment(self):
        from django.core.exceptions import ValidationError
        self.duplicates();a=self.user('model_pending',status='PENDING');a.status='VERIFIED'
        with self.assertRaises(ValidationError):a.clean()
    def test_new_verified_insert_blocked_for_each_tier(self):
        for tier in ['STATE','ZONAL','LGA','WARD']:
            role=RoleDefinition.objects.create(title='Isolated '+tier,tier=tier,seat_number=19)
            self.user('holder_'+tier,role=tier,role_definition=role)
            with self.subTest(tier=tier),self.assertRaises(IntegrityError),transaction.atomic():self.user('new_'+tier,role=tier,role_definition=role)
    def test_bulk_update_to_verified_cannot_join_legacy_duplicate_seat(self):
        self.duplicates();a=self.user('isolated_pending',status='PENDING')
        with self.assertRaises(IntegrityError),transaction.atomic():User.objects.filter(pk=a.pk).update(status='VERIFIED')
        a.refresh_from_db();self.assertEqual(a.status,'PENDING')
    def test_assignment_from_null_role_definition_cannot_bypass_guard(self):
        self.duplicates();a=self.user('isolated_unassigned',role_definition=None)
        with self.assertRaises(IntegrityError),transaction.atomic():User.objects.filter(pk=a.pk).update(role_definition=self.r)
    def test_reinstatement_cannot_join_occupied_legacy_seat(self):
        a,b=self.duplicates();User.objects.filter(pk=b.pk).update(status='SUSPENDED')
        with self.assertRaises(IntegrityError),transaction.atomic():User.objects.filter(pk=b.pk).update(status='VERIFIED')
    def test_move_from_legacy_seat_to_vacant_role_allowed(self):
        a,b=self.duplicates();r=RoleDefinition.objects.create(title='Ward Communications Officer',tier='WARD',seat_number=2)
        User.objects.filter(pk=a.pk).update(role_definition=r);a.refresh_from_db();self.assertEqual(a.role_definition_id,r.pk);b.refresh_from_db();self.assertEqual(b.role_definition_id,self.r.pk)
    def test_move_to_existing_other_seat_blocked(self):
        a,b=self.duplicates();r=RoleDefinition.objects.create(title='Ward Monitoring Officer',tier='WARD',seat_number=3);self.user('isolated_other_holder',role_definition=r)
        with self.assertRaises(IntegrityError),transaction.atomic():User.objects.filter(pk=a.pk).update(role_definition=r)
    def test_same_zonal_role_in_other_zone_allowed(self):
        r=RoleDefinition.objects.create(title='Senatorial Director',tier='ZONAL',seat_number=1);self.user('zone1',role='ZONAL',role_definition=r);self.user('zone2',role='ZONAL',role_definition=r,zone=self.z2)
    def test_pending_registration_in_occupied_seat_preserved(self):
        self.duplicates();a=self.user('pending_in_occupied_seat',status='PENDING');self.assertEqual(a.status,'PENDING')
    def test_server_approval_rejects_occupied_legacy_seat(self):
        self.duplicates();p=RoleDefinition.objects.create(title='President',tier='STATE',seat_number=1);actor=self.user('isolated_president',role='STATE',role_definition=p);a=self.user('isolated_applicant',status='PENDING')
        with self.assertRaises(MemberDecisionError) as err:decide_application(actor,a.pk,'approve')
        self.assertEqual(err.exception.code,'seat_filled');a.refresh_from_db();self.assertEqual(a.status,'PENDING')
    def test_install_guard_is_idempotent(self):
        self.duplicates()
        for _ in range(2):
            with connection.schema_editor() as editor:install_guard(apps,editor)
        self.assertTrue(guard_is_installed(connection,User._meta.db_table));self.assertEqual(User.objects.count(),2)
    def test_original_0014_already_applied_indexes_can_be_adopted(self):
        self.user('original_strict_holder')
        with connection.schema_editor() as editor:
            remove_guard(apps,editor)
            editor.execute("CREATE UNIQUE INDEX unique_verified_ward_seat ON staff_user(role_definition_id,ward_id) WHERE status='VERIFIED' AND role='WARD' AND role_definition_id IS NOT NULL")
            install_guard(apps,editor)
        self.assertTrue(guard_is_installed(connection,User._meta.db_table));self.assertEqual(User.objects.count(),1)
    def test_concurrent_direct_orm_verifications_have_only_one_winner(self):
        if connection.vendor!='postgresql':self.skipTest('Real PostgreSQL locking test')
        a=self.user('race_a',status='PENDING');b=self.user('race_b',status='PENDING');barrier=Barrier(2)
        def worker(pk):
            connections['default'].close()
            try:
                with transaction.atomic():
                    barrier.wait(timeout=10);User.objects.filter(pk=pk).update(status='VERIFIED')
                return 'verified'
            except IntegrityError:return 'blocked'
            finally:connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[a.pk,b.pk]))
        self.assertEqual(sorted(results),['blocked','verified']);self.assertEqual(User.objects.filter(status='VERIFIED').count(),1)

@override_settings(IS_PRODUCTION=True,EMAIL_BACKEND='staff.lockally_backend.LockallyEmailBackend',LOCKALLY_API_KEY='isolated',LOCKALLY_API_URL='https://example.invalid/send',LOCKALLY_FROM_EMAIL='sender@example.invalid',TELEGRAM_BOT_TOKEN='isolated',TELEGRAM_WEBHOOK_SECRET='isolated')
class PreflightTests(TransactionTestCase):
    def test_existing_duplicates_warn_without_mutation(self):
        r=RoleDefinition.objects.create(title='President',tier='STATE',seat_number=1)
        with without_guard():
            for i in range(2):User.objects.create(username=f'legacy_warning_{i}',phone=str(i),role='STATE',status='VERIFIED',role_definition=r)
        out=StringIO();call_command('check_release',database=True,stdout=out);self.assertIn('retained unchanged',out.getvalue());self.assertEqual(User.objects.count(),2)
    def test_missing_guard_still_blocks_post_migration_deployment(self):
        with without_guard(),self.assertRaises(CommandError):call_command('check_release',database=True,stdout=StringIO())
    def test_invalid_tier_still_blocks_deployment(self):
        r=RoleDefinition.objects.create(title='Ward Community Lead',tier='WARD',seat_number=1);User.objects.create(username='bad_tier',phone='bad',role='GENERAL',status='PENDING',role_definition=r)
        with self.assertRaises(CommandError):call_command('check_release',database=True,stdout=StringIO())
