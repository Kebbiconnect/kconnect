"""Local API lifecycle acceptance. NOT production/provider/device certification."""
import io, tempfile, shutil
from datetime import timedelta
from PIL import Image
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from leadership.models import Zone,LGA,Ward,RoleDefinition
from leadership.roles import ROLES_BY_TIER
from staff.models import User,DisciplinaryAction
from core.models import Report,Notification
from rest_api.models import DeviceRegistration
from donations.models import Donation

class LifecycleAcceptanceTests(TestCase):
    def setUp(self):
        self.temp=tempfile.mkdtemp(prefix='kpn-local-acceptance-');self.storage=override_settings(MEDIA_ROOT=self.temp);self.storage.enable()
        self.z=Zone.objects.create(name='Synthetic acceptance zone');self.l=LGA.objects.create(name='Synthetic acceptance LGA',zone=self.z);self.w=Ward.objects.create(name='Synthetic acceptance ward',lga=self.l)
        self.z2=Zone.objects.create(name='Synthetic other zone');self.l2=LGA.objects.create(name='Synthetic other LGA',zone=self.z2);self.w2=Ward.objects.create(name='Synthetic other ward',lga=self.l2)
        self.c=APIClient();self.users={}
        titles=['President','Director of Media & Communications','Director of Finance','Finance Operations Officer','Director of Audit & Accountability','Director of Legal Affairs & Ethics','Director of Monitoring & Compliance','Director of Programmes & Events','General Secretary','Director of Women\'s Development','Director of Youth Development','Director of Member Support & Welfare','Director of Public Relations & Partnerships','Assistant General Secretary','Senatorial Director','LGA Network Lead','Ward Community Lead','Ward Communications Officer']
        for n,title in enumerate(titles):
            tier=next(t for t,roles in ROLES_BY_TIER.items() if title in roles)
            rd,_=RoleDefinition.objects.get_or_create(tier=tier,title=title,defaults={'seat_number':ROLES_BY_TIER[tier].index(title)+1})
            scope={} if tier=='STATE' else {'zone':self.z} if tier=='ZONAL' else {'zone':self.z,'lga':self.l} if tier=='LGA' else {'zone':self.z,'lga':self.l,'ward':self.w}
            self.users[title]=User.objects.create_user(username=f'acceptance_{n}',password='LocalOnly-Lifecycle-942!',email=f'acceptance{n}@example.invalid',phone=f'isolated-{n}',role=tier,status='VERIFIED',role_definition=rd,**scope)
        self.member=User.objects.create_user(username='acceptance_member',password='LocalOnly-Lifecycle-942!',email='member@example.invalid',phone='isolated-member',role='GENERAL',status='VERIFIED',zone=self.z,lga=self.l,ward=self.w)
        self.other=User.objects.create_user(username='acceptance_other',password='LocalOnly-Lifecycle-942!',phone='isolated-other',role='GENERAL',status='VERIFIED',zone=self.z2,lga=self.l2,ward=self.w2)
        self.as_role('Director of Media & Communications')
    def tearDown(self):self.storage.disable();shutil.rmtree(self.temp,ignore_errors=True)
    def as_role(self,title):self.c.force_authenticate(self.users[title])
    def request(self,method,path,data=None,status=200,fmt='json'):
        r=getattr(self.c,method)('/api/v1/'+path,data,format=fmt) if data is not None else getattr(self.c,method)('/api/v1/'+path)
        self.assertEqual(r.status_code,status,getattr(r,'data',r.content[:300]));return getattr(r,'data',None)
    def image(self,name='isolated.png'):
        out=io.BytesIO();Image.new('RGB',(16,16),'green').save(out,'PNG');return SimpleUploadedFile(name,out.getvalue(),content_type='image/png')
    def test_registration_approval_login_refresh_logout_lifecycle(self):
        rd,_=RoleDefinition.objects.get_or_create(tier='LGA',title='LGA Administrative Officer',defaults={'seat_number':2})
        self.c.force_authenticate(None)
        data=self.request('post','auth/register/',{'username':'isolated_signup','password':'LocalOnly-Registration-942!','password_confirm':'LocalOnly-Registration-942!','email':'signup@example.invalid','first_name':'Isolated','last_name':'Signup','phone':'isolated-signup','gender':'M','photo':self.image(),'zone':self.z.pk,'lga':self.l.pk,'role_definition':rd.pk},201,'multipart')
        self.assertEqual(data['status'],'PENDING');self.as_role('President');self.request('post',f"members/{data['id']}/decision/",{'decision':'approve'})
        self.c.force_authenticate(None);tokens=self.request('post','auth/login/',{'username':'isolated_signup','password':'LocalOnly-Registration-942!'})
        self.c.credentials(HTTP_AUTHORIZATION='Bearer '+tokens['access']);me=self.request('get','auth/me/');self.assertEqual(me['status'],'VERIFIED')
        rotated=self.request('post','auth/refresh/',{'refresh':tokens['refresh']});self.assertIn('access',rotated)
        self.request('post','auth/logout/',{'refresh':rotated['refresh']},204);self.request('post','auth/refresh/',{'refresh':rotated['refresh']},401)
    def test_password_reset_local_delivery_and_new_login(self):
        from django.core import mail
        import re
        self.c.force_authenticate(None);self.request('post','auth/password-reset/',{'email':self.member.email})
        match=re.search(r'/account/reset-password/([^/]+)/([^/]+)/',mail.outbox[-1].body);self.assertIsNotNone(match)
        self.request('post','auth/password-reset/confirm/',{'uid':match[1],'token':match[2],'new_password':'Changed-Local-Password-942!'})
        self.request('post','auth/login/',{'username':self.member.username,'password':'Changed-Local-Password-942!'})
        self.request('post','auth/password-reset/confirm/',{'uid':match[1],'token':match[2],'new_password':'Another-Local-Password-942!'},400)
    def test_rejection_archives_auth_denies_and_record_survives(self):
        u=User.objects.create_user(username='isolated_pending',phone='isolated-pending',role='LGA',status='PENDING',role_definition=self.users['LGA Network Lead'].role_definition,zone=self.z,lga=self.l)
        self.as_role('President');self.request('post',f'members/{u.pk}/decision/',{'decision':'reject','reason':'Isolated acceptance rejection'})
        u.refresh_from_db();self.assertFalse(u.is_active);self.assertIsNotNone(u.archived_at);self.assertEqual(u.archive_reason,'Isolated acceptance rejection')
        self.request('post',f'members/{u.pk}/decision/',{'decision':'approve'},400)
    def test_member_suspend_reinstate_and_dismiss(self):
        self.as_role('President')
        for action,status in [('suspend','SUSPENDED'),('reinstate','VERIFIED'),('dismiss','SUSPENDED')]:
            self.request('post',f'members/{self.member.pk}/administration/',{'action':action,'reason':'Isolated acceptance action'});self.member.refresh_from_db();self.assertEqual(self.member.status,status)
        self.assertFalse(self.member.is_active)
    def test_member_role_edit_and_swap(self):
        self.as_role('President');a=self.users['Ward Community Lead'];b=self.users['Ward Communications Officer'];old_a=a.role_definition_id;old_b=b.role_definition_id
        self.request('post',f'members/{a.pk}/administration/',{'action':'swap','member2':b.pk});a.refresh_from_db();b.refresh_from_db();self.assertEqual((a.role_definition_id,b.role_definition_id),(old_b,old_a))
        rd,_=RoleDefinition.objects.get_or_create(tier='LGA',title='LGA Administrative Officer',defaults={'seat_number':2})
        self.request('post',f'members/{self.member.pk}/administration/',{'action':'edit_role','role_definition':rd.pk,'zone':self.z.pk,'lga':self.l.pk});self.member.refresh_from_db();self.assertEqual(self.member.role,'LGA')
    def test_reports_complete_hierarchical_escalation(self):
        self.as_role('Ward Community Lead');self.request('get','reports/recipient/')
        r=self.request('post','reports/',{'title':'Isolated ward report','content':'Local acceptance content','period':'Synthetic period'},201)
        self.as_role('LGA Network Lead');review=self.request('post',f"reports/{r['id']}/review/",{'action':'approve','notes':'Isolated review'});child=review['escalated_report'];self.assertIsNotNone(child);self.assertEqual(child['report_type'],'LGA_TO_ZONAL')
        self.as_role('Senatorial Director');review=self.request('post',f"reports/{child['id']}/review/",{'action':'approve'});state=review['escalated_report'];self.assertEqual(state['report_type'],'ZONAL_TO_STATE')
        self.as_role('Director of Monitoring & Compliance');final=self.request('post',f"reports/{state['id']}/review/",{'action':'approve'});self.assertEqual(final['status'],'APPROVED');self.assertIsNone(final['escalated_report']);self.assertEqual(Report.objects.count(),3)
    def test_report_non_recipient_cannot_review(self):
        self.as_role('Ward Community Lead');r=self.request('post','reports/',{'title':'Isolated report','content':'Test'},201)
        self.as_role('General Secretary');self.request('post',f"reports/{r['id']}/review/",{'action':'approve'},403)
    def test_editorial_draft_return_revision_publish_lifecycle(self):
        self.as_role('Ward Communications Officer');a=self.request('post','articles/mine/',{'title':'Isolated acceptance story','content':'Local content','category':'GENERAL'},201)
        self.request('post',f"articles/{a['id']}/submit/",{})
        self.as_role('Director of Media & Communications');self.request('post',f"articles/{a['id']}/decision/",{'action':'return','note':'Please revise.'})
        self.as_role('Ward Communications Officer');a=self.request('patch',f"articles/mine/{a['id']}/",{'content':'Revised local content'});self.assertEqual(a['status'],'DRAFT');self.request('post',f"articles/{a['id']}/submit/",{})
        self.as_role('Director of Media & Communications');a=self.request('post',f"articles/{a['id']}/decision/",{'action':'publish'})
        self.c.force_authenticate(None);public=self.request('get',f"newsroom/{a['slug']}/");self.assertEqual(public['status'],'PUBLISHED')
    def test_media_upload_review_publication_lifecycle(self):
        self.as_role('Ward Communications Officer');m=self.request('post','media/mine/',{'title':'Isolated media','media_type':'PHOTO','file':self.image()},201,'multipart');self.assertEqual(m['status'],'PENDING')
        self.as_role('Director of Media & Communications');self.request('post',f"media/{m['id']}/decision/",{'action':'approve'})
        self.c.force_authenticate(None);r=self.request('get','gallery/');self.assertIn(m['id'],[x['id'] for x in r['results']])
    def test_article_body_image_upload_local_storage(self):
        self.as_role('Ward Communications Officer');r=self.request('post','articles/images/',{'image':self.image()},201,'multipart');self.assertIn('kpn_newsroom/',r['url'])
    def test_event_create_update_attendance_minutes_delete(self):
        self.as_role('Director of Programmes & Events');now=timezone.now();e=self.request('post','events/',{'title':'Isolated event','description':'Local fixture','location':'Isolated','start_date':now.isoformat(),'end_date':(now+timedelta(hours=1)).isoformat()},201)
        self.request('patch',f"events/{e['id']}/",{'title':'Updated isolated event'});self.request('put',f"events/{e['id']}/attendance/",{'records':[{'attendee':self.member.pk,'present':True}]})
        self.as_role('General Secretary');self.request('put',f"events/{e['id']}/minutes/",{'content':'Local minutes','summary':'Local summary','attendees_present':[self.member.pk],'is_published':True})
        self.as_role('Director of Programmes & Events');self.request('delete',f"events/{e['id']}/",status=204);self.request('get',f"events/{e['id']}/",status=404)
    def test_ward_meeting_attendance_minutes_and_scope(self):
        self.as_role('Ward Community Lead');m=self.request('post','ward-meetings/',{'title':'Isolated ward meeting','meeting_type':'GENERAL','date':'2026-10-13','agenda':'Local agenda'},201)
        self.request('put',f"ward-meetings/{m['id']}/attendance/",{'records':[{'attendee':self.member.pk,'present':True}]});self.request('patch',f"ward-meetings/{m['id']}/",{'minutes':'Local ward minutes'})
        self.request('put',f"ward-meetings/{m['id']}/attendance/",{'records':[{'attendee':self.other.pk,'present':True}]},403)
    def test_women_youth_welfare_create_participants_update_delete(self):
        for kind,title in [('women',"Director of Women's Development"),('youth','Director of Youth Development'),('welfare','Director of Member Support & Welfare')]:
            with self.subTest(kind=kind):
                self.as_role(title);p=self.request('post',f'programs/{kind}/',{'title':f'Isolated {kind} programme','description':'Local fixture','program_type':'OTHER'},201)
                self.request('put',f"programs/{kind}/{p['id']}/participants/",{'members':[self.member.pk]});r=self.request('get',f"programs/{kind}/{p['id']}/participants/");self.assertEqual(r['members'],[self.member.pk])
                self.request('patch',f"programs/{kind}/{p['id']}/",{'status':'COMPLETED'});self.request('delete',f"programs/{kind}/{p['id']}/",status=204)
    def test_finance_donate_verify_record_expense_balance(self):
        self.as_role('Director of Finance');d=self.request('post','finance/donations/',{'donor_name':'Isolated donor','amount':'100.00','reference':'isolated-bank-reference'},201)
        self.request('post',f"finance/donations/{d['id']}/verify/",{});self.as_role('Finance Operations Officer');self.request('post',f"finance/donations/{d['id']}/record/",{})
        self.request('post','finance/expenses/',{'description':'Isolated expense','amount':'25.00','category':'OTHER','date':'2026-10-13'},201)
        r=self.request('get','finance/summary/');self.assertEqual(r['balance'],'75.00');self.assertEqual(Donation.objects.get(pk=d['id']).status,'RECORDED')
        self.request('post','finance/reports/',{'title':'Isolated financial report','report_period':'Synthetic','summary':'Local summary','total_income':'100.00','total_expenses':'25.00'},201)
    def test_audit_create_edit_submit_locks_draft(self):
        self.as_role('Director of Audit & Accountability');a=self.request('post','management/audit-reports/',{'title':'Isolated audit','audit_period':'Synthetic','findings':'Local findings','recommendations':'Local recommendations'},201)
        self.request('patch',f"management/audit-reports/{a['id']}/",{'findings':'Revised local findings'});s=self.request('post',f"audit-reports/{a['id']}/submit/",{});self.assertEqual(s['submitted_to'],self.users['President'].pk)
        self.request('patch',f"management/audit-reports/{a['id']}/",{'findings':'Must not edit after submission'},403);self.request('delete',f"management/audit-reports/{a['id']}/",status=405)
    def test_disciplinary_legal_review_dismissal_lifecycle(self):
        self.as_role('President');a=self.request('post','discipline/',{'user':self.member.pk,'action_type':'DISMISSAL','reason':'Isolated acceptance only'},201)
        self.request('post',f"discipline/{a['id']}/decision/",{'decision':'APPROVE'},400)
        self.as_role('Director of Legal Affairs & Ethics');self.request('post',f"discipline/{a['id']}/legal-opinion/",{'legal_opinion':'Isolated favorable review','legal_approved':True})
        self.as_role('President');self.request('post',f"discipline/{a['id']}/decision/",{'decision':'APPROVE'});self.member.refresh_from_db();self.assertFalse(self.member.is_active)
    def test_notifications_read_unread_and_ownership(self):
        n=Notification.objects.create(user=self.member,title='Isolated',message='Local fixture');self.c.force_authenticate(self.member);self.assertEqual(self.request('get','notifications/summary/')['unread_count'],1)
        self.request('post',f'notifications/{n.pk}/state/',{'is_read':True});self.assertEqual(self.request('get','notifications/summary/')['unread_count'],0)
        self.request('post',f'notifications/{n.pk}/state/',{'is_read':False});self.c.force_authenticate(self.other);self.request('post',f'notifications/{n.pk}/read/',{},404)
        self.c.force_authenticate(self.member);self.request('post','notifications/read-all/',{},204);self.assertEqual(self.request('get','notifications/summary/')['unread_count'],0)
    def test_device_register_deactivate_delete(self):
        self.c.force_authenticate(self.member);d=self.request('post','devices/',{'token':'isolated-push-token','platform':'ANDROID'});self.request('post','devices/deactivate/',{'token':'isolated-push-token'},204);self.assertFalse(DeviceRegistration.objects.get(pk=d['id']).is_active);self.request('delete',f"devices/{d['id']}/",status=204)
    def test_device_token_follows_account_without_duplicate_or_leak(self):
        self.c.force_authenticate(self.member);self.request('post','devices/',{'token':'isolated-shared-device-token','platform':'ANDROID'})
        self.c.force_authenticate(self.other);self.request('post','devices/',{'token':'isolated-shared-device-token','platform':'ANDROID'})
        self.assertEqual(DeviceRegistration.objects.filter(token='isolated-shared-device-token').count(),1);self.assertEqual(DeviceRegistration.objects.get(token='isolated-shared-device-token').user_id,self.other.pk)
        self.c.force_authenticate(self.member);self.assertEqual(self.request('get','devices/')['count'],0)
    def test_announcements_create_receive_update_delete(self):
        self.as_role('President');a=self.request('post','announcements/',{'title':'Isolated notice','content':'Synthetic local notice','scope':'GENERAL','priority':'NORMAL'},201)
        self.c.force_authenticate(self.member);r=self.request('get','announcements/received/');self.assertIn(a['id'],[x['id'] for x in r['results']])
        self.as_role('President');self.request('patch',f"announcements/{a['id']}/",{'content':'Updated local notice'});self.request('delete',f"announcements/{a['id']}/",status=204)
    def test_reporter_promotion_and_revocation(self):
        self.as_role('Director of Media & Communications');self.request('post',f'reporters/{self.member.pk}/promote-community/',{});r=self.request('post',f'reporters/{self.member.pk}/promote-trusted/',{});self.assertTrue(r['is_trusted_reporter']);self.request('post',f'reporters/{self.member.pk}/revoke/',{});self.member.refresh_from_db();self.assertFalse(self.member.is_trusted_reporter)
    def test_faq_and_outreach_management_lifecycle(self):
        self.as_role('Assistant General Secretary');f=self.request('post','management/faq/',{'question':'Isolated question','answer':'Local answer'},201);self.request('patch',f"management/faq/{f['id']}/",{'answer':'Updated local answer'});self.request('delete',f"management/faq/{f['id']}/",status=204)
        self.as_role('Director of Public Relations & Partnerships');o=self.request('post','outreach/',{'organization':'Isolated organisation','engagement_type':'OTHER','date':'2026-10-13','purpose':'Local acceptance fixture'},201);self.request('patch',f"outreach/{o['id']}/",{'status':'COMPLETED'});self.request('delete',f"outreach/{o['id']}/",status=204)
    def test_finance_management_cannot_edit_or_delete_ledger(self):
        self.as_role('Director of Finance');d=self.request('post','management/donations/',{'donor_name':'Isolated','amount':'5.00','reference':'isolated-immutable-ledger'},201)
        self.request('patch',f"management/donations/{d['id']}/",{'amount':'500.00'},405);self.request('delete',f"management/donations/{d['id']}/",status=405)

    def test_report_review_structured_notes_are_rejected(self):
        self.as_role('Ward Community Lead');r=self.request('post','reports/',{'title':'Isolated report','content':'Local content'},201)
        self.as_role('LGA Network Lead')
        for notes in (None,[],{}):
            self.request('post',f"reports/{r['id']}/review/",{'action':'reject','notes':notes},400)
        self.assertEqual(Report.objects.get(pk=r['id']).status,'SUBMITTED')
    def test_old_account_cannot_deactivate_transferred_device(self):
        self.c.force_authenticate(self.member);self.request('post','devices/',{'token':'isolated-transferred-token'})
        self.c.force_authenticate(self.other);self.request('post','devices/',{'token':'isolated-transferred-token'})
        self.c.force_authenticate(self.member);self.request('post','devices/deactivate/',{'token':'isolated-transferred-token'},204)
        d=DeviceRegistration.objects.get(token='isolated-transferred-token');self.assertTrue(d.is_active);self.assertEqual(d.user,self.other)

    def test_escalated_report_cannot_be_changed_by_repeat_review(self):
        self.as_role('Ward Community Lead');r=self.request('post','reports/',{'title':'Isolated report','content':'Local content'},201)
        self.as_role('LGA Network Lead');self.request('post',f"reports/{r['id']}/review/",{'action':'approve'})
        self.request('post',f"reports/{r['id']}/review/",{'action':'reject','notes':'Repeat review must not overwrite history'},400)
        self.assertEqual(Report.objects.get(pk=r['id']).status,'ESCALATED');self.assertEqual(Report.objects.filter(parent_report_id=r['id']).count(),1)
    def test_direct_audit_create_cannot_set_reviewer_notes(self):
        self.as_role('Director of Audit & Accountability');a=self.request('post','audit-reports/',{'title':'Isolated audit','audit_period':'Synthetic','findings':'Local findings','recommendations':'Local recommendation','review_notes':'Forged reviewer note'},201)
        self.assertEqual(a['review_notes'],'')
