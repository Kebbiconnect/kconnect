"""Geographic directory: seeding, alias resolution, model integrity."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from leadership.models import LGA, Ward, Zone
from intelligence.geo import lga_for, resolve_alias
from intelligence.models import (
    Community, District, GeoAlias, GeoEntity, IntelligenceCategory,
)
from intelligence.tests.helpers import seed_directory

CANONICAL_LGAS = {
    'Aleiro', 'Arewa', 'Argungu', 'Augie', 'Bagudo', 'Birnin Kebbi', 'Bunza',
    'Dandi', 'Fakai', 'Gwandu', 'Jega', 'Kalgo', 'Koko/Besse', 'Maiyama',
    'Ngaski', 'Sakaba', 'Shanga', 'Suru', 'Danko/Wasagu', 'Yauri', 'Zuru',
}


class SeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def test_exactly_21_lgas_seeded_with_canonical_names(self):
        self.assertEqual(LGA.objects.count(), 21)
        self.assertEqual(set(LGA.objects.values_list('name', flat=True)), CANONICAL_LGAS)

    def test_categories_seeded(self):
        self.assertEqual(IntelligenceCategory.objects.count(), 22)
        security = IntelligenceCategory.objects.get(slug='security-public-safety')
        self.assertTrue(security.is_sensitive)
        self.assertFalse(IntelligenceCategory.objects.get(slug='education').is_sensitive)

    def test_seed_command_is_idempotent(self):
        seed_directory()
        seed_directory()
        self.assertEqual(LGA.objects.count(), 21)
        self.assertEqual(
            GeoAlias.objects.filter(status='APPROVED').count(), 4)


class AliasResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def test_canonical_name_resolves(self):
        kind, record = resolve_alias('Danko/Wasagu')
        self.assertEqual(kind, 'LGA')
        self.assertEqual(record.name, 'Danko/Wasagu')

    def test_blueprint_alias_examples_resolve(self):
        # Blueprint §5/Doc 08: "Wasagu" and "Danko/Wasagu" -> Danko/Wasagu LGA.
        for text in ('Wasagu', 'wasagu', 'Wasagu/Danko', 'Danko Wasagu'):
            kind, record = resolve_alias(text)
            self.assertEqual((kind, record.name), ('LGA', 'Danko/Wasagu'), text)

    def test_seed_variant_spelling_resolves(self):
        kind, record = resolve_alias('Aliero')
        self.assertEqual((kind, record.name), ('LGA', 'Aleiro'))

    def test_unknown_name_does_not_resolve(self):
        self.assertIsNone(resolve_alias('Nonexistent Place XYZ'))

    def test_pending_alias_does_not_resolve_until_approved(self):
        lga = LGA.objects.get(name='Zuru')
        district = District.objects.create(name='Rikoto District', lga=lga)
        alias = GeoAlias.objects.create(
            alias='Testville', target_kind='DISTRICT', district=district)
        self.assertIsNone(resolve_alias('Testville'))
        alias.status = 'APPROVED'
        alias.save()
        kind, record = resolve_alias('Testville')
        self.assertEqual((kind, record.pk), ('DISTRICT', district.pk))

    def test_lga_for_follows_record_links(self):
        lga = LGA.objects.get(name='Yauri')
        ward = Ward.objects.create(name='Test Ward', lga=lga)
        self.assertEqual(lga_for('Test Ward').pk, lga.pk)
        self.assertIsNone(lga_for('Nonexistent Place XYZ'))


class DirectoryIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def setUp(self):
        self.lga = LGA.objects.get(name='Argungu')
        self.other_lga = LGA.objects.get(name='Zuru')

    def test_community_can_carry_ward_and_district_of_same_lga(self):
        ward = Ward.objects.create(name='Test Ward', lga=self.lga)
        district = District.objects.create(name='Test District', lga=self.lga)
        community = Community(name='Test Community', lga=self.lga, ward=ward, district=district)
        community.full_clean()
        community.save()
        self.assertEqual(community.ward.lga_id, community.lga_id)
        self.assertEqual(community.district.lga_id, community.lga_id)

    def test_community_rejects_district_from_another_lga(self):
        district = District.objects.create(name='Foreign District', lga=self.other_lga)
        community = Community(name='Bad Community', lga=self.lga, district=district)
        with self.assertRaises(ValidationError):
            community.full_clean()

    def test_community_rejects_ward_from_another_lga(self):
        ward = Ward.objects.create(name='Foreign Ward', lga=self.other_lga)
        community = Community(name='Bad Community', lga=self.lga, ward=ward)
        with self.assertRaises(ValidationError):
            community.full_clean()

    def test_community_name_unique_within_lga(self):
        Community.objects.create(name='Dup Community', lga=self.lga)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Community.objects.create(name='Dup Community', lga=self.lga)

    def test_geo_alias_requires_exactly_one_matching_target(self):
        district = District.objects.create(name='Some District', lga=self.lga)
        two_targets = GeoAlias(alias='Ambiguous', target_kind='LGA', lga=self.lga, district=district)
        with self.assertRaises(ValidationError):
            two_targets.full_clean()
        wrong_kind = GeoAlias(alias='Wrong Kind', target_kind='DISTRICT', lga=self.lga)
        with self.assertRaises(ValidationError):
            wrong_kind.full_clean()

    def test_geo_entity_ward_must_match_lga(self):
        ward = Ward.objects.create(name='Entity Ward', lga=self.other_lga)
        entity = GeoEntity(name='Test School', kind='SCHOOL', lga=self.lga, ward=ward)
        with self.assertRaises(ValidationError):
            entity.full_clean()
