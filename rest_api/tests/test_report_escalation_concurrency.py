"""Local PostgreSQL race regression for report escalation; no provider acceptance."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.test import TransactionTestCase
from django.db import connection,connections
from leadership.models import Zone,LGA,Ward,RoleDefinition
from staff.models import User
from core.models import Report
from core.services.reports import escalate_report,ReportWorkflowError

class ReportEscalationConcurrencyTests(TransactionTestCase):
    def test_one_child_for_two_concurrent_manual_escalations(self):
        if connection.vendor!='postgresql':self.skipTest('Requires PostgreSQL row locks.')
        z=Zone.objects.create(name='Isolated race zone');l=LGA.objects.create(name='Isolated race LGA',zone=z);w=Ward.objects.create(name='Isolated race ward',lga=l)
        roles={title:RoleDefinition.objects.create(title=title,tier=tier,seat_number=1) for title,tier in [('Ward Community Lead','WARD'),('LGA Network Lead','LGA'),('Senatorial Director','ZONAL')]}
        ward=User.objects.create_user(username='isolated_race_ward',phone='race-ward',role='WARD',status='VERIFIED',role_definition=roles['Ward Community Lead'],zone=z,lga=l,ward=w)
        lead=User.objects.create_user(username='isolated_race_lga',phone='race-lga',role='LGA',status='VERIFIED',role_definition=roles['LGA Network Lead'],zone=z,lga=l)
        User.objects.create_user(username='isolated_race_zone',phone='race-zone',role='ZONAL',status='VERIFIED',role_definition=roles['Senatorial Director'],zone=z)
        report=Report.objects.create(title='Isolated race report',content='Local fixture',report_type='WARD_TO_LGA',submitted_by=ward,submitted_to=lead,status='APPROVED')
        barrier=Barrier(2)
        def escalate(_):
            try:
                stale=Report.objects.get(pk=report.pk);actor=User.objects.get(pk=lead.pk);barrier.wait(timeout=10);escalate_report(stale,actor);return 'escalated'
            except ReportWorkflowError as exc:return exc.code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(escalate,[1,2]))
        self.assertCountEqual(outcomes,['escalated','not_escalatable']);self.assertEqual(Report.objects.filter(parent_report=report).count(),1)
