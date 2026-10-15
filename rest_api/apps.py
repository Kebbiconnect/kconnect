from django.apps import AppConfig


class RestApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rest_api'

    def ready(self):
        from django.conf import settings
        from campaigns.models import Campaign
        from core.models import Opportunity, CommunityInitiative, CommunityReport, Report
        from staff.models import User, WomensProgram, YouthProgram, WelfareProgram
        from media.models import MediaItem
        from donations.models import Donation
        overrides={}
        seen=set()
        for model,field,name in (
            (Campaign,'category','NewsCategory'),(Opportunity,'category','OpportunityCategory'),
            (CommunityInitiative,'category','CommunityCategory'),(Campaign,'status','ArticleStatus'),
            (Opportunity,'status','OpportunityStatus'),(CommunityInitiative,'status','CommunityStatus'),
            (CommunityReport,'status','CommunityReportStatus'),(Report,'status','HierarchicalReportStatus'),
            (User,'status','MembershipStatus'),(MediaItem,'status','MediaStatus'),
            (Donation,'status','DonationStatus'),(WomensProgram,'status','ProgrammeStatus'),
        ):
            field_choices=model._meta.get_field(field).choices
            fingerprint=tuple(sorted(str(value) for value,label in field_choices)) if field_choices else ()
            if fingerprint and fingerprint not in seen:
                overrides[name+'Enum']=list(field_choices);seen.add(fingerprint)
        settings.SPECTACULAR_SETTINGS['ENUM_NAME_OVERRIDES']=overrides
