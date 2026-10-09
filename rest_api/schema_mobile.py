"""Documentation-only annotations. No request authentication/business logic is changed.
Free-form response objects describe legacy hand-built JSON accurately without pretending
that their nested fields have a serializer. Native resource requests have typed unions.
"""
import inspect
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema,extend_schema_view,OpenApiTypes,PolymorphicProxySerializer,OpenApiParameter
from . import auth,views,workflow_views,mobile_views,member_mobile_views,dashboard_views,mobilization_views

OBJECT={"type":"object","additionalProperties":True}
def object_schema(properties,required=()):return {"type":"object","properties":properties,**({"required":list(required)} if required else {})}
STR={"type":"string"};INT={"type":"integer"};BOOL={"type":"boolean"}
MEMBERS=object_schema({"members":{"type":"array","items":INT}},["members"])
NO_CONTENT={"LogoutView","PasswordChangeView","NotificationReadView","NotificationReadAllView","DeviceDeactivateView","TelegramDisconnectView"}
# APIViews need annotations because they return deliberate hand-built JSON, not a ModelSerializer.
for module in (auth,views,workflow_views,mobile_views,member_mobile_views,dashboard_views,mobilization_views):
    for name,cls in list(vars(module).items()):
        if not inspect.isclass(cls) or cls.__module__!=module.__name__ or not issubclass(cls,APIView):continue
        specs={}
        for method in ("get","post","put","patch","delete"):
            if method not in cls.__dict__:continue
            response={204:None} if name in NO_CONTENT or method=="delete" else {200:OBJECT}
            specs[method]=extend_schema(request={"application/json":OBJECT} if method in ("post","put","patch") else None,responses=response)
        if specs:extend_schema_view(**specs)(cls)

extend_schema_view(get=extend_schema(responses={200:object_schema({"organization":STR,"motto":STR,"introduction":STR,"pillars":{"type":"array","items":object_schema({"title":STR,"body":STR,"route":STR},["title","body","route"])}})}))(mobile_views.MobileHomeView)
extend_schema_view(get=extend_schema(responses={200:object_schema({"id":INT,"name":STR,"role_title":STR,"tier":STR,"jurisdiction":STR,"bio":STR,"photo":{"type":"string","nullable":True,"format":"uri"}})}))(mobile_views.PublicLeaderDetailView)
extend_schema_view(get=extend_schema(responses={200:object_schema({"unread_count":INT},["unread_count"])}))(mobile_views.NotificationSummaryView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"is_read":BOOL},["is_read"])},responses={200:object_schema({"id":INT,"is_read":BOOL})}))(mobile_views.NotificationStateView)
for cls in (mobile_views.ProgramParticipantsView,mobile_views.WardAttendanceView):
    if cls is mobile_views.ProgramParticipantsView:extend_schema_view(get=extend_schema(responses={200:MEMBERS}),put=extend_schema(request={"application/json":MEMBERS},responses={200:MEMBERS}))(cls)
    else:extend_schema_view(get=extend_schema(responses={200:{"type":"array","items":object_schema({"attendee":INT,"present":BOOL,"notes":STR})}}),put=extend_schema(request={"application/json":object_schema({"records":{"type":"array","items":object_schema({"attendee":INT,"present":BOOL,"notes":STR},["attendee"])}})},responses={200:{"type":"array","items":OBJECT}}))(cls)
