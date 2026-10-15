from pathlib import Path
from django.test import TestCase
from django.urls import reverse, resolve
from django.template.loader import render_to_string
from leadership.models import RoleDefinition, Zone, LGA, Ward
from leadership.roles import ROLES_BY_TIER
from leadership.capabilities import capabilities_for, ALL_CAPABILITIES
from staff.models import User
from staff.quick_actions import actions_for
from telegram_integration.models import TelegramMembership
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

class QuickActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zone=Zone.objects.create(name='Quick action test zone')
        cls.lga=LGA.objects.create(name='Quick action test LGA',zone=cls.zone)
        cls.ward=Ward.objects.create(name='Quick action test ward',lga=cls.lga)
        cls.users=[]
        for tier,titles in ROLES_BY_TIER.items():
            for seat,title in enumerate(titles,1):
                rd=RoleDefinition.objects.create(title=title,tier=tier,seat_number=seat)
                user=User.objects.create_user(username=f'qa_{tier.lower()}_{seat}',phone=f'{tier}{seat}',role=tier,status='VERIFIED',role_definition=rd,zone=cls.zone,lga=cls.lga,ward=cls.ward)
                TelegramMembership.objects.create(user=user,telegram_user_id=-(800000+user.pk),is_verified=True,telegram_status='member')
                cls.users.append(user)
        cls.general=User.objects.create_user(username='qa_general',phone='qa_general',role='GENERAL',status='VERIFIED',zone=cls.zone,lga=cls.lga,ward=cls.ward)
        cls.users.append(cls.general)

    def test_all_42_roles_have_resolvable_concise_actions(self):
        self.assertEqual(len(self.users),42)
        for user in self.users:
            with self.subTest(role=user.role_definition.title if user.role_definition else 'Member'):
                actions=actions_for(user)
                self.assertGreaterEqual(len(actions),4)
                self.assertEqual(len({a['key'] for a in actions}),len(actions))
                for action in actions:
                    resolve(action['url'])
                    self.assertNotIn('#',action['url'])
                    self.assertLessEqual(len(action['label']),24)

    def test_pending_accounts_have_no_shortcuts(self):
        self.general.status='PENDING'
        self.assertEqual(actions_for(self.general),[])

    def test_member_does_not_see_leadership_tools(self):
        self.assertEqual({a['key'] for a in actions_for(self.general)},{'profile','opportunities','newsroom','calendar','rankings'})

    def test_media_has_oversight_without_invalid_submit_route(self):
        media=next(u for u in self.users if u.role_definition and u.role_definition.title=='Director of Media & Communications')
        self.assertNotIn('SUBMIT_REPORTS',capabilities_for(media))
        self.assertIn('REVIEW_REPORTS',capabilities_for(media))
        self.assertEqual([a['key'] for a in actions_for(media)][:4],['editorial','upload','articles','announcements'])
        self.assertNotIn('submit_report',{a['key'] for a in actions_for(media)})
        client=APIClient();client.credentials(HTTP_AUTHORIZATION='Bearer '+str(AccessToken.for_user(media)))
        self.assertEqual(client.get('/api/v1/reports/recipient/').status_code,403)
        self.assertEqual(client.get('/api/v1/reports/').status_code,200)

    def test_all_role_web_dashboards_render_and_actions_are_accessible(self):
        for user in self.users:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response=self.client.get(reverse('staff:dashboard'),follow=True)
                self.assertEqual(response.status_code,200)
                self.assertContains(response,'class="kpn-quick-actions"')
                self.assertEqual(response.content.decode().count('class="kpn-quick-tile"'),len(actions_for(user)))
                self.assertNotContains(response,'Log attendance for a recent ward gathering')
                for action in actions_for(user):
                    page=self.client.get(action['url'])
                    # A shortcut must actually open its authorized tool, not bounce
                    # back to the dashboard, return 403, or contain a dead anchor.
                    self.assertEqual(page.status_code,200,(user.username,action['key'],getattr(page,'url',None)))

    def test_only_four_actions_are_in_primary_grid(self):
        president=self.users[0]
        html=render_to_string('staff/dashboards/includes/_quick_actions.html',{'primary_actions':actions_for(president)[:4],'more_actions':actions_for(president)[4:]})
        self.assertEqual(html.split('<details')[0].count('class="kpn-quick-tile"'),4)
        self.assertIn('<summary>More actions',html)