extend_schema_view(post=extend_schema(request={"multipart/form-data":object_schema({"image":{"type":"string","format":"binary"}},["image"])},responses={201:object_schema({"success":INT,"file":object_schema({"url":{"type":"string","format":"uri"}})})},description="Verified WRITE_ARTICLES members only. Multipart JPG/PNG/GIF/WebP image; max 2 MB and 4000px per dimension. Returns Editor.js-compatible storage URL."))(mobile_views.ArticleBodyImageView)
RESOURCE_SERIALIZERS=list(dict.fromkeys(item[1] for item in mobile_views.RESOURCE_CONFIG.values()))
RESOURCE=PolymorphicProxySerializer(component_name="MobileManagementResource",serializers=RESOURCE_SERIALIZERS,resource_type_field_name=None)
RESOURCE_LIST=PolymorphicProxySerializer(component_name="MobileManagementResource",serializers=RESOURCE_SERIALIZERS,resource_type_field_name=None,many=True)
KIND=OpenApiParameter("kind",OpenApiTypes.STR,OpenApiParameter.PATH,enum=list(mobile_views.RESOURCE_CONFIG))
extend_schema_view(get=extend_schema(parameters=[KIND],responses=RESOURCE_LIST),post=extend_schema(parameters=[KIND],request=RESOURCE,responses={201:RESOURCE}))(mobile_views.ResourceListCreateView)
extend_schema_view(get=extend_schema(parameters=[KIND],responses=RESOURCE),put=extend_schema(parameters=[KIND],request=RESOURCE,responses=RESOURCE),patch=extend_schema(parameters=[KIND],request=RESOURCE,responses=RESOURCE),delete=extend_schema(parameters=[KIND],responses={204:None},description="Only resources marked can_delete by the catalog. Financial entries/audits cannot be deleted."))(mobile_views.ResourceDetailView)
PROGRAM=PolymorphicProxySerializer(component_name="MobileProgramme",serializers=[config[1] for config in workflow_views.PROGRAMS.values()],resource_type_field_name=None)
PKIND=OpenApiParameter("kind",OpenApiTypes.STR,OpenApiParameter.PATH,enum=list(workflow_views.PROGRAMS))
extend_schema_view(get=extend_schema(parameters=[PKIND],responses=PROGRAM),put=extend_schema(parameters=[PKIND],request=PROGRAM,responses=PROGRAM),patch=extend_schema(parameters=[PKIND],request=PROGRAM,responses=PROGRAM),delete=extend_schema(parameters=[PKIND],responses={204:None}))(mobile_views.ProgramDetailView)
extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("format_name",OpenApiTypes.STR,OpenApiParameter.PATH,enum=["csv","pdf"])],responses={(200,"text/csv"):OpenApiTypes.BINARY,(200,"application/pdf"):OpenApiTypes.BINARY},description="President EXPORT_MEMBERS permission required; CSV cells are formula-neutralized."))(member_mobile_views.MemberExportView)

from .serializers import MemberSerializer,CampaignSerializer
PASSWORD={"type":"string","format":"password","writeOnly":True}
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"refresh":STR},["refresh"])},responses={204:None}))(auth.LogoutView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"email":{"type":"string","format":"email"}},["email"])},responses={200:object_schema({"message":STR})}))(auth.PasswordResetRequestView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"uid":STR,"token":STR,"new_password":PASSWORD},["uid","token","new_password"])},responses={200:object_schema({"message":STR})}))(auth.PasswordResetConfirmView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"old_password":PASSWORD,"new_password":PASSWORD},["old_password","new_password"])},responses={204:None}))(auth.PasswordChangeView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"decision":{"type":"string","enum":["approve","reject"]}},["decision"])},responses={200:MemberSerializer}))(views.MemberDecisionView)
extend_schema_view(post=extend_schema(request=None,responses={200:CampaignSerializer},description="Owner's nonempty DRAFT only. Returned articles must be edited/saved to DRAFT before submitting again."))(views.ArticleSubmitView)
extend_schema_view(post=extend_schema(request={"application/json":object_schema({"action":{"type":"string","enum":["publish","return","reject"]},"note":STR},["action"])},responses={200:CampaignSerializer},description="REVIEW_ARTICLES required. Pending articles only. Return/reject requires an editor note."))(views.ArticleDecisionView)
extend_schema_view(get=extend_schema(parameters=[OpenApiParameter(name,OpenApiTypes.STR,OpenApiParameter.QUERY) for name in ('search','gender','status','tier','zone','lga','ward')],description="All filters remain within the member visibility rules enforced by staff.services.member_admin.members_qs."))(views.MemberListView)

extend_schema_view(get=extend_schema(parameters=[OpenApiParameter(name,OpenApiTypes.STR,OpenApiParameter.QUERY) for name in ('search','zone','lga','ward','role','tier','gender','status')],description="Exact website member_mobilization role-decorator authorization, always filtered through members_qs jurisdiction. Default status VERIFIED; legacy APPROVED alias maps to VERIFIED."))(mobilization_views.MobilizationListView)
extend_schema_view(get=extend_schema(responses={200:object_schema({"fields":{"type":"array","items":OBJECT}})},parameters=[OpenApiParameter(name,OpenApiTypes.INT,OpenApiParameter.QUERY) for name in ('zone','lga')]))(mobilization_views.MobilizationFiltersView)
extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("format_name",OpenApiTypes.STR,OpenApiParameter.PATH,enum=['csv','pdf'])]+[OpenApiParameter(name,OpenApiTypes.STR,OpenApiParameter.QUERY) for name in ('search','zone','lga','ward','role','tier','gender','status')],responses={(200,"text/csv"):OpenApiTypes.BINARY,(200,"application/pdf"):OpenApiTypes.BINARY},description="Same filters and jurisdiction as the native mobilization list; not restricted to the displayed page. CSV formula prefixes neutralized; PDF cells escaped."))(mobilization_views.MobilizationExportView)
